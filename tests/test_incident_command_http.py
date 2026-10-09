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
import json
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
from sqlalchemy import event

from sre_agent.application import create_application
from sre_agent.incident.runtime import ActorReference, IncidentCommand
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
    "mitigation_id": "mit_disable_payment_flag",
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
            "DROP TABLE IF EXISTS alert_triage, consumption_limit_policies, "
            "bok_section_chunks, bok_documents, "
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
            "('approving-harness','agent','Misconfigured harness','active',now(),now())"
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
            for name in ("demo-human", "sender-human", "bystander-human", "approving-harness"):
                BEARERS[name] = f"Bearer {(await credentials.issue(name)).key}"
            grants = GrantRepository(session)
            for resource in ("catalog", "grants"):
                await grants.create(
                    f"grant-admin-human-admin-write-{resource}",
                    "admin-human",
                    "admin.write",
                    "administrative_control",
                    resource,
                )
        provisioned = await provision(build_service(database, b"0" * 32), f"Bearer {admin.key}")
        assert provisioned.catalog_status == 201
        assert provisioned.command_grant_status == 201 and provisioned.run_command_active
        assert provisioned.approve_grant_status == 201 and provisioned.run_approve_active
        control = build_service(database, b"0" * 32)
        for principal, action in (
            ("sender-human", "run.command"),
            # A governed misconfiguration the route must survive: an agent
            # holding the human gate. The route must still reject the agent.
            ("approving-harness", "run.approve"),
        ):
            grant_id = f"grant-{principal}-{action.replace('.', '-')}-incident-response"
            created = await control.create_grant(
                {
                    "grant_id": grant_id,
                    "principal_id": principal,
                    "action": action,
                    "resource": {
                        "resource_type": "incident_workflow",
                        "resource_id": "incident-response",
                    },
                    "effect": "allow",
                },
                f"Bearer {admin.key}",
                f"issue330-fixture-{principal}-{action.replace('.', '-')}",
            )
            assert created.status_code == 201

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
    if isinstance(command, str) and command in {
        "approve_mitigation",
        "reject_mitigation",
        "request_changes",
    }:
        extra.setdefault("expected_incident_version", 0)
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
    query_log: list[tuple[str, Any]] | None = None,
) -> Any:
    headers = {}
    if bearer is not None:
        headers["Authorization"] = BEARERS.get(bearer, bearer)
    if key is not None:
        headers["Idempotency-Key"] = key
    app = create_application(Settings(DATABASE_URL))
    engine = app.state.database.engine.sync_engine

    def capture(_connection, _cursor, statement, parameters, _context, _executemany) -> None:
        assert query_log is not None
        query_log.append((statement, parameters))

    if query_log is not None:
        event.listen(engine, "before_cursor_execute", capture)
    try:
        with TestClient(app) as client:
            return client.post(
                f"/v1/incidents/{incident_id}/runs/{run_id or RUNS[incident_id]}/commands",
                json=body,
                headers=headers,
            )
    finally:
        if query_log is not None:
            event.remove(engine, "before_cursor_execute", capture)


def _assert_run_lookup_is_scoped(
    statements: list[tuple[str, Any]], *, incident_id: str, run_id: str
) -> None:
    run_queries = [
        (statement.lower(), parameters)
        for statement, parameters in statements
        if "from incident.runs" in statement.lower()
    ]
    assert run_queries
    for statement, parameters in run_queries:
        normalized = " ".join(statement.split())
        assert "where run_id=" in normalized and "and incident_id=" in normalized, normalized
        assert run_id in str(parameters)
        assert incident_id in str(parameters)
    assert not any(
        "from incident.snapshots" in query.lower() or "from incident.run_events" in query.lower()
        for query, _ in statements
    )


def _state(incident_id: str) -> str:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state->>'state' FROM incident.incidents WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _replace_mitigation(incident_id: str, mitigation_id: str) -> None:
    """Represent a newer proposal revision before exercising the stale client."""
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.incidents SET "
            "state=jsonb_set(state, '{mitigation_strategy,mitigation_id}', to_jsonb(%s::text)), "
            "version=version+1, updated_at=now() WHERE incident_id=%s",
            (mitigation_id, incident_id),
        )


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


@pytest.mark.parametrize(
    ("case", "revision"),
    [
        ("null", None),
        ("boolean", True),
        ("string", "0"),
        ("array", []),
        ("object", {}),
        ("negative", -1),
    ],
)
def test_supplied_review_revision_must_be_a_nonnegative_integer(case: str, revision: Any) -> None:
    incident_id = f"inc-b3-version-{case}"
    _mitigating(incident_id)
    body = _body()
    body["expected_incident_version"] = revision

    refused = _send(incident_id, f"key-version-{case}-0001", body)

    assert refused.status_code == 422
    with psycopg.connect(DATABASE_URL) as connection:
        version, state, decisions, events = connection.execute(
            "SELECT i.version, i.state->>'state', "
            "(SELECT count(*) FROM incident.decisions WHERE incident_id=i.incident_id), "
            "(SELECT count(*) FROM incident.run_events WHERE incident_id=i.incident_id) "
            "FROM incident.incidents i WHERE i.incident_id=%s",
            (incident_id,),
        ).fetchone()
    assert (version, state, decisions, events) == (0, "mitigating", 0, 0)


def test_an_approval_for_v2_cannot_authorize_a_changed_v3_proposal() -> None:
    incident_id = "inc-b3-v2-cannot-approve-v3"
    _mitigating(incident_id)
    _replace_mitigation(incident_id, "mit_v3_payment_flag")
    with psycopg.connect(DATABASE_URL) as connection:
        before = connection.execute(
            "SELECT i.version, i.state->'mitigation_strategy'->>'mitigation_id', "
            "(SELECT count(*) FROM incident.decisions WHERE incident_id=i.incident_id), "
            "(SELECT count(*) FROM incident.run_events WHERE incident_id=i.incident_id) "
            "FROM incident.incidents i WHERE i.incident_id=%s",
            (incident_id,),
        ).fetchone()

    stale = _send(incident_id, "key-stale-v2-approve-v3-001", _body(expected_incident_version=0))

    assert stale.status_code == 409
    with psycopg.connect(DATABASE_URL) as connection:
        after = connection.execute(
            "SELECT i.version, i.state->'mitigation_strategy'->>'mitigation_id', "
            "(SELECT count(*) FROM incident.decisions WHERE incident_id=i.incident_id), "
            "(SELECT count(*) FROM incident.run_events WHERE incident_id=i.incident_id) "
            "FROM incident.incidents i WHERE i.incident_id=%s",
            (incident_id,),
        ).fetchone()
    assert before == after == (1, "mit_v3_payment_flag", 0, 0)


def test_a_run_of_another_incident_is_404_and_changes_neither() -> None:
    _mitigating("inc-b3-owner", "inc-b3-elsewhere")
    queries: list[tuple[str, Any]] = []
    owner_run_id = RUNS["inc-b3-owner"]
    foreign = _send(
        "inc-b3-elsewhere",
        "key-foreign-00001",
        _body(),
        run_id=owner_run_id,
        query_log=queries,
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "run_not_found"
    _assert_run_lookup_is_scoped(queries, incident_id="inc-b3-elsewhere", run_id=owner_run_id)
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
    # Each _send creates a new application, so this exact replay crosses an
    # app restart and must return the persisted first result without re-deciding.
    reloaded = _send(
        "inc-b3-approve",
        "key-approve-000001",
        _body(comment="Reviewed with the payments owner."),
    )
    assert reloaded.status_code == 202
    assert reloaded.json() == payload
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT document->'approval'->'actor_reference'->>'principal_id',"
            " document->>'comment', document->'approval'->>'mitigation_id',"
            " document->'approval'->>'reviewed_incident_version',"
            " (SELECT count(*) FROM incident.decisions WHERE incident_id = %s),"
            " (SELECT count(*) FROM incident.run_events WHERE incident_id = %s) "
            "FROM incident.decisions WHERE incident_id = %s",
            ("inc-b3-approve", "inc-b3-approve", "inc-b3-approve"),
        ).fetchone()
    assert row == (
        "demo-human",
        "Reviewed with the payments owner.",
        MITIGATION["mitigation_id"],
        "0",
        1,
        1,
    )


def test_legacy_review_replay_is_exact_and_fresh_versionless_review_is_rejected() -> None:
    _mitigating("inc-b3-legacy-replay", "inc-b3-versionless")

    versionless = _body()
    versionless.pop("expected_incident_version")
    rejected = _send("inc-b3-versionless", "key-no-version-v3", versionless)
    assert rejected.status_code == 422
    with psycopg.connect(DATABASE_URL) as connection:
        fresh_counts = connection.execute(
            "SELECT (SELECT count(*) FROM incident.run_events WHERE incident_id = %s), "
            "(SELECT count(*) FROM incident.decisions WHERE incident_id = %s)",
            ("inc-b3-versionless", "inc-b3-versionless"),
        ).fetchone()
    assert fresh_counts == (0, 0)

    incident_id = "inc-b3-legacy-replay"
    key = "key-legacy-v2-approval"
    approved = _send(incident_id, key, _body())
    assert approved.status_code == 202
    run_id = RUNS[incident_id]
    legacy_hash = IncidentCommand(
        command_id=key,
        incident_id=incident_id,
        run_id=run_id,
        transition_id="apply_mitigation",
        actor="human",
        actor_reference=ActorReference(principal_id="demo-human"),
        outcome="approve",
        approval=True,
    ).payload_sha256()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.transition_commits SET payload_sha256 = %s "
            "WHERE incident_id = %s AND command_id = %s",
            (legacy_hash, incident_id, key),
        )
        before = connection.execute(
            "SELECT state->>'state', state->'mitigation_strategy'->>'mitigation_id', "
            "state->'mitigation_strategy'->>'approval_status', version FROM incident.incidents "
            "WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()
        counts_before = connection.execute(
            "SELECT (SELECT count(*) FROM incident.run_events WHERE incident_id = %s), "
            "(SELECT count(*) FROM incident.decisions WHERE incident_id = %s)",
            (incident_id, incident_id),
        ).fetchone()
    assert before == ("verifying", MITIGATION["mitigation_id"], "approved", 1)
    assert counts_before == (1, 1)

    exact_replay = _send(incident_id, key, versionless)
    assert exact_replay.status_code == 202
    assert exact_replay.json() == approved.json()
    with psycopg.connect(DATABASE_URL) as connection:
        state = connection.execute(
            "SELECT state FROM incident.incidents WHERE incident_id = %s", (incident_id,)
        ).fetchone()[0]
        state["state"] = "mitigating"
        state["mitigation_strategy"]["mitigation_id"] = "mit_legacy_v3"
        state["mitigation_strategy"]["approval_status"] = "pending"
        run_state = connection.execute(
            "SELECT state FROM incident.runs WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
        run_state["current_state"] = "mitigating"
        run_state["status"] = "awaiting_human"
        run_state["pending_command"] = "approve_mitigation"
        connection.execute(
            "UPDATE incident.incidents SET state = %s::jsonb, version = version + 1 "
            "WHERE incident_id = %s",
            (json.dumps(state), incident_id),
        )
        connection.execute(
            "UPDATE incident.runs SET state = %s::jsonb, version = version + 1 WHERE run_id = %s",
            (json.dumps(run_state), run_id),
        )

    stale_replay = _send(incident_id, key, versionless)
    assert stale_replay.status_code == 202
    assert stale_replay.json() == approved.json()
    changed_versionless = _body(comment="changed legacy retry")
    changed_versionless.pop("expected_incident_version")
    changed_payload = _send(incident_id, key, changed_versionless)
    assert changed_payload.status_code == 409
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state->>'state', state->'mitigation_strategy'->>'mitigation_id', "
            "state->'mitigation_strategy'->>'approval_status', version FROM incident.incidents "
            "WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM incident.run_events WHERE incident_id = %s), "
            "(SELECT count(*) FROM incident.decisions WHERE incident_id = %s)",
            (incident_id, incident_id),
        ).fetchone()
        run_after = connection.execute(
            "SELECT state->>'current_state', state->>'status', state->>'pending_command', version "
            "FROM incident.runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
    assert row == ("mitigating", "mit_legacy_v3", "pending", 2)
    assert counts == (1, 1)
    assert run_after == ("mitigating", "awaiting_human", "approve_mitigation", 2)


def test_a_retried_command_returns_the_same_state_and_decides_once() -> None:
    _mitigating("inc-b3-retry")
    first = _send("inc-b3-retry", "key-retry-0000001", _body())
    again = _send("inc-b3-retry", "key-retry-0000001", _body())
    assert (first.status_code, again.status_code) == (202, 202)
    assert first.json() == again.json()
    conflicting = _send("inc-b3-retry", "key-retry-0000001", _body(comment="another request"))
    assert conflicting.status_code == 409
    changed_revision = _send(
        "inc-b3-retry",
        "key-retry-0000001",
        _body(expected_incident_version=1),
    )
    assert changed_revision.status_code == 409
    with psycopg.connect(DATABASE_URL) as connection:
        count = connection.execute(
            "SELECT count(*) FROM incident.run_events WHERE run_id = %s", (RUNS["inc-b3-retry"],)
        ).fetchone()
    assert count == (1,)
