"""Issue #23 C2b: triage commands over real HTTP on real PostgreSQL."""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import sql

from sre_agent.application import create_application
from sre_agent.investigator.contract import InvestigationRequest
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
REASON = "Sustained 5xx spike on checkout."
IMPACT = "Checkout requests failed for customers."
ALERT_CONTEXT = {
    "service": "checkout",
    "summary": "Elevated checkout failures were observed.",
    "observed_at": "2026-10-07T10:30:00-05:00",
    "source": "operator-confirmed-monitoring",
    "severity": "sev2",
}
BEARERS: dict[str, str] = {}
ROOT = Path(__file__).parents[1]
STATE_VALIDATOR = Draft202012Validator(
    yaml.safe_load((ROOT / "agent" / "schemas" / "triage-state.schema.yaml").read_text())
)
INCIDENT_STATE_VALIDATOR = Draft202012Validator(
    yaml.safe_load((ROOT / "agent" / "schemas" / "incident-state.schema.yaml").read_text()),
    format_checker=FormatChecker(),
)


@pytest.fixture(scope="module", autouse=True)
def triage_http_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_reservations, consumption_limit_policies, "
            "bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, resources, alert_triage, "
            "principals, idempotency_records, mcp_tools, mcp_servers, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('op-human','human','Operator','active',now(),now()),"
            "('reader-human','human','Reader','active',now(),now()),"
            "('bystander-human','human','Bystander','active',now(),now()),"
            "('producer-agent','agent','External producer','active',now(),now()),"
            "('producer-limited','agent','Limited producer','active',now(),now()),"
            "('context-human','human','Context operator','active',now(),now()),"
            "('context-revocable','human','Revocable operator','active',now(),now()),"
            "('eligible-linker','human','Eligible incident reader','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at,"
            " owner_id, source, source_ref, display_name, visibility, description,"
            " tags) VALUES ('incident_workflow','incident-response','active',now(),"
            " 'papiarcacamilo','incident_workflow','incident-response@1.0.0',"
            " 'Incident response workflow','private','','[]')"
        )
        connection.execute(
            "INSERT INTO incident.incidents (incident_id, state, version, created_at,"
            " updated_at) VALUES ('inc-http-target',"
            " jsonb_build_object('state', CAST('active' AS text)), 1, now(), now())"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> None:
        async with database.transaction() as session:
            creds = CredentialRepository(session)
            issued_op = await creds.issue("op-human")
            issued_reader = await creds.issue("reader-human")
            issued_by = await creds.issue("bystander-human")
            issued_agent = await creds.issue("producer-agent")
            issued_limited = await creds.issue("producer-limited")
            issued_context_human = await creds.issue("context-human")
            issued_context_revocable = await creds.issue("context-revocable")
            issued_eligible_linker = await creds.issue("eligible-linker")
            grants = GrantRepository(session)
            for index, action in enumerate(
                ("alert.triage", "alert.dismiss", "alert.associate", "run.read", "incident.declare")
            ):
                await grants.create(
                    f"grant-op-human-{index}",
                    "op-human",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
            await grants.create(
                "grant-reader-human-0",
                "reader-human",
                "alert.read",
                "incident_workflow",
                "incident-response",
            )
            for index, action in enumerate(
                (
                    "alert.triage",
                    "alert.dismiss",
                    "alert.associate",
                    "run.read",
                    "incident.declare",
                )
            ):
                await grants.create(
                    f"grant-producer-agent-{index}",
                    "producer-agent",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
            for index, action in enumerate(("alert.dismiss", "run.read")):
                await grants.create(
                    f"grant-producer-limited-{index}",
                    "producer-limited",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
            for index, action in enumerate(
                (
                    "alert.read",
                    "alert.triage",
                    "alert.dismiss",
                    "alert.associate",
                    "run.read",
                    "incident.declare",
                )
            ):
                await grants.create(
                    f"grant-context-human-{index}",
                    "context-human",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
            for index, action in enumerate(("alert.read", "alert.dismiss")):
                await grants.create(
                    f"grant-context-revocable-{index}",
                    "context-revocable",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
            await grants.create(
                "grant-producer-agent-read",
                "producer-agent",
                "alert.read",
                "incident_workflow",
                "incident-response",
            )
            await grants.create(
                "grant-producer-limited-read",
                "producer-limited",
                "alert.read",
                "incident_workflow",
                "incident-response",
            )
            await grants.create(
                "grant-eligible-linker-alert-read",
                "eligible-linker",
                "alert.read",
                "incident_workflow",
                "incident-response",
            )
            await grants.create(
                "grant-eligible-linker-run-read",
                "eligible-linker",
                "run.read",
                "incident_workflow",
                "incident-response",
            )
        BEARERS["op"] = f"Bearer {issued_op.key}"
        BEARERS["reader"] = f"Bearer {issued_reader.key}"
        BEARERS["bystander"] = f"Bearer {issued_by.key}"
        BEARERS["agent"] = f"Bearer {issued_agent.key}"
        BEARERS["limited_agent"] = f"Bearer {issued_limited.key}"
        BEARERS["context_human"] = f"Bearer {issued_context_human.key}"
        BEARERS["context_revocable"] = f"Bearer {issued_context_revocable.key}"
        BEARERS["eligible_linker"] = f"Bearer {issued_eligible_linker.key}"

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client(url: str = DATABASE_URL) -> TestClient:
    return TestClient(create_application(Settings(url)))


def _cmd(operation: str, version: int = 1, **kwargs) -> dict:
    if operation == "triage_declare":
        kwargs.setdefault("impact", IMPACT)
        kwargs.setdefault("alert_context", dict(ALERT_CONTEXT))
    return {"operation": operation, "expected_version": version, **kwargs}


def _post(
    client: TestClient,
    alert_id: str,
    body: dict | None,
    key: str | None,
    bearer: str | None,
    raw: bytes | None = None,
):
    headers: dict[str, str] = {}
    if bearer is not None:
        headers["Authorization"] = bearer
    if key is not None:
        headers["Idempotency-Key"] = key
    path = f"/v1/alerts/{alert_id}/triage/commands"
    if raw is not None:
        headers["Content-Type"] = "application/json"
        return client.post(path, content=raw, headers=headers)
    return client.post(path, json=body, headers=headers)


def _incident_count() -> int:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        return int(connection.execute("SELECT count(*) FROM incident.incidents").fetchone()[0])


def _count_rows(table: str) -> int:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def test_open_dismiss_link_are_200() -> None:
    client, bearer = _client(), BEARERS["op"]
    opened = _post(client, "aho", _cmd("open_triage"), "k-open-123456789012", bearer)
    assert opened.status_code == 200
    assert (opened.json()["status"], opened.json()["alert_id"]) == ("open", "aho")
    dismissed = _post(
        client, "aho", _cmd("triage_dismiss", reason=REASON), "k-dismiss-12345678", bearer
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    linked = _post(
        client,
        "ahl",
        _cmd("triage_link", reason=REASON, target_incident_id="inc-http-target"),
        "k-link-12345678901",
        bearer,
    )
    assert linked.status_code == 200
    assert linked.json()["incident_id"] == "inc-http-target"


def test_declare_is_201_with_contract_shape() -> None:
    response = _post(
        _client(),
        "ahd",
        _cmd("triage_declare", reason=REASON, severity="sev2"),
        "k-declare-1234567890",
        BEARERS["op"],
    )
    assert response.status_code == 201
    body = response.json()
    assert STATE_VALIDATOR.is_valid(body), body
    assert (body["status"], body["alert_id"], body["actor"]) == ("declared", "ahd", "op-human")
    assert isinstance(body["incident_id"], str) and isinstance(body["decided_at"], str)


def test_declare_replay_returns_original_without_second_incident() -> None:
    client = _client()
    body = _cmd("triage_declare", reason=REASON, severity="sev1")
    before = _incident_count()
    first = _post(client, "ahr", body, "k-replay-12345678901", BEARERS["op"])
    assert first.status_code == 201
    assert _incident_count() == before + 1
    second = _post(client, "ahr", body, "k-replay-12345678901", BEARERS["op"])
    assert second.status_code == 201
    assert second.json()["incident_id"] == first.json()["incident_id"]
    assert second.json()["expected_version"] == first.json()["expected_version"]
    assert _incident_count() == before + 1


def test_declare_persists_operator_impact_through_http_state_event_and_replay() -> None:
    client, alert_id = _client(), "al-impact-http"
    prefix = "Customer checkout remained unavailable. "
    impact = prefix + "x" * (2000 - len(prefix))
    assert len(impact) == 2000
    # Incident severity is the operator's decision and remains separate from
    # the confirmed severity of the source alert.
    body = _cmd("triage_declare", reason=REASON, severity="sev1", impact=impact)
    before = _incident_count()
    first = _post(client, alert_id, body, "k-impact-http-123456", BEARERS["op"])
    assert first.status_code == 201
    result = first.json()
    assert (result["decision_origin"], result["responsible_system"]) == ("manual", None)
    assert _incident_count() == before + 1

    state = _get(client, alert_id, BEARERS["reader"])
    assert state.status_code == 200
    assert state.json()["incident_id"] == result["incident_id"]
    assert (state.json()["decision_origin"], state.json()["responsible_system"]) == (
        "manual",
        None,
    )
    detail = client.get(
        f"/v1/incidents/{result['incident_id']}", headers={"Authorization": BEARERS["op"]}
    )
    assert detail.status_code == 200
    assert detail.json()["impact"] == impact

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        incident = connection.execute(
            "SELECT state FROM incident.incidents WHERE incident_id=%s",
            (result["incident_id"],),
        ).fetchone()
        event = connection.execute(
            "SELECT payload->'incident_state' FROM incident.run_events "
            "WHERE incident_id=%s ORDER BY sequence LIMIT 1",
            (result["incident_id"],),
        ).fetchone()
        snapshot = connection.execute(
            "SELECT incident_state FROM incident.snapshots WHERE incident_id=%s "
            "ORDER BY version LIMIT 1",
            (result["incident_id"],),
        ).fetchone()
        run_id = connection.execute(
            "SELECT run_id FROM incident.runs WHERE incident_id=%s", (result["incident_id"],)
        ).fetchone()[0]
        event_count = connection.execute(
            "SELECT count(*) FROM incident.run_events WHERE incident_id=%s",
            (result["incident_id"],),
        ).fetchone()[0]
    assert incident[0]["impact"] == impact
    assert event[0]["impact"] == impact
    assert snapshot is not None
    for aggregate in (incident[0], event[0], snapshot[0]):
        assert aggregate["alert"] == {
            "alert_id": alert_id,
            **ALERT_CONTEXT,
            "status": "triaged",
        }
        assert INCIDENT_STATE_VALIDATOR.is_valid(aggregate), aggregate
        assert aggregate["severity"] == "sev1"
        assert aggregate["alert"]["severity"] == "sev2"
        InvestigationRequest.model_validate(
            {
                "incident_id": result["incident_id"],
                "run_id": run_id,
                "objective": "investigate",
                "context": {
                    "incident_id": result["incident_id"],
                    "state": "investigating",
                    "alert": aggregate["alert"],
                },
            }
        )
    assert event_count == 1

    replay = _post(client, alert_id, body, "k-impact-http-123456", BEARERS["op"])
    assert replay.status_code == 201
    assert replay.json() == result
    assert _incident_count() == before + 1
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM incident.run_events WHERE incident_id=%s",
            (result["incident_id"],),
        ).fetchone() == (1,)


@pytest.mark.parametrize(
    ("impact", "include_impact", "status", "code"),
    [
        (None, False, 422, "invalid_impact"),
        (None, True, 422, "invalid_impact"),
        (7, True, 400, "invalid_command"),
        ("", True, 422, "invalid_impact"),
        (" \t\n ", True, 422, "invalid_impact"),
        ("x" * 2001, True, 422, "invalid_impact"),
    ],
)
def test_invalid_impact_is_rejected_without_persisting_decision_or_incident(
    impact, include_impact: bool, status: int, code: str
) -> None:
    client = _client()
    alert_id = f"al-bad-impact-{status}-{code}-{int(include_impact)}"
    body = _cmd("triage_declare", reason=REASON, severity="sev2")
    if include_impact:
        body["impact"] = impact
    else:
        body.pop("impact")
    incidents_before = _incident_count()
    triage_before = _count_rows("alert_triage")
    events_before = _count_rows("incident.run_events")

    response = _post(client, alert_id, body, f"k-bad-impact-{status}-{code}-1234", BEARERS["op"])

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert _incident_count() == incidents_before
    assert _count_rows("alert_triage") == triage_before
    assert _count_rows("incident.run_events") == events_before
    assert _get(client, alert_id, BEARERS["reader"]).status_code == 404


@pytest.mark.parametrize(
    ("seed_operation", "seed_body", "rewrite_operation", "rewrite_body", "terminal_status"),
    [
        (
            "triage_declare",
            {"reason": REASON, "severity": "sev2"},
            "triage_dismiss",
            {"reason": REASON},
            "declared",
        ),
        (
            "triage_dismiss",
            {"reason": REASON},
            "triage_declare",
            {"reason": REASON, "severity": "sev2"},
            "dismissed",
        ),
        (
            "triage_link",
            {"reason": REASON, "target_incident_id": "inc-http-target"},
            "triage_declare",
            {"reason": REASON, "severity": "sev2"},
            "linked",
        ),
    ],
)
def test_terminal_decision_cannot_be_rewritten(
    seed_operation: str,
    seed_body: dict,
    rewrite_operation: str,
    rewrite_body: dict,
    terminal_status: str,
) -> None:
    client, alert_id = _client(), f"al-terminal-{terminal_status}"
    seed_key = f"k-terminal-seed-{terminal_status}-123"
    seed = _post(client, alert_id, _cmd(seed_operation, **seed_body), seed_key, BEARERS["op"])
    assert seed.status_code == (201 if seed_operation == "triage_declare" else 200)
    before_rewrite = _incident_count()

    rewrite = _post(
        client,
        alert_id,
        _cmd(rewrite_operation, version=seed.json()["expected_version"], **rewrite_body),
        f"k-terminal-rewrite-{terminal_status}-123",
        BEARERS["op"],
    )

    assert rewrite.status_code == 409
    assert rewrite.json()["error"]["code"] == "terminal_decision"
    assert _incident_count() == before_rewrite
    state = _get(client, alert_id, BEARERS["reader"])
    assert state.status_code == 200
    assert (state.json()["status"], state.json()["expected_version"]) == (
        terminal_status,
        seed.json()["expected_version"],
    )
    assert state.json()["incident_id"] == seed.json()["incident_id"]

    if seed_operation == "triage_declare":
        replay = _post(client, alert_id, _cmd(seed_operation, **seed_body), seed_key, BEARERS["op"])
        assert replay.status_code == 201
        assert replay.json() == seed.json()


def test_declared_alert_keeps_existing_fresh_declare_conflict() -> None:
    client, alert_id = _client(), "al-terminal-double-declare"
    first = _post(
        client,
        alert_id,
        _cmd("triage_declare", reason=REASON, severity="sev2"),
        "k-terminal-first-12345",
        BEARERS["op"],
    )
    assert first.status_code == 201
    duplicate = _post(
        client,
        alert_id,
        _cmd("triage_declare", reason=REASON, severity="sev2"),
        "k-terminal-next-123456",
        BEARERS["op"],
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "already_declared"


@pytest.mark.parametrize(
    ("operation", "body"),
    [
        ("open_triage", {}),
        ("triage_declare", {"reason": REASON, "severity": "sev2"}),
    ],
)
def test_agent_grants_cannot_authorize_human_only_terminal_triage(
    operation: str, body: dict
) -> None:
    """Action grants do not turn an agent credential into a human operator."""
    client = _client()
    alert_id = f"al-agent-{operation.removeprefix('triage_')}"
    incidents_before = _incident_count()
    triage_before = _count_rows("alert_triage")
    events_before = _count_rows("incident.run_events")

    response = _post(
        client,
        alert_id,
        _cmd(operation, **body),
        f"k-agent-{operation.removeprefix('triage_')}-123456789",
        BEARERS["agent"],
    )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "operator_required"
    assert _incident_count() == incidents_before
    assert _count_rows("alert_triage") == triage_before
    assert _count_rows("incident.run_events") == events_before
    assert _get(client, alert_id, BEARERS["reader"]).status_code == 404


@pytest.mark.parametrize(
    ("operation", "body", "expected_incident_id"),
    [
        ("triage_dismiss", {"reason": REASON}, None),
        (
            "triage_link",
            {"reason": REASON, "target_incident_id": "inc-http-target"},
            "inc-http-target",
        ),
    ],
)
def test_authorized_external_producer_decision_persists_and_replays_provenance(
    operation: str, body: dict, expected_incident_id: str | None
) -> None:
    client = _client()
    alert_id = f"al-external-{operation.removeprefix('triage_')}"
    key = f"k-external-{operation.removeprefix('triage_')}-123456789"
    incidents_before = _incident_count()
    events_before = _count_rows("incident.run_events")
    response = _post(client, alert_id, _cmd(operation, **body), key, BEARERS["agent"])

    assert response.status_code == 200, response.text
    first = response.json()
    assert (first["decision_origin"], first["responsible_system"]) == (
        "external_automatic",
        "producer-agent",
    )
    assert first["incident_id"] == expected_incident_id
    state = _get(client, alert_id, BEARERS["reader"])
    assert state.status_code == 200
    assert state.json() == first
    replay = _post(client, alert_id, _cmd(operation, **body), key, BEARERS["agent"])
    assert replay.status_code == 200
    assert replay.json() == first
    assert _incident_count() == incidents_before
    assert _count_rows("incident.run_events") == events_before


@pytest.mark.parametrize(
    ("operation", "owner", "other", "expected_actor", "origin", "responsible_system"),
    [
        ("triage_dismiss", "op", "agent", "op-human", "manual", None),
        (
            "triage_dismiss",
            "agent",
            "op",
            "producer-agent",
            "external_automatic",
            "producer-agent",
        ),
        ("triage_declare", "op", "context_human", "op-human", "manual", None),
    ],
)
def test_idempotency_binding_is_owned_by_the_original_principal(
    operation: str,
    owner: str,
    other: str,
    expected_actor: str,
    origin: str,
    responsible_system: str | None,
) -> None:
    client = _client()
    alert_id = f"al-owner-bound-{operation}-{owner}-{other}"
    key = f"k-owner-bound-{operation}-{owner}-{other}-123456789"
    if operation == "triage_declare":
        body = _cmd(operation, reason=REASON, severity="sev2")
    else:
        body = _cmd(operation, reason=REASON)

    def database_snapshot() -> tuple[object, ...]:
        with psycopg.connect(DATABASE_URL) as connection:
            triage = connection.execute(
                "SELECT status, incident_id, expected_version, actor, decision_origin, "
                "responsible_system FROM alert_triage WHERE alert_id=%s",
                (alert_id,),
            ).fetchone()
            binding = connection.execute(
                "SELECT principal_id, payload_sha256, outcome, transition_count "
                "FROM idempotency_records WHERE scope=%s",
                (f"triage:{alert_id}",),
            ).fetchone()
            event_count = connection.execute("SELECT count(*) FROM incident.run_events").fetchone()[
                0
            ]
            incident_count = connection.execute(
                "SELECT count(*) FROM incident.incidents"
            ).fetchone()[0]
        return triage, binding, event_count, incident_count

    first = _post(client, alert_id, body, key, BEARERS[owner])
    assert first.status_code == (201 if operation == "triage_declare" else 200), first.text
    original = first.json()
    assert (original["actor"], original["decision_origin"], original["responsible_system"]) == (
        expected_actor,
        origin,
        responsible_system,
    )
    after_first = database_snapshot()
    assert after_first[0][3:] == (expected_actor, origin, responsible_system)
    assert after_first[1][0] == expected_actor
    stored_outcome = after_first[1][2]["response_payload"]
    assert (
        stored_outcome["actor"],
        stored_outcome["decision_origin"],
        stored_outcome["responsible_system"],
    ) == (
        expected_actor,
        origin,
        responsible_system,
    )
    assert stored_outcome["incident_id"] == original["incident_id"]

    foreign_replay = _post(client, alert_id, body, key, BEARERS[other])
    assert foreign_replay.status_code == 409, foreign_replay.text
    assert foreign_replay.json()["error"]["code"] == "idempotency_conflict"
    assert database_snapshot() == after_first

    owner_replay = _post(client, alert_id, body, key, BEARERS[owner])
    assert owner_replay.status_code == first.status_code
    assert owner_replay.json() == original
    assert database_snapshot() == after_first


def test_external_producer_without_exact_association_grant_has_no_effect() -> None:
    client, alert_id = _client(), "al-external-no-associate"
    before = (_incident_count(), _count_rows("alert_triage"), _count_rows("incident.run_events"))
    response = _post(
        client,
        alert_id,
        _cmd("triage_link", reason=REASON, target_incident_id="inc-http-target"),
        "k-external-no-associate-12345",
        BEARERS["limited_agent"],
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authorized"
    assert (
        _incident_count(),
        _count_rows("alert_triage"),
        _count_rows("incident.run_events"),
    ) == before
    assert _get(client, alert_id, BEARERS["reader"]).status_code == 404


def test_request_cannot_forge_decision_origin_or_responsible_system() -> None:
    client, alert_id = _client(), "al-forged-origin"
    before = (_incident_count(), _count_rows("alert_triage"), _count_rows("incident.run_events"))
    response = _post(
        client,
        alert_id,
        _cmd(
            "triage_dismiss",
            reason=REASON,
            decision_origin="manual",
            responsible_system="forged-system",
        ),
        "k-forged-origin-12345678",
        BEARERS["agent"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert (
        _incident_count(),
        _count_rows("alert_triage"),
        _count_rows("incident.run_events"),
    ) == before
    assert _get(client, alert_id, BEARERS["reader"]).status_code == 404


def test_legacy_state_and_replay_report_unknown_without_actor_inference() -> None:
    client = _client()
    legacy_alert_id = "al-legacy-producer"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO alert_triage (alert_id,status,incident_id,expected_version,reason,"
            "severity,actor,decided_at) VALUES "
            "(%s,'dismissed',NULL,1,%s,NULL,'producer-agent',now())",
            (legacy_alert_id, REASON),
        )
    legacy = _get(client, legacy_alert_id, BEARERS["reader"])
    assert legacy.status_code == 200
    assert (
        legacy.json()["actor"],
        legacy.json()["decision_origin"],
        legacy.json()["responsible_system"],
    ) == ("producer-agent", "unknown", None)

    alert_id, key = "al-legacy-replay", "k-legacy-replay-123456789"
    body = _cmd("triage_dismiss", reason=REASON)
    first = _post(client, alert_id, body, key, BEARERS["agent"])
    assert first.status_code == 200
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE idempotency_records SET outcome=jsonb_set(outcome,'{response_payload}',"
            "(outcome->'response_payload')-'decision_origin'-'responsible_system') "
            "WHERE scope=%s",
            (f"triage:{alert_id}",),
        )
    replay = _post(client, alert_id, body, key, BEARERS["agent"])
    assert replay.status_code == 200
    assert (
        replay.json()["actor"],
        replay.json()["decision_origin"],
        replay.json()["responsible_system"],
    ) == ("producer-agent", "unknown", None)


def test_unauthenticated_is_401() -> None:
    client = _client()
    body = _cmd("open_triage")
    missing = _post(client, "al-http-401", body, "k-http-401-1234567890", None)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_failed"
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    bad = _post(
        client, "al-http-401", body, "k-http-401-1234567890", "Bearer sre_admn_0123456789abcdefghij"
    )
    assert bad.status_code == 401


def test_forbidden_hides_existence() -> None:
    client = _client()
    for alert_id in ("al-http-ghost-one", "al-http-ghost-two"):
        response = _post(
            client, alert_id, _cmd("open_triage"), "k-http-403-1234567890", BEARERS["bystander"]
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_authorized"
        assert alert_id not in response.text
        assert REASON not in response.text


def test_status_table() -> None:
    client, bearer = _client(), BEARERS["op"]
    open_v1 = _cmd("open_triage")
    dec = {"reason": REASON, "severity": "sev2", "impact": IMPACT}
    V, S, N = "validation_error", "stale_version", "incident_not_found"
    nosev = _cmd("triage_declare", reason=REASON)
    sev9 = _cmd("triage_declare", reason=REASON, severity="sev9")
    nolink = _cmd("triage_link", reason=REASON, target_incident_id="inc-absent")
    oplist = {"operation": ["triage_dismiss"], "expected_version": 1, "reason": REASON}
    opint = {"operation": 7, "expected_version": 1}
    nover = {"operation": "open_triage"}
    strver = {"operation": "open_triage", "expected_version": "1"}
    cases = [
        ("ahk", open_v1, None, None, 400, "invalid_idempotency_key"),
        ("ahk", open_v1, "short", None, 400, "invalid_idempotency_key"),
        ("ahk", None, "k-malformed-123456", b"{not json", 400, "invalid_command"),
        ("ahk", _cmd("nope"), "k-unknown-123456789", None, 422, V),
        ("ahk", oplist, "k-oplist-12345678901", None, 422, V),
        ("ahk", opint, "k-opint-123456789012", None, 422, V),
        ("ahk", ["open_triage"], "k-bodylist-123456789", None, 422, V),
        ("ahk", nover, "k-nover-123456789012", None, 400, "invalid_command"),
        ("ahk", strver, "k-strver-12345678901", None, 400, "invalid_command"),
        (
            "ahk",
            {"operation": "triage_dismiss", "expected_version": 1, "reason": ["reason"]},
            "k-reasonlist-1234567",
            None,
            400,
            "invalid_command",
        ),
        (
            "ahk",
            {"operation": "triage_dismiss", "expected_version": 1, "reason": 7},
            "k-reasonint-12345678",
            None,
            400,
            "invalid_command",
        ),
        (
            "ahk",
            {
                "operation": "triage_link",
                "expected_version": 1,
                "reason": REASON,
                "target_incident_id": 7,
            },
            "k-targetint-12345678",
            None,
            400,
            "invalid_command",
        ),
        (
            "ahk",
            {
                "operation": "triage_declare",
                "expected_version": 1,
                "reason": REASON,
                "severity": 2,
            },
            "k-sevint-12345678901",
            None,
            400,
            "invalid_command",
        ),
        (
            "ahk",
            {
                "operation": "triage_declare",
                "expected_version": 1,
                "reason": REASON,
                "severity": ["sev2"],
            },
            "k-sevlist-1234567890",
            None,
            400,
            "invalid_command",
        ),
        ("ahk", nosev, "k-nosev-12345678901", None, 422, "invalid_severity"),
        ("ahk", sev9, "k-sev9-12345678901", None, 422, "invalid_severity"),
        ("ahs", _cmd("triage_declare", version=2, **dec), "k-stale-12345678901", None, 409, S),
        (
            "al-no-context",
            {
                "operation": "triage_declare",
                "expected_version": 1,
                "reason": REASON,
                "severity": "sev2",
                "impact": IMPACT,
            },
            "k-alert-context-missing-123",
            None,
            422,
            "invalid_alert_context",
        ),
        (
            "ahi",
            _cmd("triage_declare", **(dec | {"impact": ""})),
            "k-impact-123456789",
            None,
            422,
            "invalid_impact",
        ),
        ("ahn", nolink, "k-404-1234567890123", None, 404, N),
        ("BAD ID!", open_v1, "k-badid-12345678901", None, 400, "invalid_command"),
    ]
    for alert_id, body, key, raw, status, code in cases:
        response = _post(client, alert_id, body, key, bearer, raw=raw)
        assert response.status_code == status, (alert_id, body)
        assert response.json()["error"]["code"] == code, (alert_id, body)


@pytest.mark.parametrize(
    "field,value",
    [
        ("service", ""),
        ("service", ["checkout"]),
        ("service", "x" * 201),
        ("summary", " \t "),
        ("summary", 42),
        ("summary", "x" * 2001),
        ("observed_at", "not-a-date"),
        ("observed_at", "2026-10-07T10:30:00"),
        ("observed_at", None),
        ("source", ""),
        ("source", ["monitor"]),
        ("source", "x" * 201),
        ("severity", "critical"),
        ("severity", None),
    ],
    ids=[
        "blank-service",
        "wrong-type-service",
        "long-service",
        "blank-summary",
        "wrong-type-summary",
        "long-summary",
        "invalid-date",
        "naive-date",
        "missing-date",
        "blank-source",
        "wrong-type-source",
        "long-source",
        "unknown-severity",
        "null-severity",
    ],
)
def test_declare_rejects_invalid_alert_context_without_persisting(field, value) -> None:
    client = _client()
    alert_id = f"al-invalid-context-{field.replace('_', '-')}-{len(str(value))}"
    body = _cmd("triage_declare", reason=REASON, severity="sev3")
    body["alert_context"][field] = value
    before = _triage_write_counts(alert_id)
    response = _post(
        client,
        alert_id,
        body,
        f"k-invalid-context-{field}-{len(str(value))}-123456",
        BEARERS["op"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_alert_context"
    assert _triage_write_counts(alert_id) == before


@pytest.mark.parametrize(
    "mutation", ["missing-field", "wrong-container"], ids=["missing-field", "wrong-container"]
)
def test_declare_rejects_incomplete_alert_context_without_persisting(mutation: str) -> None:
    alert_id = f"al-invalid-context-{mutation}"
    body = _cmd("triage_declare", reason=REASON, severity="sev3")
    if mutation == "missing-field":
        del body["alert_context"]["summary"]
    else:
        body["alert_context"] = [ALERT_CONTEXT]
    before = _triage_write_counts(alert_id)
    response = _post(
        _client(), alert_id, body, f"k-invalid-context-{mutation}-123456", BEARERS["op"]
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_alert_context"
    assert _triage_write_counts(alert_id) == before


def test_declare_rejects_extra_alert_context_property_without_persisting() -> None:
    alert_id = "al-invalid-context-extra"
    body = _cmd("triage_declare", reason=REASON, severity="sev3")
    body["alert_context"]["detector_guess"] = "critical"
    before = _triage_write_counts(alert_id)
    response = _post(_client(), alert_id, body, "k-invalid-context-extra-123456", BEARERS["op"])
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_alert_context"
    assert _triage_write_counts(alert_id) == before


def test_declare_requires_alert_context_without_persisting() -> None:
    alert_id = "al-missing-alert-context-no-write"
    body = {
        "operation": "triage_declare",
        "expected_version": 1,
        "reason": REASON,
        "severity": "sev2",
        "impact": IMPACT,
    }
    before = _triage_write_counts(alert_id)
    response = _post(_client(), alert_id, body, "k-missing-alert-context-123456", BEARERS["op"])
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_alert_context"
    assert _triage_write_counts(alert_id) == before


def test_changed_alert_context_with_same_idempotency_key_conflicts_without_mutation() -> None:
    client, alert_id = _client(), "al-context-idempotency-binding"
    key = "k-context-idempotency-binding-123456"
    body = _cmd("triage_declare", reason=REASON, severity="sev1")
    first = _post(client, alert_id, body, key, BEARERS["op"])
    assert first.status_code == 201, first.text
    after_first = _triage_write_counts(alert_id)
    changed = _cmd("triage_declare", reason=REASON, severity="sev1")
    changed["alert_context"]["summary"] = "A different operator-confirmed alert summary."
    replay = _post(client, alert_id, changed, key, BEARERS["op"])
    assert replay.status_code == 409, replay.text
    assert replay.json()["error"]["code"] == "idempotency_conflict"
    assert _triage_write_counts(alert_id) == after_first
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        state = connection.execute(
            "SELECT state->'alert' FROM incident.incidents WHERE incident_id=%s",
            (first.json()["incident_id"],),
        ).fetchone()[0]
    assert state["summary"] == ALERT_CONTEXT["summary"]


def _triage_write_counts(alert_id: str) -> tuple[int, int, int, int, int]:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        return (
            connection.execute(
                "SELECT count(*) FROM alert_triage WHERE alert_id=%s", (alert_id,)
            ).fetchone()[0],
            connection.execute("SELECT count(*) FROM incident.incidents").fetchone()[0],
            connection.execute("SELECT count(*) FROM incident.run_events").fetchone()[0],
            connection.execute("SELECT count(*) FROM incident.snapshots").fetchone()[0],
            connection.execute(
                "SELECT count(*) FROM idempotency_records WHERE scope=%s",
                (f"triage:{alert_id}",),
            ).fetchone()[0],
        )


def test_storage_outage_is_503() -> None:
    client = _client("postgresql://postgres:postgres@127.0.0.1:1/postgres")
    response = _post(
        client,
        "al-http-down",
        _cmd("open_triage"),
        "k-http-down-1234567890",
        "Bearer sre_admn_0123456789abcdefghij",
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert response.headers["Retry-After"] == "5"


def _get(client: TestClient, alert_id: str, bearer: str | None):
    headers = {} if bearer is None else {"Authorization": bearer}
    return client.get(f"/v1/alerts/{alert_id}/triage", headers=headers)


def _get_context(client: TestClient, alert_id: str, bearer: str | None):
    headers = {} if bearer is None else {"Authorization": bearer}
    return client.get(f"/v1/alerts/{alert_id}/triage/context", headers=headers)


def _get_eligible_incidents(client: TestClient, alert_id: str, bearer: str | None):
    headers = {} if bearer is None else {"Authorization": bearer}
    return client.get(f"/v1/alerts/{alert_id}/triage/eligible-incidents", headers=headers)


def test_context_read_only_principal_gets_empty_actions_and_null_state_without_effects() -> None:
    client, alert_id = _client(), "al-context-reader-only"
    before = (
        _incident_count(),
        _count_rows("alert_triage"),
        _count_rows("incident.run_events"),
        _count_rows("idempotency_records"),
    )
    response = _get_context(client, alert_id, BEARERS["reader"])
    assert response.status_code == 200, response.text
    assert response.json() == {"alert_id": alert_id, "triage_state": None, "allowed_actions": []}
    assert (
        _incident_count(),
        _count_rows("alert_triage"),
        _count_rows("incident.run_events"),
        _count_rows("idempotency_records"),
    ) == before


@pytest.mark.parametrize(
    ("bearer_name", "expected_actions"),
    [
        (
            "context_human",
            ["open_triage", "triage_dismiss", "triage_link", "triage_declare"],
        ),
        ("agent", ["triage_dismiss", "triage_link"]),
        ("limited_agent", ["triage_dismiss"]),
        ("reader", []),
    ],
)
def test_context_projects_exact_policy_actions_for_humans_agents_and_readers(
    bearer_name: str, expected_actions: list[str]
) -> None:
    alert_id = f"al-context-{bearer_name}"
    response = _get_context(_client(), alert_id, BEARERS[bearer_name])
    assert response.status_code == 200, response.text
    assert response.json() == {
        "alert_id": alert_id,
        "triage_state": None,
        "allowed_actions": expected_actions,
    }


def test_context_refreshes_state_and_hides_all_fresh_actions_after_terminal_decision() -> None:
    client, alert_id = _client(), "al-context-terminal"
    opened = _post(
        client,
        alert_id,
        _cmd("open_triage"),
        "k-context-open-123456789",
        BEARERS["context_human"],
    )
    assert opened.status_code == 200
    current = _get_context(client, alert_id, BEARERS["context_human"])
    assert current.status_code == 200
    assert current.json()["triage_state"]["status"] == "open"
    assert current.json()["allowed_actions"] == [
        "open_triage",
        "triage_dismiss",
        "triage_link",
        "triage_declare",
    ]
    dismissed = _post(
        client,
        alert_id,
        _cmd("triage_dismiss", version=1, reason=REASON),
        "k-context-dismiss-1234567",
        BEARERS["context_human"],
    )
    assert dismissed.status_code == 200
    terminal = _get_context(client, alert_id, BEARERS["context_human"])
    assert terminal.status_code == 200
    assert terminal.json()["triage_state"]["status"] == "dismissed"
    assert terminal.json()["allowed_actions"] == []


def test_context_requires_read_grant_before_known_or_unknown_state_lookup() -> None:
    client, alert_id = _client(), "al-context-protected"
    opened = _post(
        client,
        alert_id,
        _cmd("open_triage"),
        "k-context-protect-12345",
        BEARERS["context_human"],
    )
    assert opened.status_code == 200
    for requested_id in (alert_id, "al-context-absent"):
        response = _get_context(client, requested_id, BEARERS["op"])
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_authorized"
        assert "triage_state" not in response.json()


def test_context_rejects_malformed_alert_identifier() -> None:
    response = _get_context(_client(), "BAD ID!", BEARERS["reader"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_command"


def test_post_revalidates_grant_revoked_after_context_projection() -> None:
    client, alert_id = _client(), "al-context-revoked"
    projected = _get_context(client, alert_id, BEARERS["context_revocable"])
    assert projected.status_code == 200
    assert projected.json()["allowed_actions"] == ["triage_dismiss"]
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE grants SET status='revoked' WHERE principal_id='context-revocable' "
            "AND action='alert.dismiss'"
        )
    before = (_count_rows("alert_triage"), _count_rows("idempotency_records"))
    response = _post(
        client,
        alert_id,
        _cmd("triage_dismiss", reason=REASON),
        "k-context-revoked-123456789",
        BEARERS["context_revocable"],
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authorized"
    assert (_count_rows("alert_triage"), _count_rows("idempotency_records")) == before


def test_context_fails_closed_when_real_policy_storage_is_unavailable() -> None:
    role = "triage_context_policy_denied"
    password = uuid4().hex
    parts = urlsplit(DATABASE_URL)
    dsn = urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.netloc.rsplit('@', 1)[-1]}"))
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
            connection.execute(f"DROP OWNED BY {role}")
            connection.execute(f"DROP ROLE {role}")
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(connection.info.dbname), sql.Identifier(role)
            )
        )
        connection.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        connection.execute(f"GRANT SELECT ON TABLE credentials, principals, resources TO {role}")
    try:
        with psycopg.connect(dsn) as restricted:
            assert restricted.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] > 0
        with _client(dsn) as client:
            response = _get_context(client, "al-context-policy-fault", BEARERS["reader"])
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "storage_unavailable"
        assert response.headers["Retry-After"] == "5"
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(f"DROP OWNED BY {role}")
            connection.execute(f"DROP ROLE {role}")


def test_triage_state_reads_back_dismiss() -> None:
    client = _client()
    posted = _post(
        client,
        "al-read-dismiss",
        _cmd("triage_dismiss", reason=REASON),
        "k-read-dismiss-1234567",
        BEARERS["op"],
    )
    assert posted.status_code == 200
    read = _get(client, "al-read-dismiss", BEARERS["reader"])
    assert read.status_code == 200
    body = read.json()
    assert STATE_VALIDATOR.is_valid(body), body
    assert (body["status"], body["reason"]) == ("dismissed", REASON)
    assert (body["actor"], body["expected_version"]) == ("op-human", 1)
    assert (body["decision_origin"], body["responsible_system"]) == ("manual", None)
    assert body["incident_id"] is None
    assert _get(client, "al-read-dismiss", BEARERS["reader"]).json() == body


def test_triage_state_command_only_is_403() -> None:
    """The contractual read grant alone authorizes the read (P1 guard)."""
    client = _client()
    existing = _get(client, "al-read-dismiss", BEARERS["op"])
    assert existing.status_code == 403
    assert existing.json()["error"]["code"] == "not_authorized"
    assert "dismissed" not in existing.text
    missing = _get(client, "al-read-ghost-three", BEARERS["op"])
    assert missing.status_code == 403
    assert "al-read-ghost-three" not in missing.text


def test_triage_state_carries_declared_incident() -> None:
    client = _client()
    posted = _post(
        client,
        "al-read-declare",
        _cmd("triage_declare", reason=REASON, severity="sev2"),
        "k-read-declare-1234567",
        BEARERS["op"],
    )
    assert posted.status_code == 201
    body = _get(client, "al-read-declare", BEARERS["reader"]).json()
    assert STATE_VALIDATOR.is_valid(body), body
    assert body["status"] == "declared"
    assert body["incident_id"] == posted.json()["incident_id"]


def test_triage_state_unknown_is_404() -> None:
    response = _get(_client(), "al-read-ghost-one", BEARERS["reader"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "triage_not_found"


def test_triage_state_denials() -> None:
    client = _client()
    missing = _get(client, "al-read-dismiss", None)
    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    forbidden = _get(client, "al-read-ghost-two", BEARERS["bystander"])
    assert forbidden.status_code == 403
    assert "al-read-ghost-two" not in forbidden.text
    bad = _get(client, "BAD ID!", BEARERS["op"])
    assert bad.status_code == 400
    down = _get(
        _client("postgresql://postgres:postgres@127.0.0.1:1/postgres"),
        "al-read-dismiss",
        BEARERS["op"],
    )
    assert down.status_code == 503
    assert down.headers["Retry-After"] == "5"


def test_eligible_incidents_uses_valid_untriaged_alert_without_inventory_lookup() -> None:
    client, alert_id = _client(), "al-no-triage-eligible"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.incidents SET state=jsonb_build_object('state','closed')"
        )
    before = (
        _incident_count(),
        _count_rows("alert_triage"),
        _count_rows("incident.run_events"),
        _count_rows("idempotency_records"),
    )

    listed = _get_eligible_incidents(client, alert_id, BEARERS["eligible_linker"])

    assert listed.status_code == 200, listed.text
    assert listed.json() == {"items": []}
    assert _get(client, alert_id, BEARERS["reader"]).status_code == 404
    assert (
        _incident_count(),
        _count_rows("alert_triage"),
        _count_rows("incident.run_events"),
        _count_rows("idempotency_records"),
    ) == before


def test_eligible_incidents_requires_authentication_and_both_read_grants() -> None:
    client, alert_id = _client(), "al-eligible-auth"
    for bearer, status, code in (
        (None, 401, "authentication_failed"),
        (BEARERS["reader"], 403, "not_authorized"),
        (BEARERS["op"], 403, "not_authorized"),
        (BEARERS["eligible_linker"], 200, None),
    ):
        response = _get_eligible_incidents(client, alert_id, bearer)
        assert response.status_code == status, response.text
        if code is not None:
            assert response.json()["error"]["code"] == code


def test_eligible_incidents_rejects_malformed_alert_id_before_authentication() -> None:
    response = _get_eligible_incidents(_client(), "BAD ID!", None)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_command"


def test_eligible_incidents_fails_closed_on_real_incident_storage_denial() -> None:
    role = "triage_eligible_incidents_denied"
    password = uuid4().hex
    parts = urlsplit(DATABASE_URL)
    dsn = urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.netloc.rsplit('@', 1)[-1]}"))
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
            connection.execute(f"DROP OWNED BY {role}")
            connection.execute(f"DROP ROLE {role}")
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(connection.info.dbname), sql.Identifier(role)
            )
        )
        connection.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        connection.execute(
            f"GRANT SELECT ON TABLE credentials, principals, resources, grants TO {role}"
        )
    try:
        with psycopg.connect(dsn) as restricted:
            assert restricted.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] > 0
        with _client(dsn) as client:
            denied = _get_eligible_incidents(client, "al-eligible-denied", BEARERS["reader"])
            unavailable = _get_eligible_incidents(
                client, "al-eligible-storage-fault", BEARERS["eligible_linker"]
            )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "not_authorized"
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "storage_unavailable"
        assert unavailable.headers["Retry-After"] == "5"
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(f"DROP OWNED BY {role}")
            connection.execute(f"DROP ROLE {role}")


def test_eligible_incidents_caps_in_deterministic_order_and_excludes_terminal_states() -> None:
    eligible = ("active", "investigating", "mitigating", "verifying")
    terminal = ("resolved", "postmortem", "closed")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.incidents SET state=jsonb_build_object('state','closed')"
        )
        for index in range(105):
            incident_id = f"inc-list-{index:03d}"
            state = eligible[index % len(eligible)]
            connection.execute(
                "INSERT INTO incident.incidents (incident_id,state,version,created_at,updated_at) "
                "VALUES (%s,jsonb_build_object('state',CAST(%s AS text)),0,now(),now())",
                (incident_id, state),
            )
        for state in terminal:
            connection.execute(
                "INSERT INTO incident.incidents (incident_id,state,version,created_at,updated_at) "
                "VALUES (%s,jsonb_build_object('state',CAST(%s AS text)),0,now(),now())",
                (f"inc-a-terminal-{state}", state),
            )

    response = _get_eligible_incidents(_client(), "al-eligible-bounded", BEARERS["eligible_linker"])
    expected = [
        {"incident_id": f"inc-list-{index:03d}", "state": eligible[index % len(eligible)]}
        for index in range(100)
    ]
    assert response.status_code == 200, response.text
    assert response.json() == {"items": expected}


def test_eligible_list_then_closed_destination_is_rejected_without_association() -> None:
    client, alert_id, incident_id = _client(), "al-eligible-close-race", "inc-eligible-race"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO incident.incidents (incident_id,state,version,created_at,updated_at) "
            "VALUES (%s,jsonb_build_object('state','active'),0,now(),now())",
            (incident_id,),
        )

    listed = _get_eligible_incidents(client, alert_id, BEARERS["eligible_linker"])
    assert listed.status_code == 200, listed.text
    assert {item["incident_id"] for item in listed.json()["items"]} >= {incident_id}
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.incidents SET state=jsonb_build_object('state','resolved') "
            "WHERE incident_id=%s",
            (incident_id,),
        )
    before = (_count_rows("alert_triage"), _count_rows("idempotency_records"))
    linked = _post(
        client,
        alert_id,
        _cmd("triage_link", target_incident_id=incident_id, reason=REASON),
        "k-eligible-close-race-01",
        BEARERS["op"],
    )
    assert linked.status_code == 409, linked.text
    assert linked.json()["error"]["code"] == "destination_ineligible"
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM alert_triage WHERE alert_id=%s AND status='linked'",
                (alert_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT state->>'state' FROM incident.incidents WHERE incident_id=%s",
                (incident_id,),
            ).fetchone()[0]
            == "resolved"
        )
    assert (_count_rows("alert_triage"), _count_rows("idempotency_records")) == before
