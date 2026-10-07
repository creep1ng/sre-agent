"""Issue #23 C2b: triage commands over real HTTP on real PostgreSQL."""

import asyncio
import os
from pathlib import Path

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
REASON = "Sustained 5xx spike on checkout."
IMPACT = "Checkout requests failed for customers."
BEARERS: dict[str, str] = {}
ROOT = Path(__file__).parents[1]
STATE_VALIDATOR = Draft202012Validator(
    yaml.safe_load((ROOT / "agent" / "schemas" / "triage-state.schema.yaml").read_text())
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
            "('producer-agent','agent','External producer','active',now(),now())"
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
                ("alert.dismiss", "alert.associate", "run.read", "incident.declare")
            ):
                await grants.create(
                    f"grant-producer-agent-{index}",
                    "producer-agent",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
        BEARERS["op"] = f"Bearer {issued_op.key}"
        BEARERS["reader"] = f"Bearer {issued_reader.key}"
        BEARERS["bystander"] = f"Bearer {issued_by.key}"
        BEARERS["agent"] = f"Bearer {issued_agent.key}"

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client(url: str = DATABASE_URL) -> TestClient:
    return TestClient(create_application(Settings(url)))


def _cmd(operation: str, version: int = 1, **kwargs) -> dict:
    if operation == "triage_declare":
        kwargs.setdefault("impact", IMPACT)
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
    body = _cmd("triage_declare", reason=REASON, severity="sev2", impact=impact)
    before = _incident_count()
    first = _post(client, alert_id, body, "k-impact-http-123456", BEARERS["op"])
    assert first.status_code == 201
    result = first.json()
    assert _incident_count() == before + 1

    state = _get(client, alert_id, BEARERS["reader"])
    assert state.status_code == 200
    assert state.json()["incident_id"] == result["incident_id"]
    detail = client.get(
        f"/v1/incidents/{result['incident_id']}", headers={"Authorization": BEARERS["op"]}
    )
    assert detail.status_code == 200
    assert detail.json()["impact"] == impact

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        incident = connection.execute(
            "SELECT state->>'impact' FROM incident.incidents WHERE incident_id=%s",
            (result["incident_id"],),
        ).fetchone()
        event = connection.execute(
            "SELECT payload->'incident_state'->>'impact' FROM incident.run_events "
            "WHERE incident_id=%s ORDER BY sequence LIMIT 1",
            (result["incident_id"],),
        ).fetchone()
        event_count = connection.execute(
            "SELECT count(*) FROM incident.run_events WHERE incident_id=%s",
            (result["incident_id"],),
        ).fetchone()[0]
    assert incident == (impact,)
    assert event == (impact,)
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
        ("triage_dismiss", {"reason": REASON}),
        (
            "triage_link",
            {"reason": REASON, "target_incident_id": "inc-http-target"},
        ),
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
