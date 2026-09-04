import os
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from sre_agent.governance.authorization import ResourceAuthorizationFact
from sre_agent.governance.dto import AuditEvent
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import (
    AuditRepository,
    CredentialRepository,
    GrantRepository,
    PrincipalRepository,
    ResourceRepository,
)

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)


@pytest.fixture(scope="module", autouse=True)
def repository_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO principals VALUES
            ('admin-human','human','Admin','active',now(),now()),
            ('demo-human','human','Demo','active',now(),now()),
            ('incident-harness','agent','Incident harness','active',now(),now()),
            ('restricted-harness','agent','Restricted harness','active',now(),now())"""
        )
        connection.execute(
            """INSERT INTO credentials VALUES
            ('credential-incident-harness','incident-harness','inci1234',
             'scrypt$do-not-project','active',now(),NULL,NULL)"""
        )
        connection.execute(
            """INSERT INTO resources VALUES
            ('llm_model','triage-agent','active','triage-agent','triage-agent',
             'openai/gpt-4o-mini','openrouter','openai')"""
        )
        connection.execute(
            """INSERT INTO grants VALUES
            ('grant-incident-harness-invoke-triage-agent','incident-harness','invoke',
             'llm_model','triage-agent','allow','active',now()),
            ('grant-demo-human-invoke-triage-agent','demo-human','invoke',
             'llm_model','triage-agent','allow','revoked',now())"""
        )
        connection.commit()


def audit_event(*, allowed: bool, latency_ms: int | None = None) -> AuditEvent:
    digest = "a" * 64
    reference = {"algorithm": "hmac-sha-256", "key_version": 1, "digest": digest}
    policy_decision = (
        {
            "decision": "allow",
            "reason_code": "grant_matched",
            "grant_ref": reference,
        }
        if allowed
        else {"decision": "deny", "reason_code": "no_matching_grant"}
    )
    return AuditEvent(
        event_id=UUID(int=1 if allowed else 2),
        occurred_at=datetime(2026, 8, 22, 12, 0 if allowed else 1, tzinfo=UTC),
        operation="responses.create",
        action="invoke",
        stage="authorization",
        outcome="success" if allowed else "denied",
        reason_code="grant_matched" if allowed else "no_matching_grant",
        response_status=200 if allowed else 403,
        retryable=False,
        latency_ms=latency_ms,
        correlation={"request_id": UUID(int=11 if allowed else 12)},
        identity={
            "principal_ref": reference,
            "principal_kind": "agent",
            "principal_status": "active",
            "credential_ref": reference,
        },
        resource={"resource_type": "llm_model", "resource_ref": reference},
        model_alias_ref=reference,
        policy_decision=policy_decision,
        routing=None,
        untrusted_input=None,
        redaction={
            "policy_version": "redaction-1.0.0",
            "result": "success",
            "source_class": "none",
            "categories": [],
            "match_count": 0,
            "sink_eligible": False,
        },
        content_state="absent",
        redacted_content=None,
        authoritative_acceptance="accepted",
        ordinary_result="released",
        exporter_result="not_attempted",
        correction_of_event_id=None,
    )


@pytest.mark.asyncio
async def test_lookup_round_trips_are_secret_and_routing_safe() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        principal = await PrincipalRepository(session).get("incident-harness")
        credential = await CredentialRepository(session).get("credential-incident-harness")
        resource = await ResourceRepository(session).get("llm_model", "triage-agent")
        grant = await GrantRepository(session).find_active(
            "incident-harness", "invoke", "llm_model", "triage-agent"
        )

        assert principal is not None and principal.kind == "agent"
        assert credential is not None and credential.status == "active"
        assert resource is not None and resource.resource_id == "triage-agent"
        assert grant is not None and grant.resource == resource
        serialized = repr((credential.model_dump(), resource.model_dump(), grant.model_dump()))
        assert "key_hash" not in serialized
        assert "scrypt$do-not-project" not in serialized
        assert "router" not in serialized
        assert "inference_provider" not in serialized
    await database.dispose()


@pytest.mark.asyncio
async def test_resource_authorization_view_precedes_assignment_resolution() -> None:
    database = Database(DATABASE_URL)
    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    event.listen(database.engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        async with database.transaction() as session:
            repository = ResourceRepository(session)
            view = await repository.authorization_view("llm_model", "triage-agent")
            assert view is not None
            assert isinstance(view, ResourceAuthorizationFact)
            assert (view.resource_type, view.resource_id, view.status) == (
                "llm_model",
                "triage-agent",
                "active",
            )
            assert not hasattr(view, "concrete_model")
            assert await repository.authorization_view("llm_model", "missing") is None

        authorization_sql = next(
            statement for statement in statements if "FROM resources" in statement
        )
        assert "resources.status" in authorization_sql
        assert "model_alias_id" not in authorization_sql
        assert "concrete_model" not in authorization_sql
        assert "inference_provider" not in authorization_sql

        statements.clear()
        async with database.transaction() as session:
            assignment = await ResourceRepository(session).resolve_assignment(
                "llm_model", "triage-agent"
            )
            assert assignment is not None
            assert assignment.model_alias_id == "triage-agent"
            assert assignment.concrete_model == "openai/gpt-4o-mini"
            assert assignment.inference_provider == "openai"

        assignment_sql = next(
            statement for statement in statements if "FROM resources" in statement
        )
        assert "concrete_model" in assignment_sql
        assert "inference_provider" in assignment_sql
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", record_statement)
        await database.dispose()


@pytest.mark.asyncio
async def test_grant_decision_matches_only_the_active_exact_direct_grant() -> None:
    assert not hasattr(GrantRepository, "decide")
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        repository = GrantRepository(session)
        allow = await repository.find_active(
            "incident-harness", "invoke", "llm_model", "triage-agent"
        )
        assert allow is not None and allow.grant_id == "grant-incident-harness-invoke-triage-agent"
        for principal_id in (
            "restricted-harness",
            "admin-human",
            "demo-human",
            "absent-principal",
        ):
            assert (
                await repository.find_active(principal_id, "invoke", "llm_model", "triage-agent")
                is None
            )
        wrong_action = await repository.find_active(
            "incident-harness", "read_metadata", "llm_model", "triage-agent"
        )
        assert wrong_action is None
    await database.dispose()


@pytest.mark.asyncio
async def test_audits_commit_read_with_a_bound_and_reject_raw_mutation() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        repository = AuditRepository(session)
        await repository.append(audit_event(allowed=True, latency_ms=17))
        await repository.append(audit_event(allowed=False, latency_ms=3))

    async with database.transaction() as session:
        repository = AuditRepository(session)
        latest = await repository.read_recent(limit=1)
        all_events = await repository.read_recent(limit=2)
        assert latest[0].policy_decision is not None
        assert latest[0].policy_decision.decision == "deny"
        assert latest[0].latency_ms == 3
        assert {event.outcome for event in all_events} == {"success", "denied"}
        assert {event.latency_ms for event in all_events} == {3, 17}
        for invalid_limit in (0, 101):
            with pytest.raises(ValueError, match="limit must be between 1 and 100"):
                await repository.read_recent(limit=invalid_limit)

    for statement in (
        "UPDATE audit_events SET retryable=true",
        "DELETE FROM audit_events",
    ):
        with pytest.raises(DBAPIError, match="audit_events are append-only"):
            async with database.transaction() as session:
                await session.execute(text(statement))

    async with database.transaction() as session:
        events = await AuditRepository(session).read_recent(limit=10)
        assert len(events) == 2
        assert all(event.retryable is False for event in events)
    await database.dispose()


@pytest.mark.asyncio
async def test_audit_repository_requires_latency_before_flush() -> None:
    database = Database(DATABASE_URL)
    with pytest.raises(ValueError, match="latency_ms is required"):
        async with database.transaction() as session:
            await AuditRepository(session).append(audit_event(allowed=True))
    await database.dispose()
