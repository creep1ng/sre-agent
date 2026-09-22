"""Issue #189 A1: incident_workflow is registrable and grantable in the catalog."""

import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from sre_agent.control.service import CatalogCreate
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationDenialCause,
)
from sre_agent.governance.dto import Grant, Principal, ResourceCatalogEntry
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import (
    CatalogRepository,
    GrantRepository,
    ResourceRepository,
)

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
# Exact PO-approved refinement (chain A): the stable workflow resource, not
# each incident or run. run.read is the only incident grant in this slice.
APPROVED_BODY = {
    "resource_type": "incident_workflow",
    "resource_id": "incident-response",
    "owner_id": "papiarcacamilo",
    "source": "incident_workflow",
    "source_ref": "incident-response@1.0.0",
    "status": "active",
    "discoverability": {
        "display_name": "Incident response workflow",
        "visibility": "private",
        "description": "Stable governed incident workflow resource.",
        "tags": ["incident", "workflow"],
    },
}
NOW = datetime(2026, 9, 22, tzinfo=UTC)


def test_approved_catalog_body_validates() -> None:
    body = CatalogCreate.model_validate(APPROVED_BODY)
    assert (body.resource_type, body.resource_id) == ("incident_workflow", "incident-response")
    assert (body.owner_id, body.source, body.source_ref) == (
        "papiarcacamilo",
        "incident_workflow",
        "incident-response@1.0.0",
    )
    assert body.status == "active"
    assert body.discoverability.visibility == "private"


def test_catalog_body_rejects_unknown_type_source_and_extra_fields() -> None:
    # NOTE: source-to-type matching is enforced by catalog.create (422), not the
    # DTO; the DTO only closes the body shape and the admitted vocabularies.
    with pytest.raises(ValidationError):
        CatalogCreate.model_validate({**APPROVED_BODY, "resource_type": "incident"})
    with pytest.raises(ValidationError):
        CatalogCreate.model_validate({**APPROVED_BODY, "source": "grants"})
    with pytest.raises(ValidationError):
        CatalogCreate.model_validate({**APPROVED_BODY, "extra": "nope"})


def test_catalog_entry_projection_enforces_workflow_source_and_lifecycle() -> None:
    entry = ResourceCatalogEntry.model_validate(APPROVED_BODY)
    assert entry.owner_id == "papiarcacamilo"
    with pytest.raises(ValidationError):
        ResourceCatalogEntry.model_validate({**APPROVED_BODY, "status": "draft"})
    with pytest.raises(ValidationError):
        ResourceCatalogEntry.model_validate({**APPROVED_BODY, "source": "bok"})


def test_grant_dto_admits_run_read_on_workflow() -> None:
    grant = Grant(
        grant_id="grant-demo-human-run-read-incident-response",
        principal_id="demo-human",
        action="run.read",
        resource={"resource_type": "incident_workflow", "resource_id": "incident-response"},
        effect="allow",
        status="active",
        created_at=NOW,
    )
    assert grant.action == "run.read"
    assert grant.resource.resource_type == "incident_workflow"


@pytest.fixture(scope="module", autouse=True)
def workflow_database() -> None:
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
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES ('demo-human','human','Demo','active',now(),now())"
        )


@pytest.mark.asyncio
async def test_register_evaluate_revoke_deny_lifecycle() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            entry = await CatalogRepository(session).create(
                "incident_workflow",
                "incident-response",
                "papiarcacamilo",
                "incident_workflow",
                "incident-response@1.0.0",
                "active",
                "Incident response workflow",
                "private",
                "Stable governed incident workflow resource.",
                ["incident", "workflow"],
            )
        assert (entry.resource_type, entry.status) == ("incident_workflow", "active")
        assert (entry.owner_id, entry.source) == ("papiarcacamilo", "incident_workflow")
        assert entry.discoverability.visibility == "private"

        async with database.transaction() as session:
            read = await CatalogRepository(session).get("incident_workflow", "incident-response")
        assert read is not None and read.source_ref == "incident-response@1.0.0"

        subject = Principal(
            principal_id="demo-human",
            kind="human",
            display_name="Demo",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
        async with database.transaction() as session:
            resources, grants = ResourceRepository(session), GrantRepository(session)
            engine = AuthorizationDecisionEngine(resources, grants)
            denied = await engine.evaluate(
                subject, "run.read", "incident_workflow", "incident-response"
            )
            assert denied.decision.decision == "deny"
            assert denied.denial_cause == AuthorizationDenialCause.GRANT_NOT_APPLICABLE

            created = await grants.create(
                "grant-demo-human-run-read-incident-response",
                "demo-human",
                "run.read",
                "incident_workflow",
                "incident-response",
            )
            assert created.status == "active"
            allowed = await engine.evaluate(
                subject, "run.read", "incident_workflow", "incident-response"
            )
            assert allowed.decision.decision == "allow"
            assert allowed.decision.reason_code == "grant_matched"

            revoked = await grants.revoke("grant-demo-human-run-read-incident-response")
            assert revoked is not None and revoked.status == "revoked"
            denied_again = await engine.evaluate(
                subject, "run.read", "incident_workflow", "incident-response"
            )
            assert denied_again.decision.decision == "deny"
            assert denied_again.denial_cause == AuthorizationDenialCause.GRANT_NOT_APPLICABLE
    finally:
        await database.dispose()


def test_authorization_vocabulary_contracts_workflow_grant() -> None:
    contract = yaml.safe_load(Path("agent/api/authorization.v1.yaml").read_text())
    assert contract["approved_resource_type"]["name"] == "incident_workflow"
    assert "run.read" in {action["name"] for action in contract["actions"]}
