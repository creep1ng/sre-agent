"""Issue #330 B3: sending a human command over HTTP, against real PostgreSQL.

Written from what the boundary could get wrong before the route existed: a
caller with no credential, a credential holding one command action but not the
other, a body signing the command with somebody else's name, an agent credential
signing a human command, a body asserting an authority the route did not
resolve, a field of the wrong JSON type, a run addressed under another incident,
a command the workflow does not admit from the current state, and a retried
command deciding twice.

The case that matters most is the third one: the same authenticated human sends
two commands, and only the one their grant covers is accepted. That is the
separation the contract draws between asking for changes and approving a
mitigation, observed end to end.

Every case seeds the incidents it acts on, so each one passes alone, in any
order: the module only prepares what no case changes, the schema, the
principals and their grants.
"""

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from alembic import command as alembic
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository
from sre_agent.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from provision_incident_workflow import build_service, provision  # noqa: E402

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
INITIAL_STATE_PATH = (
    REPOSITORY_ROOT / "agent/fixtures/incidents/otel-payment-failure/initial-state.yaml"
)
# The application runs on the real clock, and the store requires updated_at to
# be at or after created_at, so the seed has to sit in the past of any run.
NOW = datetime.now(UTC) - timedelta(hours=1)
BEARERS: dict[str, str] = {}
RUNS: dict[str, str] = {}
MITIGATION = {
    "mitigation_id": "mit-disable-payment-flag",
    "description": "Disable the paymentFailure flag in flagd.",
    "steps": ["Ask the operator to set paymentFailure to off."],
    "risk": "low",
    "verification_check": "Payment error rate stays below one percent for ten minutes.",
    "approval_status": "pending",
    "execution_mode": "human",
    "created_by": "agent",
    "created_at": NOW.isoformat(),
}


@pytest.fixture(scope="module", autouse=True)
def authorized_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, "
            "resources, mcp_tools, mcp_servers, "
            "principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    alembic.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('admin-human','human','Admin','active',now(),now()),"
            "('demo-human','human','Demo operator','active',now(),now()),"
            "('sender-human','human','Sender only','active',now(),now()),"
            "('bystander-human','human','Bystander','active',now(),now()),"
            "('approving-harness','agent','Misconfigured harness','active',now(),now()),"
            "('whoami-expired','human','Expired whoami','active',now(),now()),"
            "('whoami-revoked','human','Revoked whoami','active',now(),now()),"
            "('whoami-inactive','human','Inactive whoami','inactive',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at) VALUES "
            "('administrative_control','catalog','active',now()),"
            "('administrative_control','grants','active',now())"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> None:
        async with database.transaction() as session:
            credentials = CredentialRepository(session)
            admin = await credentials.issue("admin-human")
            for name in (
                "demo-human",
                "sender-human",
                "bystander-human",
                "approving-harness",
                "whoami-expired",
                "whoami-revoked",
                "whoami-inactive",
            ):
                BEARERS[name] = f"Bearer {(await credentials.issue(name)).key}"
            await session.execute(
                text(
                    "UPDATE credentials SET created_at = now() - interval '2 seconds', "
                    "expires_at = now() - interval '1 second' "
                    "WHERE principal_id = 'whoami-expired'"
                )
            )
            await session.execute(
                text(
                    "UPDATE credentials SET status = 'revoked', revoked_at = created_at "
                    "WHERE principal_id = 'whoami-revoked'"
                )
            )
            grants = GrantRepository(session)
            for resource in ("catalog", "grants"):
                await grants.create(
                    f"grant-admin-human-admin-write-{resource}",
                    "admin-human",
                    "admin.write",
                    "administrative_control",
                    resource,
                )
        # The catalog resource comes from the governed path; slice B2 provisions
        # these two grants the same way, so here they are only fixture data.
        assert (
            await provision(build_service(database, b"0" * 32), f"Bearer {admin.key}")
        ).catalog_status == 201
        async with database.transaction() as session:
            grants = GrantRepository(session)
            # Provisioning now creates the demo-human command grants. Keep only the
            # sender and misconfigured-agent grants this HTTP suite needs.
            for principal, action in (
                ("sender-human", "run.command"),
                # A misconfiguration the route must survive: an agent holding the
                # human gate. Provisioning never grants it (B2).
                ("approving-harness", "run.approve"),
            ):
                await grants.create(
                    f"grant-{principal}-{action.replace('.', '-')}-incident-response",
                    principal,
                    action,
                    "incident_workflow",
                    "incident-response",
                )

    asyncio.run(_setup())
    asyncio.run(database.dispose())


async def _seed(database: Database, incident_id: str) -> str:
    document = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    document.update(
        state="mitigating",
        incident_id=incident_id,
        severity="sev2",
        mitigation_strategy=dict(MITIGATION),
    )
    run_id = f"run_{incident_id.replace('-', '')}"
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(incident_id, document, now=NOW)
        await work.runs.add(
            run_id,
            incident_id,
            {
                "workflow_version": "1.0.0",
                "current_state": "mitigating",
                "status": "awaiting_human",
                "pending_command": "approve_mitigation",
            },
            now=NOW,
        )
    return run_id


def _mitigating(*incident_ids: str) -> None:
    """Seed fresh incidents awaiting approval, for the case that calls it."""

    database = Database(DATABASE_URL)

    async def _all() -> None:
        for incident_id in incident_ids:
            RUNS[incident_id] = await _seed(database, incident_id)

    try:
        asyncio.run(_all())
    finally:
        asyncio.run(database.dispose())


def _body(command: str = "approve_mitigation", principal: str = "demo-human", **extra: Any) -> dict:
    return {
        "command": command,
        "actor": "human",
        "actor_reference": {"reference_version": "1.0.0", "principal_id": principal},
        **extra,
    }


def _send(
    incident_id: str,
    key: str | None,
    body: Any,
    *,
    bearer: str | None = "demo-human",
    run_id: str | None = None,
) -> Any:
    headers = {}
    if bearer is not None:
        headers["Authorization"] = BEARERS.get(bearer, bearer)
    if key is not None:
        headers["Idempotency-Key"] = key
    client = TestClient(create_application(Settings(DATABASE_URL)))
    return client.post(
        f"/v1/incidents/{incident_id}/runs/{run_id or RUNS[incident_id]}/commands",
        json=body,
        headers=headers,
    )


def _whoami(bearer: str | None = "demo-human") -> Any:
    headers = {} if bearer is None else {"Authorization": BEARERS.get(bearer, bearer)}
    client = TestClient(create_application(Settings(DATABASE_URL)))
    return client.get("/v1/whoami", headers=headers)


@pytest.mark.parametrize("principal", ["demo-human", "sender-human"])
def test_whoami_returns_only_the_authenticated_principal_without_caching(principal: str) -> None:
    response = _whoami(principal)
    assert response.status_code == 200
    assert response.json() == {"principal_id": principal}
    assert response.headers["cache-control"] == "no-store"
    assert "credential" not in response.text


@pytest.mark.parametrize(
    "bearer",
    [
        None,
        "Bearer nope",
        "Bearer sre_unkn_0123456789abcdefghijklmnop",
        "whoami-revoked",
        "whoami-expired",
        "whoami-inactive",
    ],
)
def test_whoami_rejects_unusable_credentials_uniformly(bearer: str | None) -> None:
    response = _whoami(bearer)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"] == {
        "code": "authentication_failed",
        "message": "Authentication failed.",
    }
    assert response.json()["retryable"] is False
    assert set(response.json()) == {"error", "request_id", "retryable"}
    assert len(response.json()["request_id"]) == 36
    assert bearer is None or bearer not in response.text


def test_whoami_is_mounted_and_documents_bearer_authentication() -> None:
    client = TestClient(create_application(Settings(DATABASE_URL)))
    operation = client.get("/openapi.json").json()["paths"]["/v1/whoami"]["get"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert client.get("/openapi.json").json()["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert "401" in operation["responses"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    model_name = schema["$ref"].rsplit("/", 1)[-1]
    model = client.get("/openapi.json").json()["components"]["schemas"][model_name]
    assert set(model["properties"]) == {"principal_id"}
    assert "Cache-Control" in operation["responses"]["200"]["headers"]


def _state(incident_id: str) -> str:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state->>'state' FROM incident.incidents WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_a_request_without_a_usable_credential_is_401() -> None:
    _mitigating("inc-b3-anonymous")
    anonymous = _send("inc-b3-anonymous", "key-anonymous-001", _body(), bearer=None)
    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"
    assert (
        _send("inc-b3-anonymous", "key-badkey-0001", _body(), bearer="Bearer nope").status_code
        == 401
    )
    assert _state("inc-b3-anonymous") == "mitigating"


def test_a_credential_without_the_action_is_403_and_changes_nothing() -> None:
    _mitigating("inc-b3-denied")
    denied = _send(
        "inc-b3-denied",
        "key-bystander-001",
        _body(principal="bystander-human"),
        bearer="bystander-human",
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "not_authorized"
    assert "paymentservice" not in denied.text
    assert _state("inc-b3-denied") == "mitigating"


def test_the_same_human_may_request_changes_and_still_not_approve() -> None:
    """One credential, two commands: only the granted action is accepted."""

    _mitigating("inc-b3-sender")
    refused = _send(
        "inc-b3-sender",
        "key-sender-approve-01",
        _body(principal="sender-human"),
        bearer="sender-human",
    )
    assert refused.status_code == 403
    assert _state("inc-b3-sender") == "mitigating"

    accepted = _send(
        "inc-b3-sender",
        "key-sender-changes-01",
        _body("request_changes", "sender-human", comment="Add the rollback step."),
        bearer="sender-human",
    )
    assert accepted.status_code == 202
    assert accepted.json()["current_state"] == "investigating"
    assert _state("inc-b3-sender") == "investigating"


def test_a_command_signed_with_another_name_is_refused_as_spoofed_attribution() -> None:
    _mitigating("inc-b3-spoof")
    spoofed = _send("inc-b3-spoof", "key-spoof-00001", _body(principal="admin-human"))
    assert spoofed.status_code == 403
    assert spoofed.json()["error"]["code"] == "actor_attribution_mismatch"
    assert _state("inc-b3-spoof") == "mitigating"


def test_an_agent_credential_cannot_sign_a_human_command() -> None:
    """Even holding run.approve, an agent never passes for the human gate."""

    _mitigating("inc-b3-agent")
    refused = _send(
        "inc-b3-agent",
        "key-agent-0000001",
        _body(principal="approving-harness"),
        bearer="approving-harness",
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "actor_attribution_mismatch"
    assert _state("inc-b3-agent") == "mitigating"
    with psycopg.connect(DATABASE_URL) as connection:
        count = connection.execute(
            "SELECT count(*) FROM incident.decisions WHERE incident_id = %s", ("inc-b3-agent",)
        ).fetchone()
    assert count == (0,)


def test_a_body_claiming_an_authority_the_route_did_not_resolve_is_422() -> None:
    _mitigating("inc-b3-claim")
    claim = {
        "action": "run.command",
        "resource": {"type": "incident_workflow", "id": "incident-response"},
    }
    lying = _send("inc-b3-claim", "key-claim-000001", _body(authorization=claim))
    assert lying.status_code == 422
    assert _state("inc-b3-claim") == "mitigating"
    honest = {
        "action": "run.approve",
        "resource": {"type": "incident_workflow", "id": "incident-response"},
    }
    assert _send("inc-b3-claim", "key-claim-000002", _body(authorization=honest)).status_code == 202
    assert _state("inc-b3-claim") == "verifying"


WRONG_TYPES = {
    "command-array": _body(command=[]),
    "command-object": _body(command={}),
    "command-in-array": _body(command=["approve_mitigation"]),
    "disposition-array": _body("propose_disposition", disposition=[]),
    "disposition-object": _body("propose_disposition", disposition={}),
    "reference-array": _body(actor_reference=[]),
    "comment-array": _body(comment=[]),
    "turn-object": _body(turn_id={}),
    "authorization-array": _body(authorization=[]),
}


@pytest.mark.parametrize("case", sorted(WRONG_TYPES))
def test_a_field_of_another_json_type_is_422_and_changes_nothing(case: str) -> None:
    """A field of the wrong JSON type is an invalid request, never a server error."""

    incident_id = f"inc-b3-{case}"
    _mitigating(incident_id)
    refused = _send(incident_id, "key-types-0000001", WRONG_TYPES[case])
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "validation_error"
    assert _state(incident_id) == "mitigating"


def test_a_run_of_another_incident_is_404_and_changes_neither() -> None:
    _mitigating("inc-b3-owner", "inc-b3-elsewhere")
    foreign = _send("inc-b3-elsewhere", "key-foreign-00001", _body(), run_id=RUNS["inc-b3-owner"])
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "run_not_found"
    missing = _send("inc-b3-missing", "key-missing-00001", _body(), run_id=RUNS["inc-b3-owner"])
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "incident_not_found"
    assert (_state("inc-b3-owner"), _state("inc-b3-elsewhere")) == ("mitigating", "mitigating")
    with psycopg.connect(DATABASE_URL) as connection:
        count = connection.execute(
            "SELECT count(*) FROM incident.run_events WHERE run_id = %s", (RUNS["inc-b3-owner"],)
        ).fetchone()
    assert count == (0,)


def test_commands_the_workflow_does_not_admit_are_409() -> None:
    _mitigating("inc-b3-refused", "inc-b3-late")
    for name, key in (("escalate", "key-escalate-0001"), ("cancel_run", "key-cancel-000001")):
        refused = _send("inc-b3-refused", key, _body(name))
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "run_conflict"
    assert _state("inc-b3-refused") == "mitigating"
    # Once approved, the mitigation is no longer pending: approving it again is a
    # command its state no longer admits.
    assert _send("inc-b3-late", "key-late-approve-1", _body()).status_code == 202
    late = _send("inc-b3-late", "key-late-approve-2", _body())
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "run_conflict"
    assert _state("inc-b3-late") == "verifying"


def test_the_approval_advances_the_run_and_is_attributed() -> None:
    _mitigating("inc-b3-approve")
    approved = _send(
        "inc-b3-approve", "key-approve-000001", _body(comment="Reviewed with the payments owner.")
    )
    assert approved.status_code == 202
    payload = approved.json()
    assert (payload["current_state"], payload["status"]) == ("verifying", "running")
    assert payload["pending_command"] is None
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT document->'approval'->'actor_reference'->>'principal_id',"
            " document->>'comment' FROM incident.decisions WHERE incident_id = %s",
            ("inc-b3-approve",),
        ).fetchone()
    assert row == ("demo-human", "Reviewed with the payments owner.")


def test_a_retried_command_returns_the_same_state_and_decides_once() -> None:
    _mitigating("inc-b3-retry")
    first = _send("inc-b3-retry", "key-retry-0000001", _body())
    again = _send("inc-b3-retry", "key-retry-0000001", _body())
    assert (first.status_code, again.status_code) == (202, 202)
    assert first.json() == again.json()
    conflicting = _send("inc-b3-retry", "key-retry-0000001", _body(comment="another request"))
    assert conflicting.status_code == 409
    with psycopg.connect(DATABASE_URL) as connection:
        count = connection.execute(
            "SELECT count(*) FROM incident.run_events WHERE run_id = %s", (RUNS["inc-b3-retry"],)
        ).fetchone()
    assert count == (1,)
