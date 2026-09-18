"""Real HTTP acceptance evidence for issue #147's eight control routes."""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.jsonschema import DRAFT202012
from sqlalchemy.exc import StatementError

from sre_agent.application import create_application
from sre_agent.control.service import RotationIssuanceFailure
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import (
    AuditRepository,
    CredentialRepository,
    GrantRepository,
    PrincipalRepository,
    ResourceRepository,
)
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "CONTROL_ACCEPTANCE_DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"),
)
AUDIT_KEY = "issue147-acceptance-audit-key"
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
RELEASE = Path(__file__).parents[1] / "schemas/releases/2.0.0/json-schema"
RELEASE_23 = Path(__file__).parents[1] / "schemas/releases/2.3.0/json-schema"


@pytest.fixture(scope="module", autouse=True)
def migrated_acceptance_database() -> None:
    """Use only the dedicated database, never another test suite's database."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            assert await seed(database, SeedSettings.from_environment(SEED_ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


@pytest.fixture
def client() -> TestClient:
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def canonical() -> dict[str, Draft202012Validator]:
    documents = [json.loads(path.read_text()) for path in RELEASE.rglob("*.json")]
    registry = Registry().with_resources(
        (document["$id"], DRAFT202012.create_resource(document))
        for document in documents
        if "$id" in document
    )

    def validator(name: str) -> Draft202012Validator:
        document = next(item for item in documents if item.get("title") == name)
        return Draft202012Validator(document, registry=registry, format_checker=FormatChecker())

    return {
        "principal": validator("Principal"),
        "issuance": validator("CredentialIssuance"),
        "rotation": validator("CredentialRotation"),
        "list": validator("ListEnvelope"),
        "error": validator("ErrorEnvelope"),
    }


@pytest.fixture(scope="module")
def audit_23() -> Draft202012Validator:
    documents = [json.loads(path.read_text()) for path in RELEASE_23.rglob("*.json")]
    registry = Registry().with_resources(
        (document["$id"], DRAFT202012.create_resource(document))
        for document in documents
        if "$id" in document
    )
    document = next(item for item in documents if item.get("title") == "AuditEvent")
    return Draft202012Validator(document, registry=registry, format_checker=FormatChecker())


def headers(key: str = ADMIN_KEY, idempotency_key: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {key}"}
    if idempotency_key:
        result["Idempotency-Key"] = idempotency_key
    return result


def principal_body(principal_id: str) -> dict[str, str]:
    return {"principal_id": principal_id, "kind": "human", "display_name": principal_id}


def assert_valid(validator: Draft202012Validator, payload: object) -> None:
    assert not list(validator.iter_errors(payload)), payload


def audit_row(request_id: str) -> tuple[object, ...]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT authorization_denial_cause, response_status, identity, resource, "
            "policy_decision FROM audit_events WHERE correlation ->> 'request_id' = %s",
            (request_id,),
        ).fetchone()
    assert row is not None
    return row


def credential_count(principal_id: str) -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT count(*) FROM credentials WHERE principal_id = %s", (principal_id,)
        ).fetchone()[0]


def latest_rotation_audit() -> tuple[object, ...]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT authorization_denial_cause, response_status, identity, resource, "
            "policy_decision FROM audit_events WHERE operation = 'credentials.rotate' "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    return row


def latest_audit_event(operation: str, response_status: int):
    async def read():
        database = Database(DATABASE_URL)
        try:
            async with database.sessions() as session:
                events = await AuditRepository(session).read_recent(limit=100)
                return next(
                    event
                    for event in events
                    if event.operation == operation and event.response_status == response_status
                )
        finally:
            await database.dispose()

    return asyncio.run(read())


def test_rotation_operation_ref_matches_runtime_canonical_envelope() -> None:
    document = yaml.safe_load((RELEASE.parent / "openapi/control-plane.yaml").read_text())
    response_schema = document["paths"]["/v1/credentials/{id}/rotation"]["post"]["responses"][
        "201"
    ]["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "urn:sre-agent:schema:credential-rotation:2.0.0"}


def test_all_eight_routes_with_replays_expiry_and_revocation(
    client: TestClient, canonical: dict[str, Draft202012Validator]
) -> None:
    created = client.post(
        "/v1/principals",
        json=principal_body("route-human"),
        headers=headers(idempotency_key="create-route-human"),
    )
    assert created.status_code == 201
    route_principal = created.json()
    assert_valid(canonical["principal"], route_principal)
    assert client.get("/v1/principals", headers=headers()).status_code == 200
    listed = client.get("/v1/principals", headers=headers()).json()
    assert_valid(canonical["list"], listed)
    assert "route-human" in {item["principal_id"] for item in listed["items"]}
    fetched = client.get("/v1/principals/route-human", headers=headers())
    assert fetched.status_code == 200
    assert_valid(canonical["principal"], fetched.json())

    missing = client.put(
        "/v1/principals/route-human/status", json={"status": "inactive"}, headers=headers()
    )
    assert missing.status_code == 422
    assert_valid(canonical["error"], missing.json())
    changed = client.put(
        "/v1/principals/route-human/status",
        json={"status": "inactive", "expected_updated_at": route_principal["updated_at"]},
        headers=headers(),
    )
    assert changed.status_code == 200 and changed.json()["status"] == "inactive"
    assert_valid(canonical["principal"], changed.json())
    stale = client.put(
        "/v1/principals/route-human/status",
        json={"status": "active", "expected_updated_at": route_principal["updated_at"]},
        headers=headers(),
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "status_conflict"

    credential_principal = client.post(
        "/v1/principals",
        json=principal_body("credential-human"),
        headers=headers(idempotency_key="create-credential-human"),
    )
    assert credential_principal.status_code == 201
    old_expiry, new_expiry = "2031-01-02T03:04:05Z", "2032-01-02T03:04:05Z"
    issued = client.post(
        "/v1/principals/credential-human/credentials",
        json={"expires_at": old_expiry},
        headers=headers(idempotency_key="issue-credential-human"),
    )
    assert issued.status_code == 201
    first = issued.json()
    assert first["secret_revealed"] is True and first["replaced_credential_id"] is None
    assert first["credential"]["expires_at"] == old_expiry and first["key"].startswith("sre_")
    assert_valid(canonical["issuance"], first)
    replay = client.post(
        "/v1/principals/credential-human/credentials",
        json={"expires_at": old_expiry},
        headers=headers(idempotency_key="issue-credential-human"),
    )
    assert replay.status_code == 201 and replay.json()["secret_revealed"] is False
    assert "key" not in replay.json() and replay.json()["credential"] == first["credential"]
    assert_valid(canonical["issuance"], replay.json())
    credentials = client.get("/v1/principals/credential-human/credentials", headers=headers())
    assert credentials.status_code == 200 and first["key"] not in credentials.text
    assert_valid(canonical["list"], credentials.json())

    rotation = client.post(
        f"/v1/credentials/{first['credential']['credential_id']}/rotation",
        json={"expires_at": new_expiry},
        headers=headers(idempotency_key="rotate-credential-human"),
    )
    assert rotation.status_code == 201
    first_rotation = rotation.json()
    replacement = first_rotation["issuance"]
    assert first_rotation["old_credential"]["expires_at"] == old_expiry
    assert replacement["credential"]["expires_at"] == new_expiry
    assert replacement["replaced_credential_id"] == first["credential"]["credential_id"]
    assert replacement["secret_revealed"] is True and replacement["key"].startswith("sre_")
    assert_valid(canonical["rotation"], first_rotation)
    rotation_replay = client.post(
        f"/v1/credentials/{first['credential']['credential_id']}/rotation",
        json={"expires_at": new_expiry},
        headers=headers(idempotency_key="rotate-credential-human"),
    )
    assert rotation_replay.status_code == 201
    replay_rotation = rotation_replay.json()
    assert replay_rotation["replayed"] is True and "key" not in replay_rotation["issuance"]
    assert replay_rotation["issuance"]["secret_revealed"] is False
    assert_valid(canonical["rotation"], replay_rotation)
    assert client.get("/v1/principals", headers=headers(first["key"])).status_code == 401

    racing = client.post(
        "/v1/principals/credential-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-racing-credential"),
    ).json()["credential"]["credential_id"]
    before_race = credential_count("credential-human")

    def rotate_once(key: str) -> int:
        app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
        with TestClient(app, raise_server_exceptions=False) as race_client:
            return race_client.post(
                f"/v1/credentials/{racing}/rotation",
                json={},
                headers=headers(idempotency_key=key),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        racing_statuses = list(
            executor.map(rotate_once, ("race-rotation-key-1", "race-rotation-key-2"))
        )
    assert sorted(racing_statuses) == [201, 409]
    assert credential_count("credential-human") == before_race + 1

    replacement_id = replacement["credential"]["credential_id"]
    assert client.delete(f"/v1/credentials/{replacement_id}", headers=headers()).status_code == 204
    assert client.delete(f"/v1/credentials/{replacement_id}", headers=headers()).status_code == 204
    assert client.get("/v1/principals", headers=headers(replacement["key"])).status_code == 401
    inactive_rotation = client.post(
        f"/v1/credentials/{replacement_id}/rotation",
        json={},
        headers=headers(idempotency_key="revoked-rotation-key"),
    )
    assert inactive_rotation.status_code == 409
    assert inactive_rotation.json()["result"] == "failure"
    assert inactive_rotation.json()["error_code"] == "credential_inactive"
    assert_valid(canonical["rotation"], inactive_rotation.json())
    assert "key" not in inactive_rotation.text


def test_conflict_inactive_auth_and_hidden_denial_audit(
    client: TestClient, canonical: dict[str, Draft202012Validator]
) -> None:
    key = "conflict-principal-key"
    assert (
        client.post(
            "/v1/principals",
            json=principal_body("conflict-human"),
            headers=headers(idempotency_key=key),
        ).status_code
        == 201
    )
    conflict = client.post(
        "/v1/principals",
        json=principal_body("different-human"),
        headers=headers(idempotency_key=key),
    )
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
    )

    inactive = client.post(
        "/v1/principals",
        json=principal_body("inactive-human"),
        headers=headers(idempotency_key="create-inactive-human"),
    ).json()
    issued = client.post(
        "/v1/principals/inactive-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-inactive-human"),
    ).json()
    assert (
        client.put(
            "/v1/principals/inactive-human/status",
            json={"status": "inactive", "expected_updated_at": inactive["updated_at"]},
            headers=headers(),
        ).status_code
        == 200
    )
    inactive_denial = client.get("/v1/principals", headers=headers(issued["key"]))
    assert inactive_denial.status_code == 403
    inactive_cause, *_ = audit_row(inactive_denial.json()["request_id"])
    assert inactive_cause == "principal_inactive"

    denied_existing = client.get("/v1/principals/admin-human", headers=headers(RESTRICTED_KEY))
    denied_missing = client.get("/v1/principals/not-present-human", headers=headers(RESTRICTED_KEY))
    assert (denied_existing.status_code, denied_missing.status_code) == (403, 403)
    assert denied_existing.json()["error"] == denied_missing.json()["error"]
    assert_valid(canonical["error"], denied_existing.json())
    cause, status, identity, resource, decision = audit_row(denied_existing.json()["request_id"])
    assert cause == "grant_not_applicable" and status == 403
    assert identity is not None and resource["resource_type"] == "administrative_control"
    assert decision["decision"] == "deny"


def test_rotation_issuance_failure_rolls_back_and_audits(
    client: TestClient,
    canonical: dict[str, Draft202012Validator],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        client.post(
            "/v1/principals",
            json=principal_body("failure-human"),
            headers=headers(idempotency_key="create-failure-human"),
        ).status_code
        == 201
    )
    issued = client.post(
        "/v1/principals/failure-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-failure-human"),
    ).json()["credential"]
    before = credential_count("failure-human")

    async def fail_issuance(*_args: object, **_kwargs: object) -> object:
        raise RotationIssuanceFailure("injected acceptance failure")

    monkeypatch.setattr(CredentialRepository, "issue", fail_issuance)
    failed = client.post(
        f"/v1/credentials/{issued['credential_id']}/rotation",
        json={},
        headers=headers(idempotency_key="rotate-failure-human"),
    )
    assert failed.status_code == 409
    failure = failed.json()
    assert failure["result"] == "failure" and failure["error_code"] == "rotation_failed"
    assert failure["replacement_count"] == failure["transition_count"] == 0
    assert_valid(canonical["rotation"], failure)
    assert credential_count("failure-human") == before
    with psycopg.connect(DATABASE_URL) as connection:
        old = connection.execute(
            "SELECT status, revoked_at FROM credentials WHERE credential_id = %s",
            (issued["credential_id"],),
        ).fetchone()
    assert old == ("active", None)
    _, status, identity, resource, decision = latest_rotation_audit()
    assert status == 409 and identity is not None and resource is not None
    assert decision["decision"] == "allow"


def test_credential_issue_dependency_failure_is_sanitized_and_audited(
    client: TestClient,
    canonical: dict[str, Draft202012Validator],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert (
        client.post(
            "/v1/principals",
            json=principal_body("driver-failure-human"),
            headers=headers(idempotency_key="create-driver-failure-human"),
        ).status_code
        == 201
    )
    secret = "scrypt$never-log-driver-detail"

    async def fail_issuance(*_args: object, **_kwargs: object) -> object:
        raise StatementError(
            "credential insert failed",
            "INSERT INTO credentials (key_hash) VALUES (%(key_hash)s)",
            {"key_hash": secret},
            RuntimeError(f"driver detail: {secret}"),
            hide_parameters=True,
        )

    monkeypatch.setattr(CredentialRepository, "issue", fail_issuance)
    failed = client.post(
        "/v1/principals/driver-failure-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-driver-failure-human"),
    )
    assert failed.status_code == 500
    payload = failed.json()
    assert payload["error"]["code"] == "credential_issuance_failed"
    assert payload["retryable"] is True
    assert secret not in failed.text
    assert secret not in caplog.text
    assert_valid(canonical["error"], payload)
    with psycopg.connect(DATABASE_URL) as connection:
        reason, status = connection.execute(
            "SELECT reason_code, response_status FROM audit_events "
            "WHERE correlation ->> 'request_id' = %s",
            (payload["request_id"],),
        ).fetchone()
    assert (reason, status) == ("upstream_failed", 500)


def test_audit_append_failure_suppresses_ordinary_secret(
    canonical: dict[str, Draft202012Validator],
) -> None:
    class RejectingAudit:
        async def append(self, _event: object) -> None:
            raise RuntimeError("intentional acceptance audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/v1/principals/demo-human/credentials",
            json={},
            headers=headers(idempotency_key="audit-failure-issuance"),
        )
    assert response.status_code == 503 and response.json()["error"]["code"] == "audit_unavailable"
    assert "key" not in response.json() and "sre_" not in response.text
    assert_valid(canonical["error"], response.json())


def test_grant_revocation_is_authorized_convergent_audited_and_immediately_effective(
    client: TestClient,
) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active')"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES "
            "('grant-admin-human-admin-write-grants', 'admin-human', 'admin.write', "
            "'administrative_control', 'grants', 'allow', 'active', now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, model_alias_id, alias, "
            "concrete_model, router, inference_provider, owner_id, source, source_ref, "
            "display_name, visibility, description, tags) VALUES "
            "('llm_model', 't1-alias', 'active', 't1-alias', 't1-alias', "
            "'openai/gpt-4o-mini', 'openrouter', 'openai', "
            "'t1-alias', 'model_alias', 't1-alias', 't1-alias', 'private', '', '[]')"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES "
            "('grant-t1-invoke', 'incident-harness', 'invoke', 'llm_model', 't1-alias', "
            "'allow', 'active', now())"
        )

    async def decision() -> str:
        database = Database(DATABASE_URL)
        try:
            async with database.sessions() as session:
                principal = await PrincipalRepository(session).get("incident-harness")
                assert principal is not None
                evaluation = await AuthorizationDecisionEngine(
                    ResourceRepository(session), GrantRepository(session)
                ).evaluate(principal, "invoke", "llm_model", "t1-alias")
                return evaluation.decision.decision
        finally:
            await database.dispose()

    assert asyncio.run(decision()) == "allow"

    denied = client.delete("/v1/grants/grant-t1-invoke", headers=headers(RESTRICTED_KEY))
    assert denied.status_code == 403
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status FROM grants WHERE grant_id = 'grant-t1-invoke'"
        ).fetchone() == ("active",)

    first = client.delete("/v1/grants/grant-t1-invoke", headers=headers())
    replay = client.delete("/v1/grants/grant-t1-invoke", headers=headers())
    assert (first.status_code, replay.status_code) == (204, 204)
    assert first.content == replay.content == b""

    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status, count(*) OVER () FROM grants WHERE grant_id = 'grant-t1-invoke'"
        ).fetchone() == ("revoked", 1)
        events = connection.execute(
            "SELECT outcome, response_status, identity, resource, policy_decision, content_state, "
            "redacted_content FROM audit_events WHERE operation = 'grants.revoke' "
            "ORDER BY occurred_at, event_id"
        ).fetchall()

    assert len(events) == 3
    assert events[0][0:2] == ("denied", 403)
    assert events[0][4]["decision"] == "deny"
    for event in events[1:]:
        assert event[0:2] == ("success", 204)
        assert event[2] is not None
        assert event[3]["resource_type"] == "administrative_control"
        assert event[4]["decision"] == "allow"
        assert event[5:] == ("absent", None)

    assert asyncio.run(decision()) == "deny"


def test_grant_revocation_stages_mutation_and_audit_in_the_same_session(monkeypatch) -> None:
    grant_id = "grant-t1-shared-transaction"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active') ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES "
            "('grant-admin-human-admin-write-grants', 'admin-human', 'admin.write', "
            "'administrative_control', 'grants', 'allow', 'active', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES "
            "(%s, 'incident-harness', 'invoke.atomic-test', 'llm_model', "
            "'triage-agent', 'allow', 'active', now())",
            (grant_id,),
        )

    mutation_sessions: list[object] = []
    audit_sessions: list[object] = []
    emitted_events: list[object] = []
    original_revoke = GrantRepository.revoke

    async def tracked_revoke(repository: GrantRepository, target_id: str):
        mutation_sessions.append(repository._session)
        return await original_revoke(repository, target_id)

    class TransactionalAudit:
        async def append(self, _event: object) -> None:
            raise AssertionError("grant revocation must not use standalone audit append")

        async def append_in_transaction(self, event, session) -> None:
            audit_sessions.append(session)
            emitted_events.append(event)
            await AuditRepository(session).append(event)

    monkeypatch.setattr(GrantRepository, "revoke", tracked_revoke)
    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=TransactionalAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as atomic_client:
        response = atomic_client.delete(f"/v1/grants/{grant_id}", headers=headers())

    assert response.status_code == 204
    assert len(mutation_sessions) == len(audit_sessions) == 1
    assert mutation_sessions[0] is audit_sessions[0]
    documents = [
        json.loads(path.read_text())
        for path in (Path(__file__).parents[1] / "schemas/releases/2.3.0/json-schema").rglob(
            "*.json"
        )
    ]
    registry = Registry().with_resources(
        (document["$id"], DRAFT202012.create_resource(document))
        for document in documents
        if "$id" in document
    )
    audit_schema = next(
        document
        for document in documents
        if document.get("$id") == "urn:sre-agent:schema:audit-event:2.3.0"
    )
    assert_valid(
        Draft202012Validator(audit_schema, registry=registry, format_checker=FormatChecker()),
        emitted_events[0].model_dump(mode="json", exclude_none=True),
    )
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status FROM grants WHERE grant_id = %s", (grant_id,)
        ).fetchone() == ("revoked",)


def test_grant_revocation_rolls_back_when_authoritative_audit_rejects() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active') ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES "
            "('grant-admin-human-admin-write-grants', 'admin-human', 'admin.write', "
            "'administrative_control', 'grants', 'allow', 'active', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES "
            "('grant-t1-audit-rollback', 'incident-harness', 'invoke.audit-test', 'llm_model', "
            "'triage-agent', 'allow', 'active', now())"
        )

    class RejectingAudit:
        async def append(self, _event: object) -> None:
            raise RuntimeError("intentional grant audit rejection")

        async def append_in_transaction(self, _event: object, _session: object) -> None:
            raise RuntimeError("intentional grant audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.delete("/v1/grants/grant-t1-audit-rollback", headers=headers())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "audit_unavailable"
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status FROM grants WHERE grant_id = 'grant-t1-audit-rollback'"
        ).fetchone() == ("active",)


def _prepare_t2_grant_facts() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active') ON CONFLICT DO NOTHING"
        )
        for action in ("admin.read", "admin.write"):
            connection.execute(
                "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
                "effect, status, created_at) VALUES (%s, 'admin-human', %s, "
                "'administrative_control', 'grants', 'allow', 'active', now()) "
                "ON CONFLICT DO NOTHING",
                (f"grant-admin-human-{action.replace('.', '-')}-grants", action),
            )
        connection.execute(
            "INSERT INTO principals "
            "(principal_id, kind, display_name, status, created_at, updated_at) VALUES "
            "('t2-list-human', 'human', 'T2 list human', 'active', now(), now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO principals "
            "(principal_id, kind, display_name, status, created_at, updated_at) VALUES "
            "('t2-order-human', 'human', 'T2 order human', 'active', now(), now()) "
            "ON CONFLICT DO NOTHING"
        )
        for resource_id in (
            "t2-model",
            "t2-order-a",
            "t2-order-b",
            "t2-order-c",
            "t2-resource-only",
        ):
            connection.execute(
                "INSERT INTO resources (resource_type, resource_id, status, model_alias_id, "
                "alias, concrete_model, router, inference_provider, owner_id, source, "
                "source_ref, display_name, visibility, description, tags) VALUES "
                "('llm_model', %s, 'active', %s, %s, 'openai/gpt-4o-mini', "
                "'openrouter', 'openai', %s, 'model_alias', %s, %s, 'private', '', '[]') "
                "ON CONFLICT DO NOTHING",
                (
                    resource_id,
                    f"alias-{resource_id}",
                    resource_id,
                    f"alias-{resource_id}",
                    f"alias-{resource_id}",
                    resource_id,
                ),
            )


def test_grant_create_is_closed_idempotent_owned_and_metadata_only(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t2_grant_facts()
    body = {
        "grant_id": "grant-t2-created",
        "principal_id": "t2-list-human",
        "action": "invoke.t2",
        "resource": {"resource_type": "llm_model", "resource_id": "t2-model"},
        "effect": "allow",
    }
    request_headers = headers(idempotency_key="create-grant-t2-unit")

    denied = client.post(
        "/v1/grants",
        json=body,
        headers=headers(RESTRICTED_KEY, "denied-grant-t2-unit"),
    )
    first = client.post("/v1/grants", json=body, headers=request_headers)
    replay = client.post("/v1/grants", json=body, headers=request_headers)
    conflict = client.post(
        "/v1/grants",
        json={**body, "action": "invoke.changed"},
        headers=request_headers,
    )
    rejected_secret = client.post(
        "/v1/grants",
        json={**body, "grant_id": "grant-t2-secret", "router": "do-not-store"},
        headers=headers(idempotency_key="create-grant-t2-secret"),
    )

    assert denied.status_code == 403
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json() == {**body, "status": "active", "created_at": first.json()["created_at"]}
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert rejected_secret.status_code == 422
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM grants WHERE grant_id = 'grant-t2-created'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM grants WHERE grant_id = 'grant-t2-secret'"
            ).fetchone()[0]
            == 0
        )
        audit = connection.execute(
            "SELECT identity, resource, redacted_content FROM audit_events "
            "WHERE operation = 'grants.create' AND response_status = 201 "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert audit[0] is not None and audit[1] is not None
    assert audit[2] is None
    assert "admin-human" not in json.dumps(audit)
    success_event = latest_audit_event("grants.create", 201)
    conflict_event = latest_audit_event("grants.create", 409)
    assert success_event.reason_code == "grant_matched"
    assert conflict_event.reason_code == "status_conflict"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))
    assert_valid(audit_23, conflict_event.model_dump(mode="json", exclude_none=True))


def test_grant_create_replays_original_response_after_grant_mutation(client: TestClient) -> None:
    _prepare_t2_grant_facts()
    body = {
        "grant_id": "grant-t2-stable-replay",
        "principal_id": "t2-list-human",
        "action": "invoke.stable",
        "resource": {"resource_type": "llm_model", "resource_id": "t2-model"},
        "effect": "allow",
    }
    request_headers = headers(idempotency_key="create-grant-t2-stable-replay")

    first = client.post("/v1/grants", json=body, headers=request_headers)
    assert first.status_code == 201
    with psycopg.connect(DATABASE_URL) as connection:
        before_audits = connection.execute(
            "SELECT count(*) FROM audit_events WHERE operation = 'grants.create' "
            "AND response_status = 201"
        ).fetchone()[0]
        connection.execute(
            "UPDATE grants SET status = 'revoked' WHERE grant_id = 'grant-t2-stable-replay'"
        )

    replay = client.post("/v1/grants", json=body, headers=request_headers)

    assert replay.status_code == 201
    assert replay.content == first.content
    assert replay.json()["status"] == "active"
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status FROM grants WHERE grant_id = 'grant-t2-stable-replay'"
        ).fetchone() == ("revoked",)
        assert (
            connection.execute(
                "SELECT count(*) FROM audit_events WHERE operation = 'grants.create' "
                "AND response_status = 201"
            ).fetchone()[0]
            == before_audits
        )
        stored = connection.execute(
            "SELECT outcome -> 'response_payload' FROM idempotency_records "
            "WHERE canonical_path = '/v1/grants' AND outcome ->> 'resource_id' = %s",
            (body["grant_id"],),
        ).fetchone()
    assert stored is not None
    assert stored[0] == first.json()


def test_grant_listing_requires_a_filter_and_is_bounded_stable_and_non_enumerating(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t2_grant_facts()
    with psycopg.connect(DATABASE_URL) as connection:
        for suffix in ("a", "b", "c"):
            connection.execute(
                "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
                "effect, status, created_at) VALUES (%s, 't2-order-human', %s, 'llm_model', %s, "
                "'allow', 'active', '2026-09-17T12:00:00Z') ON CONFLICT DO NOTHING",
                (f"grant-t2-order-{suffix}", f"invoke.{suffix}", f"t2-order-{suffix}"),
            )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES ('grant-t2-resource', 't2-list-human', "
            "'invoke.resource', 'llm_model', 't2-resource-only', 'allow', 'active', now()) "
            "ON CONFLICT DO NOTHING"
        )

    assert client.get("/v1/grants", headers=headers()).status_code == 422
    assert (
        client.get("/v1/grants?principal_id=t2-list-human&limit=0", headers=headers()).status_code
        == 422
    )
    assert (
        client.get("/v1/grants?resource_id=t2-model&cursor=opaque", headers=headers()).status_code
        == 422
    )
    for query in ("principal_id=t2-list-human", "principal_id=absent-human"):
        response = client.get(f"/v1/grants?{query}", headers=headers(RESTRICTED_KEY))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "resource_unavailable"

    listed = client.get("/v1/grants?principal_id=t2-order-human&limit=2", headers=headers())
    assert listed.status_code == 200
    assert listed.json()["limit"] == 2
    assert listed.json()["truncated"] is True
    assert [item["grant_id"] for item in listed.json()["items"]] == [
        "grant-t2-order-c",
        "grant-t2-order-b",
    ]
    by_resource = client.get("/v1/grants?resource_id=t2-resource-only", headers=headers())
    assert by_resource.status_code == 200
    assert {item["grant_id"] for item in by_resource.json()["items"]} == {"grant-t2-resource"}
    assert all(
        "router" not in item and "secret" not in item for item in by_resource.json()["items"]
    )
    success_event = latest_audit_event("grants.list", 200)
    assert success_event.reason_code == "grant_matched"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))


def test_grant_create_and_audit_roll_back_together() -> None:
    _prepare_t2_grant_facts()

    class RejectingAudit:
        async def append(self, event: object) -> object:
            return event

        async def append_in_transaction(self, event: object, session: object) -> None:
            raise RuntimeError("intentional grant create audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    body = {
        "grant_id": "grant-t2-audit-rollback",
        "principal_id": "t2-list-human",
        "action": "invoke.rollback",
        "resource": {"resource_type": "llm_model", "resource_id": "t2-model"},
        "effect": "allow",
    }
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/v1/grants",
            json=body,
            headers=headers(idempotency_key="create-grant-t2-rollback"),
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "audit_unavailable"
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM grants WHERE grant_id = 'grant-t2-audit-rollback'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM idempotency_records "
                "WHERE canonical_path = '/v1/grants' AND outcome ->> 'resource_id' = "
                "'grant-t2-audit-rollback'"
            ).fetchone()[0]
            == 0
        )


def alias_body(model_alias_id: str) -> dict[str, str]:
    return {
        "model_alias_id": model_alias_id,
        "alias": model_alias_id,
        "concrete_model": "openai/gpt-4o-mini",
        "router": "openrouter",
        "inference_provider": "openai",
    }


def _prepare_t3_alias_facts() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'model_aliases', 'active') "
            "ON CONFLICT DO NOTHING"
        )
        for action in ("admin.read", "admin.write"):
            connection.execute(
                "INSERT INTO grants (grant_id, principal_id, action, resource_type, "
                "resource_id, effect, status, created_at) VALUES (%s, 'admin-human', %s, "
                "'administrative_control', 'model_aliases', 'allow', 'active', now()) "
                "ON CONFLICT DO NOTHING",
                (f"grant-admin-human-{action.replace('.', '-')}-model-aliases", action),
            )
        connection.commit()


def test_alias_create_is_closed_idempotent_owned_and_metadata_only(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t3_alias_facts()
    body = alias_body("t3-created")
    request_headers = headers(idempotency_key="create-alias-t3-unit")

    denied = client.post(
        "/v1/model-aliases",
        json=body,
        headers=headers(RESTRICTED_KEY, "denied-alias-t3-unit"),
    )
    first = client.post("/v1/model-aliases", json=body, headers=request_headers)
    replay = client.post("/v1/model-aliases", json=body, headers=request_headers)
    conflict = client.post(
        "/v1/model-aliases",
        json={**body, "concrete_model": "anthropic/claude-3-5-haiku"},
        headers=request_headers,
    )
    rejected_secret = client.post(
        "/v1/model-aliases",
        json={**body, "model_alias_id": "t3-secret", "alias": "t3-secret", "secret": "x"},
        headers=headers(idempotency_key="create-alias-t3-secret"),
    )
    rejected_status = client.post(
        "/v1/model-aliases",
        json={**body, "model_alias_id": "t3-status", "alias": "t3-status", "status": "active"},
        headers=headers(idempotency_key="create-alias-t3-status"),
    )

    assert denied.status_code == 403
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json() == {**body, "status": "active", "updated_at": first.json()["updated_at"]}
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert rejected_secret.status_code == 422
    assert rejected_status.status_code == 422
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM resources "
                "WHERE resource_type = 'llm_model' AND model_alias_id = 't3-created'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM resources "
                "WHERE resource_type = 'llm_model' AND model_alias_id IN ('t3-secret','t3-status')"
            ).fetchone()[0]
            == 0
        )
        audit = connection.execute(
            "SELECT identity, resource, redacted_content FROM audit_events "
            "WHERE operation = 'aliases.create' AND response_status = 201 "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert audit[0] is not None and audit[1] is not None
    assert audit[2] is None
    assert "admin-human" not in json.dumps(audit)
    success_event = latest_audit_event("aliases.create", 201)
    conflict_event = latest_audit_event("aliases.create", 409)
    assert success_event.reason_code == "grant_matched"
    assert conflict_event.reason_code == "status_conflict"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))
    assert_valid(audit_23, conflict_event.model_dump(mode="json", exclude_none=True))


def test_alias_create_replays_original_response_after_alias_mutation(client: TestClient) -> None:
    _prepare_t3_alias_facts()
    body = alias_body("t3-stable-replay")
    request_headers = headers(idempotency_key="create-alias-t3-stable-replay")

    first = client.post("/v1/model-aliases", json=body, headers=request_headers)
    assert first.status_code == 201
    with psycopg.connect(DATABASE_URL) as connection:
        before_audits = connection.execute(
            "SELECT count(*) FROM audit_events WHERE operation = 'aliases.create' "
            "AND response_status = 201"
        ).fetchone()[0]
        connection.execute(
            "UPDATE resources SET status = 'inactive' "
            "WHERE resource_type = 'llm_model' AND model_alias_id = 't3-stable-replay'"
        )
        connection.commit()

    replay = client.post("/v1/model-aliases", json=body, headers=request_headers)

    assert replay.status_code == 201
    assert replay.content == first.content
    assert replay.json()["status"] == "active"
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status FROM resources "
            "WHERE resource_type = 'llm_model' AND model_alias_id = 't3-stable-replay'"
        ).fetchone() == ("inactive",)
        assert (
            connection.execute(
                "SELECT count(*) FROM audit_events WHERE operation = 'aliases.create' "
                "AND response_status = 201"
            ).fetchone()[0]
            == before_audits
        )
        stored = connection.execute(
            "SELECT outcome -> 'response_payload' FROM idempotency_records "
            "WHERE canonical_path = '/v1/model-aliases' AND outcome ->> 'resource_id' = %s",
            (body["model_alias_id"],),
        ).fetchone()
    assert stored is not None
    assert stored[0] == first.json()


def test_alias_listing_is_ordered_bounded_and_non_enumerating(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t3_alias_facts()
    with psycopg.connect(DATABASE_URL) as connection:
        for suffix in ("a", "b", "c"):
            connection.execute(
                "INSERT INTO resources (resource_type, resource_id, status, model_alias_id, "
                "alias, concrete_model, router, inference_provider, owner_id, source, "
                "source_ref, display_name, visibility, description, tags) VALUES "
                "( 'llm_model', %s, 'active', %s, %s, 'openai/gpt-4o-mini', "
                "'openrouter', 'openai', %s, 'model_alias', %s, %s, 'private', '', '[]') "
                "ON CONFLICT DO NOTHING",
                (
                    f"t3-order-{suffix}",
                    f"t3-order-{suffix}",
                    f"t3-order-{suffix}",
                    f"t3-order-{suffix}",
                    f"t3-order-{suffix}",
                    f"t3-order-{suffix}",
                ),
            )
        connection.commit()

    assert client.get("/v1/model-aliases?limit=0", headers=headers()).status_code == 422
    assert client.get("/v1/model-aliases?limit=101", headers=headers()).status_code == 422
    assert client.get("/v1/model-aliases?cursor=opaque", headers=headers()).status_code == 422
    assert client.get("/v1/model-aliases?limit=2&unknown=1", headers=headers()).status_code == 422
    anonymous = client.get("/v1/model-aliases")
    assert anonymous.status_code == 401
    denied = client.get("/v1/model-aliases", headers=headers(RESTRICTED_KEY))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "resource_unavailable"

    full = client.get("/v1/model-aliases", headers=headers())
    assert full.status_code == 200
    assert full.json()["limit"] == 100
    assert full.json()["truncated"] is False
    identifiers = [item["model_alias_id"] for item in full.json()["items"]]
    assert identifiers == sorted(identifiers)
    ordered = [name for name in identifiers if name.startswith("t3-order-")]
    assert ordered == ["t3-order-a", "t3-order-b", "t3-order-c"]
    assert all(
        set(item)
        == {
            "model_alias_id",
            "alias",
            "concrete_model",
            "router",
            "inference_provider",
            "status",
            "updated_at",
        }
        for item in full.json()["items"]
    )

    bounded = client.get("/v1/model-aliases?limit=2", headers=headers())
    assert bounded.status_code == 200
    assert bounded.json()["limit"] == 2
    assert bounded.json()["truncated"] is True
    assert [item["model_alias_id"] for item in bounded.json()["items"]] == identifiers[:2]
    again = client.get("/v1/model-aliases?limit=2", headers=headers())
    assert again.content == bounded.content
    success_event = latest_audit_event("aliases.list", 200)
    assert success_event.reason_code == "grant_matched"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))


def test_alias_get_is_authorized_and_non_enumerating(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t3_alias_facts()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, model_alias_id, "
            "alias, concrete_model, router, inference_provider, owner_id, source, "
            "source_ref, display_name, visibility, description, tags) VALUES "
            "('llm_model', 't3-get-active', 'active', 't3-get-active', 't3-get-active', "
            "'openai/gpt-4o-mini', 'openrouter', 'openai', "
            "'t3-get-active', 'model_alias', 't3-get-active', 't3-get-active', "
            "'private', '', '[]') ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, model_alias_id, "
            "alias, concrete_model, router, inference_provider, owner_id, source, "
            "source_ref, display_name, visibility, description, tags) VALUES "
            "('llm_model', 't3-get-retired', 'inactive', 't3-get-retired', 't3-get-retired', "
            "'openai/gpt-4o-mini', 'openrouter', 'openai', "
            "'t3-get-retired', 'model_alias', 't3-get-retired', 't3-get-retired', "
            "'private', '', '[]') "
            "ON CONFLICT (resource_type, resource_id) DO UPDATE SET status = 'inactive'"
        )
        connection.commit()

    assert client.get("/v1/model-aliases/t3-get-active").status_code == 401
    denied = client.get("/v1/model-aliases/t3-get-active", headers=headers(RESTRICTED_KEY))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "resource_unavailable"
    assert client.get("/v1/model-aliases/INVALID", headers=headers()).status_code == 422
    for missing in ("t3-get-absent", "t3-get-retired"):
        response = client.get(f"/v1/model-aliases/{missing}", headers=headers())
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"

    fetched = client.get("/v1/model-aliases/t3-get-active", headers=headers())
    assert fetched.status_code == 200
    assert fetched.json() == {
        **alias_body("t3-get-active"),
        "status": "active",
        "updated_at": fetched.json()["updated_at"],
    }
    assert "secret" not in json.dumps(fetched.json()).lower()
    success_event = latest_audit_event("aliases.get", 200)
    assert success_event.reason_code == "grant_matched"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))


def test_alias_create_and_audit_roll_back_together() -> None:
    _prepare_t3_alias_facts()

    class RejectingAudit:
        async def append(self, event: object) -> object:
            return event

        async def append_in_transaction(self, event: object, session: object) -> None:
            raise RuntimeError("intentional alias create audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    body = alias_body("t3-audit-rollback")
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/v1/model-aliases",
            json=body,
            headers=headers(idempotency_key="create-alias-t3-rollback"),
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "audit_unavailable"
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM resources "
                "WHERE resource_type = 'llm_model' AND model_alias_id = 't3-audit-rollback'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM idempotency_records "
                "WHERE canonical_path = '/v1/model-aliases' AND outcome ->> 'resource_id' = "
                "'t3-audit-rollback'"
            ).fetchone()[0]
            == 0
        )


def _prepare_t5_alias(alias_id: str, client: TestClient) -> dict:
    _prepare_t3_alias_facts()
    created = client.post(
        "/v1/model-aliases",
        json=alias_body(alias_id),
        headers=headers(idempotency_key=f"create-alias-{alias_id}"),
    )
    assert created.status_code == 201
    return created.json()


def test_alias_assignment_replace_is_guarded_replay_safe_and_metadata_only(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    stored = _prepare_t5_alias("t5-assignment", client)
    token = stored["updated_at"]
    path = "/v1/model-aliases/t5-assignment/assignment"

    assert client.put(path, json=assignment_payload()).status_code == 401
    denied = client.put(
        path,
        json={**assignment_payload(), "expected_updated_at": token},
        headers=headers(RESTRICTED_KEY),
    )
    assert denied.status_code == 403
    assert (
        client.put(
            "/v1/model-aliases/INVALID/assignment",
            json=assignment_payload(),
            headers=headers(),
        ).status_code
        == 422
    )
    assert client.put(path, json=assignment_payload(), headers=headers()).status_code == 422
    rejected_status = client.put(
        path,
        json={**assignment_payload(), "expected_updated_at": token, "status": "active"},
        headers=headers(),
    )
    assert rejected_status.status_code == 422
    rejected_secret = client.put(
        path,
        json={**assignment_payload(), "expected_updated_at": token, "secret": "x"},
        headers=headers(),
    )
    assert rejected_secret.status_code == 422
    rejected_router = client.put(
        path,
        json={**assignment_payload(), "expected_updated_at": token, "router": "direct"},
        headers=headers(),
    )
    assert rejected_router.status_code == 422
    assert (
        client.put(
            "/v1/model-aliases/t5-assignment-absent/assignment",
            json={**assignment_payload(), "expected_updated_at": token},
            headers=headers(),
        ).status_code
        == 404
    )

    first = client.put(
        path,
        json={
            "concrete_model": "anthropic/claude-3-5-haiku",
            "router": "openrouter",
            "inference_provider": "anthropic",
            "expected_updated_at": token,
        },
        headers=headers(),
    )
    assert first.status_code == 200
    assert first.json()["concrete_model"] == "anthropic/claude-3-5-haiku"
    assert first.json()["inference_provider"] == "anthropic"
    assert first.json()["alias"] == "t5-assignment"
    assert first.json()["status"] == "active"
    assert first.json()["updated_at"] != token
    assert "secret" not in json.dumps(first.json()).lower()

    stale = client.put(
        path,
        json={**assignment_payload(), "expected_updated_at": token},
        headers=headers(),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "status_conflict"

    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT concrete_model, inference_provider, updated_at FROM resources "
            "WHERE resource_type = 'llm_model' AND model_alias_id = 't5-assignment'"
        ).fetchone()
    assert row is not None
    assert (row[0], row[1]) == ("anthropic/claude-3-5-haiku", "anthropic")
    assert row[2].isoformat().replace("+00:00", "Z") == first.json()["updated_at"].replace(
        "+00:00", "Z"
    )

    replay = client.put(
        path,
        json={
            "concrete_model": "anthropic/claude-3-5-haiku",
            "router": "openrouter",
            "inference_provider": "anthropic",
            "expected_updated_at": first.json()["updated_at"],
        },
        headers=headers(),
    )
    assert replay.status_code == 200
    assert replay.json()["concrete_model"] == "anthropic/claude-3-5-haiku"

    with psycopg.connect(DATABASE_URL) as connection:
        audit = connection.execute(
            "SELECT identity, resource, redacted_content FROM audit_events "
            "WHERE operation = 'aliases.assignment.replace' AND response_status = 200 "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert audit[0] is not None and audit[1] is not None
    assert audit[2] is None
    assert "admin-human" not in json.dumps(audit)
    success_event = latest_audit_event("aliases.assignment.replace", 200)
    conflict_event = latest_audit_event("aliases.assignment.replace", 409)
    assert success_event.reason_code == "grant_matched"
    assert conflict_event.reason_code == "status_conflict"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))
    assert_valid(audit_23, conflict_event.model_dump(mode="json", exclude_none=True))


def assignment_payload() -> dict[str, str]:
    return {
        "concrete_model": "openai/gpt-4o-mini",
        "router": "openrouter",
        "inference_provider": "openai",
    }


def test_alias_status_replace_conflicts_safely_and_hides_retired(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    stored = _prepare_t5_alias("t5-status", client)
    token = stored["updated_at"]
    path = "/v1/model-aliases/t5-status/status"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, model_alias_id, "
            "alias, concrete_model, router, inference_provider, updated_at, owner_id, source, "
            "source_ref, display_name, visibility, description, tags) VALUES "
            "('llm_model', 't5-status-retired', 'inactive', 't5-status-retired', "
            "'t5-status-retired', 'openai/gpt-4o-mini', 'openrouter', 'openai', now(), "
            "'t5-status-retired', 'model_alias', 't5-status-retired', 't5-status-retired', "
            "'private', '', '[]') "
            "ON CONFLICT (resource_type, resource_id) DO UPDATE SET status = 'inactive'"
        )
        connection.commit()

    anonymous = client.put(path, json={"status": "inactive", "expected_updated_at": token})
    assert anonymous.status_code == 401
    denied = client.put(
        path,
        json={"status": "inactive", "expected_updated_at": token},
        headers=headers(RESTRICTED_KEY),
    )
    assert denied.status_code == 403
    assert client.put(path, json={"status": "inactive"}, headers=headers()).status_code == 422
    rejected_assignment = client.put(
        path,
        json={"status": "inactive", "expected_updated_at": token, "router": "openrouter"},
        headers=headers(),
    )
    assert rejected_assignment.status_code == 422
    for missing in ("t5-status-absent", "t5-status-retired", "model-aliases"):
        response = client.put(
            f"/v1/model-aliases/{missing}/status",
            json={"status": "inactive", "expected_updated_at": token},
            headers=headers(),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"

    bumped = client.put(
        path, json={"status": "active", "expected_updated_at": token}, headers=headers()
    )
    assert bumped.status_code == 200
    assert bumped.json()["status"] == "active"
    fresh = bumped.json()["updated_at"]
    assert fresh != token

    stale = client.put(
        path, json={"status": "inactive", "expected_updated_at": token}, headers=headers()
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "status_conflict"
    conflict_event = latest_audit_event("aliases.status.replace", 409)
    assert conflict_event.reason_code == "status_conflict"
    assert_valid(audit_23, conflict_event.model_dump(mode="json", exclude_none=True))

    changed = client.put(
        path, json={"status": "inactive", "expected_updated_at": fresh}, headers=headers()
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "inactive"
    assert changed.json()["updated_at"] != fresh

    # Deactivation hides the alias: late writers observe the safe 404, never an
    # overwrite, and reactivation through the mutation API stays unavailable.
    hidden = client.put(
        path, json={"status": "active", "expected_updated_at": fresh}, headers=headers()
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "resource_not_found"

    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT status FROM resources "
            "WHERE resource_type = 'llm_model' AND model_alias_id = 't5-status'"
        ).fetchone() == ("inactive",)
        assert connection.execute(
            "SELECT status FROM resources "
            "WHERE resource_type = 'llm_model' AND model_alias_id = 't5-status-retired'"
        ).fetchone() == ("inactive",)
    success_event = latest_audit_event("aliases.status.replace", 200)
    assert success_event.reason_code == "grant_matched"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))


def test_alias_mutations_and_audit_roll_back_together(client: TestClient) -> None:
    _prepare_t5_alias("t5-audit-rollback", client)
    before = client.get("/v1/model-aliases/t5-audit-rollback", headers=headers()).json()

    class RejectingAudit:
        async def append(self, event: object) -> object:
            return event

        async def append_in_transaction(self, event: object, session: object) -> None:
            raise RuntimeError("intentional alias mutation audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        assignment = failing_client.put(
            "/v1/model-aliases/t5-audit-rollback/assignment",
            json={**assignment_payload(), "expected_updated_at": before["updated_at"]},
            headers=headers(),
        )
        status = failing_client.put(
            "/v1/model-aliases/t5-audit-rollback/status",
            json={"status": "inactive", "expected_updated_at": before["updated_at"]},
            headers=headers(),
        )

    assert assignment.status_code == 503
    assert status.status_code == 503
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT concrete_model, status, updated_at FROM resources "
            "WHERE resource_type = 'llm_model' AND model_alias_id = 't5-audit-rollback'"
        ).fetchone()
    assert row is not None
    assert (row[0], row[1]) == ("openai/gpt-4o-mini", "active")
    assert row[2].isoformat().replace("+00:00", "Z") == before["updated_at"].replace("+00:00", "Z")


def _prepare_t6_catalog_facts() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'catalog', 'active') "
            "ON CONFLICT DO NOTHING"
        )
        for action in ("admin.read", "admin.write"):
            connection.execute(
                "INSERT INTO grants (grant_id, principal_id, action, resource_type, "
                "resource_id, effect, status, created_at) VALUES (%s, 'admin-human', %s, "
                "'administrative_control', 'catalog', 'allow', 'active', now()) "
                "ON CONFLICT DO NOTHING",
                (f"grant-admin-human-{action.replace('.', '-')}-catalog", action),
            )
        connection.commit()


def _t6_body(
    resource_type: str,
    resource_id: str,
    owner_id: str,
    source: str,
    status: str,
    visibility: str = "private",
) -> dict:
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "owner_id": owner_id,
        "source": source,
        "source_ref": f"{owner_id}/{resource_id}",
        "status": status,
        "discoverability": {
            "display_name": resource_id,
            "visibility": visibility,
            "description": f"T6 {resource_type} {resource_id}.",
            "tags": ["t6"],
        },
    }


def test_catalog_create_is_closed_idempotent_owned_and_metadata_only(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t6_catalog_facts()
    _prepare_t3_alias_facts()
    body = _t6_body("mcp_server", "t6-server", "mcp-platform", "mcp", "registered")
    request_headers = headers(idempotency_key="create-catalog-t6-unit")

    denied = client.post(
        "/v1/catalog/resources",
        json=body,
        headers=headers(RESTRICTED_KEY, "denied-catalog-t6-unit"),
    )
    first = client.post("/v1/catalog/resources", json=body, headers=request_headers)
    replay = client.post("/v1/catalog/resources", json=body, headers=request_headers)
    conflict = client.post(
        "/v1/catalog/resources",
        json={**body, "status": "active"},
        headers=request_headers,
    )
    rejected_secret = client.post(
        "/v1/catalog/resources",
        json={**body, "resource_id": "t6-secret", "router": "do-not-store"},
        headers=headers(idempotency_key="create-catalog-t6-secret"),
    )
    rejected_llm = client.post(
        "/v1/catalog/resources",
        json={**body, "resource_type": "llm_model", "source": "model_alias"},
        headers=headers(idempotency_key="create-catalog-t6-llm"),
    )
    rejected_source = client.post(
        "/v1/catalog/resources",
        json={**body, "resource_id": "t6-source", "source": "skill"},
        headers=headers(idempotency_key="create-catalog-t6-source"),
    )

    assert denied.status_code == 403
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["resource_type"] == "mcp_server"
    assert first.json()["owner_id"] == "mcp-platform"
    assert "concrete_model" not in first.text and "router" not in first.text
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert rejected_secret.status_code == 422
    assert rejected_llm.status_code == 422
    assert rejected_source.status_code == 422
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM resources "
                "WHERE resource_type = 'mcp_server' AND resource_id = 't6-server'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM resources WHERE resource_id IN ('t6-secret', 't6-source')"
            ).fetchone()[0]
            == 0
        )
        audit = connection.execute(
            "SELECT identity, resource, redacted_content FROM audit_events "
            "WHERE operation = 'catalog.create' AND response_status = 201 "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert audit[0] is not None and audit[1] is not None
    assert audit[2] is None
    assert "admin-human" not in json.dumps(audit)
    success_event = latest_audit_event("catalog.create", 201)
    conflict_event = latest_audit_event("catalog.create", 409)
    assert success_event.reason_code == "grant_matched"
    assert conflict_event.reason_code == "status_conflict"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))
    assert_valid(audit_23, conflict_event.model_dump(mode="json", exclude_none=True))


def test_catalog_reads_cover_all_five_types_without_routing_leakage(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t6_catalog_facts()
    _prepare_t3_alias_facts()
    created = client.post(
        "/v1/model-aliases",
        json={**alias_body("t6-llm"), "owner_id": "alias-prod"},
        headers=headers(idempotency_key="create-alias-t6-llm"),
    )
    assert created.status_code == 201
    fixtures = [
        ("mcp_server", "t6-all-server", "mcp-platform", "mcp", "registered"),
        ("mcp_tool", "t6-all-tool", "mcp-platform", "mcp", "active"),
        ("skill", "t6-all-skill", "skill-search", "skill", "published"),
        ("bok_collection", "t6-all-bok", "bok-docs", "bok", "indexing"),
    ]
    for resource_type, resource_id, owner_id, source, status in fixtures:
        response = client.post(
            "/v1/catalog/resources",
            json=_t6_body(resource_type, resource_id, owner_id, source, status, "public"),
            headers=headers(idempotency_key=f"create-catalog-{resource_id}"),
        )
        assert response.status_code == 201, response.text

    llm = client.get("/v1/catalog/resources/llm_model/t6-llm", headers=headers())
    assert llm.status_code == 200
    assert llm.json()["owner_id"] == "alias-prod"
    assert llm.json()["source"] == "model_alias"
    assert set(llm.json()) == {
        "resource_type",
        "resource_id",
        "owner_id",
        "status",
        "source",
        "source_ref",
        "discoverability",
    }
    assert "concrete_model" not in llm.text and "router" not in llm.text

    for resource_type, resource_id, owner_id, source, status in fixtures:
        fetched = client.get(
            f"/v1/catalog/resources/{resource_type}/{resource_id}", headers=headers()
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["owner_id"] == owner_id
        assert fetched.json()["source"] == source
        assert fetched.json()["status"] == status
        assert "concrete_model" not in fetched.text

    listed = client.get("/v1/catalog/resources?limit=100", headers=headers())
    assert listed.status_code == 200
    pairs = {(item["resource_type"], item["resource_id"]) for item in listed.json()["items"]}
    assert ("llm_model", "t6-llm") in pairs
    for resource_type, resource_id, _, _, _ in fixtures:
        assert (resource_type, resource_id) in pairs
    ordered = [(item["resource_type"], item["resource_id"]) for item in listed.json()["items"]]
    assert ordered == sorted(ordered)
    assert all("concrete_model" not in json.dumps(item) for item in listed.json()["items"])
    success_event = latest_audit_event("catalog.read", 200)
    assert success_event.reason_code == "grant_matched"
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))
    list_event = latest_audit_event("catalog.list", 200)
    assert_valid(audit_23, list_event.model_dump(mode="json", exclude_none=True))


def test_catalog_list_is_bounded_stable_and_visibility_filtered(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t6_catalog_facts()
    with psycopg.connect(DATABASE_URL) as connection:
        for suffix in ("a", "b", "c"):
            connection.execute(
                "INSERT INTO resources (resource_type, resource_id, status, owner_id, source, "
                "source_ref, display_name, visibility, description, tags, updated_at) VALUES "
                "('skill', %s, 'published', 'skill-search', 'skill', %s, %s, 'public', '', "
                "'[]', now()) ON CONFLICT DO NOTHING",
                (f"t6-order-{suffix}", f"skill-search/t6-order-{suffix}", f"t6-order-{suffix}"),
            )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, owner_id, source, "
            "source_ref, display_name, visibility, description, tags, updated_at) VALUES "
            "('skill', 't6-hidden', 'published', 'skill-search', 'skill', "
            "'skill-search/t6-hidden', 't6-hidden', 'hidden', '', '[]', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, owner_id, source, "
            "source_ref, display_name, visibility, description, tags, updated_at) VALUES "
            "('skill', 't6-retired', 'inactive', 'skill-search', 'skill', "
            "'skill-search/t6-retired', 't6-retired', 'public', '', '[]', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.commit()

    assert client.get("/v1/catalog/resources?limit=0", headers=headers()).status_code == 422
    assert client.get("/v1/catalog/resources?limit=101", headers=headers()).status_code == 422
    assert client.get("/v1/catalog/resources?cursor=opaque", headers=headers()).status_code == 422
    assert (
        client.get("/v1/catalog/resources?limit=2&unknown=1", headers=headers()).status_code == 422
    )
    assert (
        client.get("/v1/catalog/resources?resource_type=unknown", headers=headers()).status_code
        == 422
    )
    assert (
        client.get("/v1/catalog/resources?visibility=secret", headers=headers()).status_code == 422
    )
    assert client.get("/v1/catalog/resources", headers=headers()).status_code == 200
    assert client.get("/v1/catalog/resources").status_code == 401
    denied = client.get("/v1/catalog/resources", headers=headers(RESTRICTED_KEY))
    assert denied.status_code == 403

    full = client.get("/v1/catalog/resources?resource_type=skill", headers=headers())
    assert full.status_code == 200
    identifiers = [item["resource_id"] for item in full.json()["items"]]
    assert "t6-hidden" not in identifiers and "t6-retired" not in identifiers
    assert [name for name in identifiers if name.startswith("t6-order-")] == [
        "t6-order-a",
        "t6-order-b",
        "t6-order-c",
    ]
    assert identifiers == sorted(identifiers)

    public = client.get("/v1/catalog/resources?visibility=public", headers=headers())
    assert public.status_code == 200
    assert all(item["discoverability"]["visibility"] == "public" for item in public.json()["items"])
    hidden = client.get("/v1/catalog/resources?visibility=hidden", headers=headers())
    assert hidden.status_code == 200 and hidden.json()["items"] == []

    bounded = client.get("/v1/catalog/resources?limit=2", headers=headers())
    assert bounded.status_code == 200 and bounded.json()["truncated"] is True
    assert client.get("/v1/catalog/resources?limit=2", headers=headers()).content == bounded.content
    success_event = latest_audit_event("catalog.list", 200)
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))


def test_catalog_read_is_authorized_and_non_enumerating(
    client: TestClient, audit_23: Draft202012Validator
) -> None:
    _prepare_t6_catalog_facts()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, owner_id, source, "
            "source_ref, display_name, visibility, description, tags, updated_at) VALUES "
            "('mcp_server', 't6-visible', 'registered', 'mcp-platform', 'mcp', "
            "'mcp-platform/t6-visible', 't6-visible', 'private', '', '[]', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, owner_id, source, "
            "source_ref, display_name, visibility, description, tags, updated_at) VALUES "
            "('mcp_server', 't6-concealed', 'registered', 'mcp-platform', 'mcp', "
            "'mcp-platform/t6-concealed', 't6-concealed', 'hidden', '', '[]', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, owner_id, source, "
            "source_ref, display_name, visibility, description, tags, updated_at) VALUES "
            "('mcp_server', 't6-offline', 'inactive', 'mcp-platform', 'mcp', "
            "'mcp-platform/t6-offline', 't6-offline', 'private', '', '[]', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.commit()

    assert client.get("/v1/catalog/resources/mcp_server/t6-visible").status_code == 401
    denied = client.get(
        "/v1/catalog/resources/mcp_server/t6-visible", headers=headers(RESTRICTED_KEY)
    )
    assert denied.status_code == 403
    assert (
        client.get("/v1/catalog/resources/unknown/t6-visible", headers=headers()).status_code == 422
    )
    assert (
        client.get("/v1/catalog/resources/mcp_server/INVALID ID", headers=headers()).status_code
        == 422
    )
    for missing in ("t6-absent", "t6-concealed", "t6-offline"):
        response = client.get(f"/v1/catalog/resources/mcp_server/{missing}", headers=headers())
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"

    fetched = client.get("/v1/catalog/resources/mcp_server/t6-visible", headers=headers())
    assert fetched.status_code == 200
    assert fetched.json()["resource_id"] == "t6-visible"
    assert "concrete_model" not in fetched.text
    success_event = latest_audit_event("catalog.read", 200)
    assert_valid(audit_23, success_event.model_dump(mode="json", exclude_none=True))


def test_catalog_create_and_audit_roll_back_together() -> None:
    _prepare_t6_catalog_facts()

    class RejectingAudit:
        async def append(self, event: object) -> object:
            return event

        async def append_in_transaction(self, event: object, session: object) -> None:
            raise RuntimeError("intentional catalog create audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    body = _t6_body("skill", "t6-rollback", "skill-search", "skill", "draft")
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/v1/catalog/resources",
            json=body,
            headers=headers(idempotency_key="create-catalog-t6-rollback"),
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "audit_unavailable"
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM resources "
                "WHERE resource_type = 'skill' AND resource_id = 't6-rollback'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM idempotency_records "
                "WHERE canonical_path = '/v1/catalog/resources' AND outcome ->> 'resource_id' = "
                "'skill/t6-rollback'"
            ).fetchone()[0]
            == 0
        )
