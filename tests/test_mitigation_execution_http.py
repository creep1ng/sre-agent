"""An approval checks its deploy-executor operation before anything moves (#722, third cut).

Written before the check existed. Ways this can fail:
1. an approval whose operation the executor's catalog no longer offers is still approved;
2. so is one whose operation the agent holds no `mitigation.execute` grant for;
3. an executor that is not configured or cannot be read lets the approval through;
4. a refused approval still changes the incident's state or version;
5. a stale approval, or one without an operation, stops being answered as before.
Principals and the human grants come from the #330 suite; this module adds the investigator's
agent and its one grant, on the rollback of sre-checkout. Only the deploy-executor is scripted,
as an HTTP server that serves its catalog.
"""

import asyncio
import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psycopg
import pytest
from test_incident_command_http import (  # noqa: F401  (module fixture)
    DATABASE_URL,
    _body,
    _mitigating,
    _send,
    authorized_database,
)

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
AGENT: list[str] = []


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
    """The deploy-executor's catalog for sre-checkout, at the image a case says is running."""

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


@contextmanager
def _executor(running: str | None) -> Iterator[str | None]:
    """The executor's URL, running that image; None configures none, DOWN one that never answers."""
    if running is None or running == DOWN:
        yield None if running is None else "http://127.0.0.1:9"
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Executor)
    server.running = running  # type: ignore[attr-defined]
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
