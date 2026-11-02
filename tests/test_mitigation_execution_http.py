"""Approving a mitigation runs its deploy-executor operation, checked first (#722, third cut).

Written before the check (cases 1 to 5) and the call (6 and 7) existed. Ways this can fail:
1. an approval whose operation the executor's catalog no longer offers is still approved;
2. so is one whose operation the agent holds no `mitigation.execute` grant for;
3. an executor that is not configured or cannot be read lets the approval through;
4. a refused approval still changes the incident's state or version, or reaches the executor;
5. a stale approval, or one without an operation, stops being answered as before;
6. the approval moves to verifying and nothing runs, or the operation runs unsigned, with a key
   that does not bind it to the run and the mitigation, or twice when the approval is retried;
7. an executor that fails, or answers nothing usable, still lets the incident move on;
8. an approval that reaches the executor leaves no audit of how it ended;
9. an operation runs where nothing audits it, or one that ran is answered, and the incident
   moved, without its audit (8 and 9 written before the audit existed);
10. the timeline does not say what ran, or a refused approval leaves it silent (written before
    the events existed).
Principals and the human grants come from the #330 suite; this module adds the investigator's
agent and its one grant, on the rollback of sre-checkout. Only the deploy-executor is scripted,
as an HTTP server that serves its catalog and checks that every operation is signed.
"""

import asyncio
import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_incident_command_http import (  # noqa: F401  (module fixture)
    BEARERS,
    DATABASE_URL,
    RUNS,
    _body,
    _mitigating,
    _send,
    authorized_database,
)

from sre_agent.application import create_application
from sre_agent.executor.signature import verify
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import PostgresAuditStore
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository
from sre_agent.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provision_demo import SERVICE_OPERATIONS, demo_grants, service_operation  # noqa: E402
from provision_incident_workflow import build_service  # noqa: E402

ROLLBACK = {
    "service": "sre-checkout",
    "operation": "deployment.rollback",
    "parameters": {"to_tag": "1.4.0"},
}
RESTART = {"service": "sre-checkout", "operation": "deployment.restart", "parameters": {}}
DOWN = "nobody answers"
SIGNING_KEY = "k" * 64
RESULT = {
    "execution_id": "exe_0123456789abcdef",
    "outcome": "rolled_back",
    "replayed": False,
    "before": {"image": "demo/checkout:1.5.0"},
    "after": {"image": "demo/checkout:1.4.0"},
    "executed_at": "2026-10-30T12:00:00.000Z",
    "duration_ms": 5162,
}
AGENT: list[str] = []
CALLS: list[tuple[str, str, dict[str, Any], str | None]] = []


@pytest.fixture(scope="module", autouse=True)
def agent_grant(request: pytest.FixtureRequest) -> None:
    """The investigator's agent and, as the demo provisions them, the operations the executor
    enrols and the agent's one grant: it may roll sre-checkout back, never restart it."""
    request.getfixturevalue("authorized_database")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('incident-harness','agent','Investigator','active',now(),now())"
        )
    database = Database(DATABASE_URL)

    async def setup() -> None:
        try:
            async with database.transaction() as session:
                credentials = CredentialRepository(session)
                admin = f"Bearer {(await credentials.issue('admin-human')).key}"
                AGENT.append((await credentials.issue("incident-harness")).key)
            control = build_service(database, b"0" * 32)
            for resource_id, description in SERVICE_OPERATIONS.items():
                body = service_operation(resource_id, description)
                assert (
                    await control.create_catalog_resource(body, admin, resource_id)
                ).status_code == 201
            [grant] = [body for body in demo_grants() if body["action"] == "mitigation.execute"]
            assert (await control.create_grant(grant, admin, grant["grant_id"])).status_code == 201
        finally:
            await database.dispose()

    asyncio.run(setup())


class _Executor(BaseHTTPRequestHandler):
    """The deploy-executor's catalog for sre-checkout, at the image a case says is running, and
    the operations it is sent, with the signature checked as the executor checks it."""

    def log_message(self, *_: Any) -> None:
        return

    def _send(self, status: int, body: dict[str, Any]) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self) -> None:
        if self.path != "/v1/services/sre-checkout":
            return self._send(404, {"error": {"code": "service_not_enrolled", "message": "no"}})
        offers = [("deployment.restart", []), ("deployment.rollback", ["to_tag"])]
        self._send(
            200,
            {
                "service": "sre-checkout",
                "container": {"image": self.server.running},  # type: ignore[attr-defined]
                "available_tags": ["1.4.0", "1.5.0"],
                "operations": [{"operation": o, "parameters": p} for o, p in offers],
            },
        )

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["content-length"]))
        key, timestamp, signature = (
            self.headers.get(name, "")
            for name in ("idempotency-key", "x-executor-timestamp", "x-executor-signature")
        )
        refused = verify(
            SIGNING_KEY.encode(), 300, "POST", self.path, key, body, timestamp, signature
        )
        CALLS.append((self.path, key, json.loads(body), refused))
        self._send(*self.server.answer)  # type: ignore[attr-defined]


@contextmanager
def _executor(running: str | None, answer: tuple = (200, RESULT)) -> Iterator[str | None]:
    """The executor's URL, running that image; None configures none, DOWN one that never answers."""
    CALLS.clear()
    if running is None or running == DOWN:
        yield None if running is None else "http://127.0.0.1:9"
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Executor)
    server.running, server.answer = running, answer  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _settings(executor_url: str | None) -> Settings:
    environment = {
        "DATABASE_URL": DATABASE_URL,
        "AUDIT_HMAC_KEY": "x" * 32,
        "INVESTIGATOR_GATEWAY_URL": "http://127.0.0.1:9",
        "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
        "INVESTIGATOR_GATEWAY_API_KEY": AGENT[0],
        "DEPLOY_EXECUTOR_SIGNING_KEY": SIGNING_KEY,
    }
    return Settings.from_environment(environment | {"DEPLOY_EXECUTOR_URL": executor_url or ""})


def _row(incident_id: str) -> tuple[str, int]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state->>'state', version FROM incident.incidents WHERE incident_id=%s",
            (incident_id,),
        ).fetchone()
    assert row is not None
    return str(row[0]), int(row[1])


def _strategy(incident_id: str) -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state->'mitigation_strategy' FROM incident.incidents WHERE incident_id=%s",
            (incident_id,),
        ).fetchone()
    assert row is not None
    return dict(row[0])


# case: (the mitigation's operation, the image the executor runs, the answer expected)
ADMISSION = {
    "allowed": (ROLLBACK, "demo/checkout:1.5.0", (202, None)),
    "no-operation": (None, None, (202, None)),
    "stale": (ROLLBACK, "demo/checkout:1.5.0", (409, "run_conflict")),
    "unoffered": (ROLLBACK, "demo/checkout:1.4.0", (409, "precondition_failed")),
    "ungranted": (RESTART, "demo/checkout:1.5.0", (403, "operation_not_authorized")),
    "unreachable": (ROLLBACK, DOWN, (503, "executor_unavailable")),
    "unconfigured": (ROLLBACK, None, (503, "executor_unavailable")),
}


@pytest.mark.parametrize("case", ADMISSION)
def test_an_approval_moves_only_while_its_operation_is_offered_and_granted(case: str) -> None:
    operation, running, expected = ADMISSION[case]
    incident_id = f"inc-admit-{case}"
    _mitigating(incident_id, **({"operation": operation} if operation else {}))
    body = _body(expected_incident_version=1 if case == "stale" else 0)
    with _executor(running) as url:
        response = _send(incident_id, f"key-admit-{case}", body, settings=_settings(url))
    code = response.json()["error"]["code"] if response.status_code != 202 else None
    assert (response.status_code, code) == expected, response.text
    assert _row(incident_id) == (("verifying", 1) if code is None else ("mitigating", 0))
    assert len(CALLS) == (1 if case == "allowed" else 0)


def test_the_approval_runs_the_operation_once_signed_and_records_its_receipt() -> None:
    _mitigating("inc-execute-once", operation=ROLLBACK)
    with _executor("demo/checkout:1.5.0") as url:
        first = _send("inc-execute-once", "key-execute-once", _body(), settings=_settings(url))
        again = _send("inc-execute-once", "key-execute-once", _body(), settings=_settings(url))
    assert (first.status_code, again.status_code) == (202, 202), first.text
    [(path, key, sent, refused)] = CALLS
    assert (path, sent, refused) == (
        "/v1/operations/deployment.rollback",
        {"service": "sre-checkout", "to_tag": "1.4.0"},
        None,
    )
    assert key == f"mitexec-{RUNS['inc-execute-once']}-mit_disable_payment_flag"
    strategy = _strategy("inc-execute-once")
    assert (strategy["approval_status"], strategy["execution_mode"]) == ("approved", "executed")
    assert strategy["execution"] == {
        "execution_id": "exe_0123456789abcdef",
        "outcome": "rolled_back",
        "replayed": False,
        "before_image": "demo/checkout:1.5.0",
        "after_image": "demo/checkout:1.4.0",
        "executed_at": "2026-10-30T12:00:00.000Z",
        "duration_ms": 5162,
    }


# case: (what the executor answers the operation, the answer the approval gets)
FAILURES = {
    "failed": ((502, {"error": {"code": "execution_failed"}}), (409, "execution_failed")),
    "docker-down": ((503, {"error": {"code": "docker_unavailable"}}), (503, "execution_failed")),
    "unreadable": ((200, {"outcome": "rolled_back"}), (503, "executor_unavailable")),
}


@pytest.mark.parametrize("case", FAILURES)
def test_an_executor_that_fails_keeps_the_incident_mitigating(case: str) -> None:
    answer, expected = FAILURES[case]
    incident_id = f"inc-execute-{case}"
    _mitigating(incident_id, operation=ROLLBACK)
    with _executor("demo/checkout:1.5.0", answer) as url:
        response = _send(incident_id, f"key-execute-{case}", _body(), settings=_settings(url))
    assert (response.status_code, response.json()["error"]["code"]) == expected, response.text
    assert len(CALLS) == 1 and _row(incident_id) == ("mitigating", 0)
    assert "execution" not in _strategy(incident_id)


def _audit(incident_id: str) -> list[tuple[Any, ...]]:
    """The mitigation.execute audit of an incident, found by its correlation reference."""
    digest = AuditProjector(b"x" * 32).reference("incident_id", incident_id).digest
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT stage, outcome, response_status, reason_code, resource->>'resource_type', "
            "identity->>'principal_kind' FROM audit_events "
            "WHERE operation='mitigation.execute' AND correlation->'incident_ref'->>'digest'=%s",
            (digest,),
        ).fetchall()


def _timeline(incident_id: str) -> list[dict[str, Any]]:
    path = f"/v1/incidents/{incident_id}/runs/{RUNS[incident_id]}/events"
    with TestClient(create_application(_settings(None))) as client:
        page = client.get(path, headers={"Authorization": BEARERS["demo-human"]})
    assert page.status_code == 200, page.text
    return list(page.json()["events"])


FAILED = (502, {"error": {"code": "execution_failed"}})
# case: (operation, image running, executor answer, audit expected, timeline event expected)
RECORDS = {
    "allowed": (ROLLBACK, "demo/checkout:1.5.0", None, ("response", "success", 200, None), None),
    "ungranted": (
        RESTART,
        "demo/checkout:1.5.0",
        None,
        ("authorization", "denied", 403, "no_matching_grant"),
        ("denial", "operation_not_authorized"),
    ),
    "unoffered": (
        ROLLBACK,
        "demo/checkout:1.4.0",
        None,
        ("upstream", "error", 409, "status_conflict"),
        ("human_command", "precondition_failed"),
    ),
    "unreachable": (
        ROLLBACK,
        DOWN,
        None,
        ("upstream", "error", 503, "upstream_unavailable"),
        ("human_command", "executor_unavailable"),
    ),
    "failed": (
        ROLLBACK,
        "demo/checkout:1.5.0",
        FAILED,
        ("upstream", "error", 409, "upstream_failed"),
        ("human_command", "execution_failed"),
    ),
}


@pytest.mark.parametrize("case", RECORDS)
def test_an_approval_that_reaches_the_executor_is_audited_and_told_in_the_timeline(
    case: str,
) -> None:
    operation, running, answer, audit, refusal = RECORDS[case]
    incident_id = f"inc-record-{case}"
    _mitigating(incident_id, operation=operation)
    with _executor(running, answer or (200, RESULT)) as url:
        _send(incident_id, f"key-record-{case}", _body(), settings=_settings(url))
    assert _audit(incident_id) == [(*audit, "service_operation", "agent")]
    last = _timeline(incident_id)[-1]
    if refusal is None:
        assert (last["kind"], last["state"]) == ("state_change", "verifying")
        assert last["summary"] == (
            "Mitigation approved; the deploy-executor ran deployment.rollback on sre-checkout: "
            "rolled_back (demo/checkout:1.5.0 → demo/checkout:1.4.0)."
        )
        return
    assert (last["kind"], last["reason_code"]) == refusal
    assert last["actor"]["reference"]["principal_id"] == "demo-human" and last["request_id"]
    assert last["summary"].startswith("Approval not applied: ")
    assert last["summary"].endswith(" The incident stays mitigating.")


def test_an_operation_never_runs_or_is_answered_without_its_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mitigating("inc-unaudited", operation=ROLLBACK)
    _mitigating("inc-audit-down", operation=ROLLBACK)

    async def down(*_: Any) -> None:
        raise ConnectionError("the audit store is down")

    with _executor("demo/checkout:1.5.0") as url:
        unaudited = replace(_settings(url), audit_hmac_key=None)
        response = _send("inc-unaudited", "key-unaudited", _body(), settings=unaudited)
        assert (response.status_code, response.json()["error"]["code"]) == (
            503,
            "executor_unavailable",
        )
        assert CALLS == [] and _row("inc-unaudited") == ("mitigating", 0)
        monkeypatch.setattr(PostgresAuditStore, "append", down)
        lost = _send("inc-audit-down", "key-audit-down", _body(), settings=_settings(url))
        assert lost.status_code == 503 and _row("inc-audit-down") == ("mitigating", 0)
        monkeypatch.undo()
        retried = _send("inc-audit-down", "key-audit-down", _body(), settings=_settings(url))
    assert retried.status_code == 202 and _row("inc-audit-down") == ("verifying", 1)
    # Both carry the same key, so the real executor replays its result instead of running again.
    key = f"mitexec-{RUNS['inc-audit-down']}-mit_disable_payment_flag"
    assert [call[1] for call in CALLS] == [key, key]
    assert _audit("inc-audit-down") == [
        ("response", "success", 200, None, "service_operation", "agent")
    ]
