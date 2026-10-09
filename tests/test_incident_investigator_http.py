"""End-to-end evidence for governed investigation run startup and receipts."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn
import yaml
from alembic import command
from alembic.config import Config
from jsonschema import Draft202012Validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from sre_agent.application import create_application
from sre_agent.gateway.mcp import MCPUpstreamTimeout, PrometheusQuery
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.incident.persistence import DecisionDraft, EventDraft
from sre_agent.incident.runtime import ActorReference, IncidentCommand, IncidentRuntime, RunStart
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.investigator.client import MCPGatewayClient
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.seeds import SeedSettings, seed, seed_mcp_demo
from sre_agent.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
HUMAN_KEY = "sre_demo_0123456789abcdefghijklmnop"
HARNESS_KEY = "sre_inci_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "local-investigation-audit-key"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": HUMAN_KEY,
    "INCIDENT_HARNESS_API_KEY": HARNESS_KEY,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> Iterator[None]:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, audit_events, skill_versions, grants, credentials, "
            "resources, alert_triage, mcp_tools, mcp_servers, principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        await seed(database, SeedSettings.from_environment(SEED_ENV))
        await seed_mcp_demo(database)
        await database.dispose()

    asyncio.run(bootstrap())
    yield


def _incident(incident_id: str) -> dict[str, Any]:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "active",
        "incident_id": incident_id,
        "severity": "sev2",
        "impact": None,
        "alert": {
            "alert_id": "alt-investigation-http",
            "service": "payments",
            "severity": "sev2",
            "status": "triaged",
            "observed_at": NOW.isoformat(),
            "summary": "Elevated payment errors.",
            "source": "synthetic-test",
        },
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW.isoformat(),
    }


def _add_incident(incident_id: str) -> None:
    async def add() -> None:
        database = Database(DATABASE_URL)
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(incident_id, _incident(incident_id), now=NOW)
        await database.dispose()

    asyncio.run(add())


def _create_started_run_with_pending_receipt(incident_id: str, command_id: str) -> str:
    async def create() -> str:
        database = Database(DATABASE_URL)
        workflow = load_incident_workflow(ROOT / "agent/workflows/incident-response.yaml")
        runtime = IncidentRuntime(workflow, lambda: PostgresIncidentUnitOfWork(database))
        result = await runtime.start_run(
            RunStart(
                command_id=command_id,
                incident_id=incident_id,
                objective="investigate",
                actor="human",
                actor_reference=ActorReference(principal_id="demo-human"),
            )
        )
        run_id = result.run.run_id
        run_suffix = run_id.removeprefix("run_")
        decision_id = f"dec_{run_suffix}"
        event_id = f"evt_{run_suffix}"
        now = NOW.isoformat()
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """INSERT INTO incident.decisions
                   (decision_id,incident_id,run_id,turn_id,document,decided_at)
                   VALUES (%s,%s,%s,NULL,%s::jsonb,%s)""",
                (
                    decision_id,
                    incident_id,
                    run_id,
                    json.dumps(
                        {
                            "actor": "agent",
                            "actor_reference": {
                                "reference_version": "1.0.0",
                                "principal_id": "incident-harness",
                            },
                        }
                    ),
                    now,
                ),
            )
            connection.execute(
                """INSERT INTO incident.run_events
                   (event_id,incident_id,run_id,turn_id,sequence,kind,payload,occurred_at)
                   VALUES (%s,%s,%s,NULL,1,'dispatch_receipt',%s::jsonb,%s)""",
                (
                    event_id,
                    incident_id,
                    run_id,
                    json.dumps(
                        {
                            "decision_id": decision_id,
                            "to": "investigating",
                            "dispatch_receipt": {
                                "dispatch_id": run_id,
                                "phase": "intent",
                                "status": "pending",
                                "request_ids": [],
                                "mcp_request_ids": [],
                            },
                        }
                    ),
                    now,
                ),
            )
        await database.dispose()
        return run_id

    return asyncio.run(create())


class ScriptedLLM:
    def __init__(self, final_outcome: dict[str, Any] | None = None) -> None:
        self.requests: list[ProviderRequest] = []
        self.final_outcome = final_outcome

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if len(self.requests) == 1:
            text = json.dumps(
                {
                    "action": "use_tool",
                    "tool": "query_prometheus",
                    "arguments": {
                        "datasource_uid": "webstore-metrics",
                        "expr": "rate(http_requests_total[5m])",
                        "query_type": "instant",
                        "end_time": "now",
                    },
                }
            )
        else:
            if self.final_outcome is not None:
                text = json.dumps(self.final_outcome)
            else:
                state = json.loads(request.input.split("State: ", 1)[1])
                evidence_id = state["collected_evidence"][0]["evidence_id"]
                text = json.dumps(
                    {
                        "action": "propose_hypothesis",
                        "statement": "A synthetic payment error-rate increase is visible.",
                        "confidence": "medium",
                        "supporting_evidence": [evidence_id],
                    }
                )
        return ProviderResult(
            response_id=f"resp_test_{len(self.requests):04d}",
            model=request.model,
            text=text,
            provider=request.provider,
        )


class InvalidMCPContractLLM(ScriptedLLM):
    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(
            response_id="resp_test_invalid_mcp_contract",
            model=request.model,
            text=json.dumps(
                {
                    "action": "use_tool",
                    "tool": "query_prometheus",
                    "arguments": {
                        "datasource_uid": "webstore-metrics",
                        "expr": "rate(http_requests_total[5m])",
                        "query_type": "range",
                        "end_time": "now",
                    },
                }
            ),
            provider=request.provider,
        )


class SchemaDrivenLLM(ScriptedLLM):
    def __init__(self) -> None:
        super().__init__()
        self.tool_schemas: list[dict[str, Any]] = []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        state = json.loads(request.input.split("State: ", 1)[1])
        schemas = state.get("tool_schemas", {})
        self.tool_schemas.append(schemas)
        if len(self.requests) == 1:
            arguments = json.loads(
                (ROOT / "schemas/mcp/1.0.0/examples/query-prometheus-input.json").read_text(
                    encoding="utf-8"
                )
            )
            if "query_prometheus" in schemas:
                Draft202012Validator(schemas["query_prometheus"]).validate(arguments)
            text = json.dumps(
                {
                    "action": "use_tool",
                    "tool": "query_prometheus",
                    "arguments": arguments,
                }
            )
        else:
            evidence_id = state["collected_evidence"][0]["evidence_id"]
            text = json.dumps(
                {
                    "action": "propose_hypothesis",
                    "statement": "The authorized synthetic Prometheus query returned evidence.",
                    "confidence": "medium",
                    "supporting_evidence": [evidence_id],
                }
            )
        return ProviderResult(
            response_id=f"resp_schema_{len(self.requests):04d}",
            model=request.model,
            text=text,
            provider=request.provider,
        )


class BlockingLLM(ScriptedLLM):
    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        super().__init__()
        self.entered, self.release = entered, release
        self.calls_started = 0

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.calls_started += 1
        if self.calls_started == 1:
            self.entered.set()
            if not await asyncio.to_thread(self.release.wait, 10):
                raise TimeoutError("test did not release the provider")
        return await super().create(request)


class BlockingFinalTurnLLM(ScriptedLLM):
    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        super().__init__()
        self.entered, self.release = entered, release

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        call = len(self.requests)
        if call == 6:
            self.entered.set()
            if not await asyncio.to_thread(self.release.wait, 10):
                raise TimeoutError("test did not release the final provider response")
        if call < 6:
            text = json.dumps(
                {
                    "action": "use_tool",
                    "tool": "query_prometheus",
                    "arguments": {
                        "datasource_uid": "webstore-metrics",
                        "expr": "rate(http_requests_total[5m])",
                        "query_type": "instant",
                        "end_time": "now",
                    },
                }
            )
        else:
            state = json.loads(request.input.split("State: ", 1)[1])
            evidence_ids = [item["evidence_id"] for item in state["collected_evidence"]]
            text = json.dumps(
                {
                    "action": "propose_hypothesis",
                    "statement": "A synthetic signal is confirmed on the final turn.",
                    "confidence": "medium",
                    "supporting_evidence": [evidence_ids[0]],
                }
            )
        return ProviderResult(
            response_id=f"resp_test_{call:04d}",
            model=request.model,
            text=text,
            provider=request.provider,
        )


class ScriptedMCP:
    def __init__(self, *, lose_response: bool = False, response: Any | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.lose_response = lose_response
        self.response = response

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        if self.lose_response:
            raise MCPUpstreamTimeout
        if self.response is not None:
            return self.response
        return {
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"service": "payments"}, "value": [0, "3"]}],
            }
        }


class _WitnessLLM:
    def __init__(self, upstream_url: str) -> None:
        self.upstream_url = upstream_url

    async def create(self, request: ProviderRequest) -> ProviderResult:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.upstream_url}/llm",
                json={
                    "provider": request.provider,
                    "model": request.model,
                    "input": request.input,
                },
            )
        response.raise_for_status()
        return ProviderResult(**response.json())


class _WitnessMCP:
    def __init__(self, upstream_url: str) -> None:
        self.upstream_url = upstream_url

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.upstream_url}/mcp",
                json={"tool_name": tool_name, "arguments": arguments},
            )
        response.raise_for_status()
        return response.json()


class _WitnessHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], witness_path: Path, *, block_second_llm: bool):
        super().__init__(address, _WitnessRequestHandler)
        self.witness_path = witness_path
        self.block_second_llm = block_second_llm
        self.counts = {"llm": 0, "mcp": 0}
        self.count_lock = threading.Lock()
        self.llm_blocked = threading.Event()
        self.release_llm = threading.Event()

    def witness(self, kind: str, sequence: int, **details: str) -> None:
        record = {"kind": kind, "sequence": sequence, **details}
        with self.witness_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


class _WitnessRequestHandler(BaseHTTPRequestHandler):
    server: _WitnessHTTPServer

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _respond(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            # Expected when the test kills the app while this upstream response is held.
            return

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/mcp":
            with self.server.count_lock:
                self.server.counts["mcp"] += 1
                sequence = self.server.counts["mcp"]
            self.server.witness("mcp", sequence, tool=body["tool_name"])
            self._respond(
                {
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"service": "payments"}, "value": [0, "3"]}],
                    }
                }
            )
            return
        if self.path != "/llm":
            self.send_error(404)
            return

        with self.server.count_lock:
            self.server.counts["llm"] += 1
            sequence = self.server.counts["llm"]
        self.server.witness("llm", sequence)
        if sequence == 1:
            text = json.dumps(
                {
                    "action": "use_tool",
                    "tool": "query_prometheus",
                    "arguments": {
                        "datasource_uid": "webstore-metrics",
                        "expr": "rate(http_requests_total[5m])",
                        "query_type": "instant",
                        "end_time": "now",
                    },
                }
            )
        else:
            if self.server.block_second_llm and sequence == 2:
                self.server.llm_blocked.set()
                if not self.server.release_llm.wait(90):
                    self.send_error(504)
                    return
            state = json.loads(body["input"].split("State: ", 1)[1])
            evidence_id = state["collected_evidence"][0]["evidence_id"]
            text = json.dumps(
                {
                    "action": "propose_hypothesis",
                    "statement": "A synthetic payment error-rate increase is visible.",
                    "confidence": "medium",
                    "supporting_evidence": [evidence_id],
                }
            )
        self._respond(
            {
                "response_id": f"resp_witness_{sequence:04d}",
                "model": body["model"],
                "provider": body["provider"],
                "text": text,
            }
        )


@contextmanager
def _controlled_upstream(*, block_second_llm: bool) -> Iterator[tuple[str, _WitnessHTTPServer]]:
    with tempfile.NamedTemporaryFile(prefix="issue330-upstream-", delete=False) as witness:
        witness_path = Path(witness.name)
    server = _WitnessHTTPServer(("127.0.0.1", 0), witness_path, block_second_llm=block_second_llm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", server
    finally:
        server.release_llm.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        witness_path.unlink(missing_ok=True)


def _run_subprocess_application(port: int, upstream_url: str) -> None:
    application = _application(
        f"http://127.0.0.1:{port}",
        llm=_WitnessLLM(upstream_url),  # type: ignore[arg-type]
        mcp=_WitnessMCP(upstream_url),  # type: ignore[arg-type]
    )
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="critical")


def _spawn_application(port: int, upstream_url: str) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(ROOT / "src"), str(ROOT / "tests"), env.get("PYTHONPATH", ""))
        if value
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; from test_incident_investigator_http import "
            "_run_subprocess_application; "
            "_run_subprocess_application(int(sys.argv[1]), sys.argv[2])",
            str(port),
            upstream_url,
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("investigator app process exited during startup")
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=1)
            if response.status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.1)
    process.kill()
    process.wait(timeout=10)
    raise RuntimeError("investigator app process did not become ready")


def _read_witness(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stop_app_process(process: subprocess.Popen) -> int:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    try:
        return process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=10)


@contextmanager
def _serve(application: Any, port: int) -> Iterator[str]:
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="critical")
    )
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "local API did not start"
    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "local API did not stop"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _application(
    base_url: str,
    *,
    harness_key: str = HARNESS_KEY,
    llm: ScriptedLLM | None = None,
    mcp: ScriptedMCP | None = None,
) -> Any:
    settings = Settings.from_environment(
        SEED_ENV
        | {
            "DATABASE_URL": DATABASE_URL,
            "AUDIT_HMAC_KEY": AUDIT_KEY,
            "INVESTIGATOR_GATEWAY_URL": base_url,
            "INVESTIGATOR_GATEWAY_API_KEY": harness_key,
            "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
        }
    )
    return create_application(
        settings,
        llm_provider=llm or ScriptedLLM(),
        mcp_client=mcp or ScriptedMCP(),
    )


def _add_agent_mcp_grants(client: httpx.Client, suffix: str) -> None:
    for grant_id, action, resource_type, resource_id in (
        (f"grant-agent-mcp-discovery-{suffix}", "mcp.discovery", "mcp_server", "grafana-mcp"),
        (
            f"grant-agent-mcp-prometheus-{suffix}",
            "mcp.invoke",
            "mcp_tool",
            "query_prometheus",
        ),
    ):
        response = client.post(
            "/v1/grants",
            headers={
                "Authorization": f"Bearer {ADMIN_KEY}",
                "Idempotency-Key": f"create-{grant_id}",
            },
            json={
                "grant_id": grant_id,
                "principal_id": "incident-harness",
                "action": action,
                "resource": {"resource_type": resource_type, "resource_id": resource_id},
                "effect": "allow",
            },
        )
        assert response.status_code == 201, response.status_code


def _grant_run_access() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from provision_incident_workflow import build_service, provision

    async def run() -> None:
        database = Database(DATABASE_URL)
        result = await provision(build_service(database, AUDIT_KEY.encode()), f"Bearer {ADMIN_KEY}")
        await database.dispose()
        assert result.run_start_active and result.run_read_active

    asyncio.run(run())


def _start(client: httpx.Client, incident_id: str, idempotency_key: str) -> httpx.Response:
    return client.post(
        f"/v1/incidents/{incident_id}/runs",
        headers={"Authorization": f"Bearer {HUMAN_KEY}", "Idempotency-Key": idempotency_key},
        json={"workflow_version": "1.0.0", "objective": "investigate"},
    )


def _database_rows(
    incident_id: str,
    run_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    with psycopg.connect(DATABASE_URL) as connection:
        incident = connection.execute(
            "SELECT state FROM incident.incidents WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()
        events = connection.execute(
            "SELECT kind,payload FROM incident.run_events WHERE run_id = %s ORDER BY sequence",
            (run_id,),
        ).fetchall()
        decisions = connection.execute(
            "SELECT document FROM incident.decisions WHERE run_id = %s ORDER BY decided_at",
            (run_id,),
        ).fetchall()
    return incident[0], [payload for _kind, payload in events], [row[0] for row in decisions]


def _receipts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event["dispatch_receipt"] for event in events if "dispatch_receipt" in event]


def _grant_receipt_from_any_run(incident_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with psycopg.connect(DATABASE_URL) as connection:
        run_id = connection.execute(
            "SELECT run_id FROM incident.runs WHERE incident_id=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (incident_id,),
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT payload FROM incident.run_events WHERE run_id=%s ORDER BY sequence", (run_id,)
        ).fetchall()
    return {"run_id": run_id}, [row[0] for row in rows]


def _active_state(run_id: str) -> tuple[dict[str, Any], int]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state,version FROM incident.runs WHERE run_id=%s", (run_id,)
        ).fetchone()
    return row[0], row[1]


def test_http_investigate_uses_governed_llm_and_mcp_and_persists_the_result() -> None:
    incident_id = "inc-investigator-positive"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    port = _free_port()
    # The service URL must be the actual local API, not a test transport or provider endpoint.
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        response = _start(client, incident_id, "investigation-positive-0001")
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        timeline = client.get(
            f"/v1/incidents/{incident_id}/runs/{run_id}/events",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )
        assert timeline.status_code == 200
        replay = _start(client, incident_id, "investigation-positive-0001")
        assert replay.status_code == 200 and replay.json()["run_id"] == run_id
    incident_state, event_payloads, decisions = _database_rows(incident_id, run_id)
    run_state, run_version = _active_state(run_id)
    receipts = _receipts(event_payloads)
    assert len(llm.requests) == 2 and len(mcp.calls) == 1
    assert llm.requests[0].input != "" and "inc-investigator-positive" in llm.requests[0].input
    assert incident_state["state"] == "investigating"
    assert len(incident_state["hypotheses"]) == 1
    assert len(incident_state["evidence"]) == 1
    assert run_state["current_state"] == "investigating" and run_version == 2
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "success"),
    ]
    mcp_request_id = incident_state["evidence"][0]["request_id"]
    assert mcp_request_id == receipts[-1]["mcp_request_ids"][0]
    transition_decision_id = next(
        event["decision_id"]
        for event in event_payloads
        if event.get("transition_id") == "continue_investigation"
    )
    assert all(
        event["decision_id"] == transition_decision_id
        for event in event_payloads
        if event.get("transition_id") == "continue_investigation"
        or event.get("outcome", {}).get("action") == "propose_hypothesis"
        or event.get("dispatch_receipt", {}).get("phase") == "outcome"
    )
    with psycopg.connect(DATABASE_URL) as connection:
        audit_count = connection.execute(
            "SELECT count(*) FROM audit_events WHERE correlation ->> 'request_id' = %s",
            (mcp_request_id,),
        ).fetchone()[0]
    assert audit_count == 1
    assert any(decision.get("transition_id") == "continue_investigation" for decision in decisions)
    assert timeline.json()["events"]
    assert "assembled_input" not in json.dumps(event_payloads)
    assert "model_output" not in json.dumps(event_payloads)


def test_investigator_receives_only_runtime_schemas_for_authorized_tools() -> None:
    incident_id = "inc-investigator-tool-schemas"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = SchemaDrivenLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        response = _start(client, incident_id, "investigation-tool-schemas-0001")
        assert response.status_code == 201
        run_id = response.json()["run_id"]

    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    receipts = _receipts(event_payloads)
    assert len(llm.requests) == 2 and len(mcp.calls) == 1
    assert [tool for tool, _ in mcp.calls] == ["query_prometheus"]
    assert len(llm.tool_schemas) == 2
    assert set(llm.tool_schemas[0]) == {"query_prometheus"}
    assert "query_elasticsearch" not in json.dumps(llm.tool_schemas)
    assert llm.tool_schemas[0]["query_prometheus"] == PrometheusQuery.model_json_schema()
    assert llm.tool_schemas[1] == llm.tool_schemas[0]
    assert incident_state["state"] == "investigating"
    assert len(incident_state["hypotheses"]) == 1 and len(incident_state["evidence"]) == 1
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "success"),
    ]


def test_indeterminate_prometheus_sample_survives_governed_http_and_prompt() -> None:
    incident_id = "inc-investigator-indeterminate-prometheus-sample"
    _add_incident(incident_id)
    _grant_run_access()
    llm = ScriptedLLM()
    mcp = ScriptedMCP(
        response={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "data": [1779400000, "NaN"],
                            "warnings": ["synthetic warning marker"],
                        }
                    ),
                }
            ]
        }
    )
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        response = _start(client, incident_id, "investigation-indeterminate-sample-0001")
        assert response.status_code == 201
        run_id = response.json()["run_id"]

    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    assert len(llm.requests) == 2 and len(mcp.calls) == 1
    prompt_state = json.loads(llm.requests[1].input.split("State: ", 1)[1])
    prompt_evidence = prompt_state["collected_evidence"][0]
    evidence_summary = json.loads(prompt_evidence["summary"])
    persisted_summary = json.loads(incident_state["evidence"][0]["summary"])

    assert _receipts(event_payloads)[-1]["status"] == "success"
    assert (
        evidence_summary
        == persisted_summary
        == {
            "result_type": "indeterminate",
            "result": [1779400000, "NaN"],
            "warnings": ["synthetic warning marker"],
        }
    )
    assert len(incident_state["hypotheses"]) == 1


def test_denied_mcp_discovery_is_confirmed_without_provider_or_upstream_and_replays_once() -> None:
    incident_id = "inc-investigator-denied"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", harness_key=RESTRICTED_KEY, llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        first = _start(client, incident_id, "investigation-denied-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]
        replay = _start(client, incident_id, "investigation-denied-0001")
        assert replay.status_code == 200
    incident_state, event_payloads, decisions = _database_rows(incident_id, run_id)
    receipts = _receipts(event_payloads)
    assert llm.requests == [] and mcp.calls == []
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert not any(
        event.get("transition_id") == "continue_investigation" for event in event_payloads
    )
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "confirmed_failure"),
    ]
    assert receipts[-1]["request_ids"]
    assert _active_state(run_id)[0]["current_state"] == "investigating"


def test_mcp_contract_rejection_before_dispatch_is_confirmed_failure() -> None:
    incident_id = "inc-investigator-mcp-rejected"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = InvalidMCPContractLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        first = _start(client, incident_id, "investigation-mcp-rejected-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]
        replay = _start(client, incident_id, "investigation-mcp-rejected-0001")
        assert replay.status_code == 200 and replay.json()["run_id"] == run_id

    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    receipts = _receipts(event_payloads)
    assert len(llm.requests) == 1 and mcp.calls == []
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert not any(
        event.get("transition_id") == "continue_investigation" for event in event_payloads
    )
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "confirmed_failure"),
    ]
    assert receipts[-1]["reason_code"] == "investigation_mcp_contract_rejected"
    assert receipts[-1]["mcp_request_ids"]
    assert _active_state(run_id)[0]["current_state"] == "investigating"
    with psycopg.connect(DATABASE_URL) as connection:
        audit_count = connection.execute(
            "SELECT count(*) FROM audit_events WHERE correlation ->> 'request_id' = %s",
            (receipts[-1]["mcp_request_ids"][0],),
        ).fetchone()[0]
    assert audit_count == 1


def test_http_200_mcp_body_rejection_has_bounded_diagnostic_and_no_redispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = "inc-investigator-mcp-body-rejected"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    original_send = MCPGatewayClient._send
    observed_mcp_responses: list[tuple[int, str]] = []

    async def incompatible_mcp_body(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await original_send(self, method, path, **kwargs)
        if method == "POST" and path == "/v1/mcp/tools/query_prometheus":
            assert response.status_code == 200
            request_id = response.headers["X-Request-ID"]
            observed_mcp_responses.append((response.status_code, request_id))
            return httpx.Response(
                response.status_code,
                json={"unexpected_shape": True},
                headers={"X-Request-ID": request_id},
            )
        return response

    monkeypatch.setattr(MCPGatewayClient, "_send", incompatible_mcp_body)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        first = _start(client, incident_id, "investigation-mcp-body-rejected-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]
        replay = _start(client, incident_id, "investigation-mcp-body-rejected-0001")
        assert replay.status_code == 200 and replay.json()["run_id"] == run_id
        timeline = client.get(
            f"/v1/incidents/{incident_id}/runs/{run_id}/events",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )
        assert timeline.status_code == 200

    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    receipt = _receipts(event_payloads)[-1]
    assert observed_mcp_responses and observed_mcp_responses[0][0] == 200
    assert len(llm.requests) == 1 and len(mcp.calls) == 1
    assert receipt["status"] == "unknown"
    assert receipt["reason_code"] == "investigation_upstream_unavailable"
    assert receipt["diagnostic"] == {
        "stage": "mcp_response_validation",
        "kind": "rejected",
        "http_status": 200,
        "request_id": observed_mcp_responses[0][1],
        "turn_count": 1,
        "collected_evidence_count": 0,
    }
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert _active_state(run_id)[0]["current_state"] == "investigating"
    assert all("diagnostic" not in event for event in timeline.json()["events"])
    with psycopg.connect(DATABASE_URL) as connection:
        audits = connection.execute(
            "SELECT operation, response_status FROM audit_events "
            "WHERE correlation ->> 'request_id' = ANY(%s)",
            (receipt["request_ids"],),
        ).fetchall()
    assert sorted(audits) == [
        ("mcp.discovery", 200),
        ("mcp.invoke", 200),
        ("responses.create", 200),
    ]


def test_transient_mcp_http_failure_has_bounded_diagnostic_and_no_redispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = "inc-investigator-mcp-upstream-502"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    original_send = MCPGatewayClient._send
    observed_mcp_responses: list[tuple[int, str]] = []

    async def transient_mcp_response(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await original_send(self, method, path, **kwargs)
        if method == "POST" and path == "/v1/mcp/tools/query_prometheus":
            assert response.status_code == 200
            request_id = response.headers["X-Request-ID"]
            observed_mcp_responses.append((502, request_id))
            return httpx.Response(502, json={"request_id": request_id})
        return response

    monkeypatch.setattr(MCPGatewayClient, "_send", transient_mcp_response)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        first = _start(client, incident_id, "investigation-mcp-upstream-502-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]
        replay = _start(client, incident_id, "investigation-mcp-upstream-502-0001")
        assert replay.status_code == 200 and replay.json()["run_id"] == run_id
        timeline = client.get(
            f"/v1/incidents/{incident_id}/runs/{run_id}/events",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )
        assert timeline.status_code == 200

    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    receipt = _receipts(event_payloads)[-1]
    assert observed_mcp_responses and observed_mcp_responses[0][0] == 502
    assert len(llm.requests) == 1 and len(mcp.calls) == 1
    assert receipt["status"] == "unknown"
    assert receipt["reason_code"] == "investigation_upstream_unavailable"
    assert receipt["diagnostic"] == {
        "stage": "gateway_transport",
        "kind": "transient",
        "http_status": 502,
        "request_id": observed_mcp_responses[0][1],
        "turn_count": 1,
        "collected_evidence_count": 0,
    }
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert _active_state(run_id)[0]["current_state"] == "investigating"
    assert all("diagnostic" not in event for event in timeline.json()["events"])


def test_responses_transport_timeout_after_mcp_collect_has_distinct_safe_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = "inc-investigator-responses-timeout-after-mcp"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    original_post = httpx.AsyncClient.post
    response_calls = 0

    async def timeout_second_response(self, url: Any, *args: Any, **kwargs: Any) -> httpx.Response:
        nonlocal response_calls
        if str(url).endswith("/v1/responses"):
            response_calls += 1
            if response_calls == 2:
                raise httpx.ReadTimeout(
                    "synthetic transport timeout", request=httpx.Request("POST", url)
                )
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", timeout_second_response)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        first = _start(client, incident_id, "investigation-responses-timeout-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]
        replay = _start(client, incident_id, "investigation-responses-timeout-0001")
        assert replay.status_code == 200 and replay.json()["run_id"] == run_id
        timeline = client.get(
            f"/v1/incidents/{incident_id}/runs/{run_id}/events",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )
        assert timeline.status_code == 200

    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    receipt = _receipts(event_payloads)[-1]
    assert response_calls == 2
    assert len(llm.requests) == 1 and len(mcp.calls) == 1
    assert receipt["status"] == "unknown"
    assert receipt["reason_code"] == "investigation_upstream_unavailable"
    assert receipt["diagnostic"] == {
        "stage": "gateway_transport",
        "kind": "transient",
        "http_status": None,
        "request_id": None,
        "turn_count": 1,
        "collected_evidence_count": 1,
    }
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert _active_state(run_id)[0]["current_state"] == "investigating"
    assert all("diagnostic" not in event for event in timeline.json()["events"])
    with psycopg.connect(DATABASE_URL) as connection:
        audits = connection.execute(
            "SELECT operation, response_status FROM audit_events "
            "WHERE correlation ->> 'request_id' = ANY(%s)",
            (receipt["request_ids"],),
        ).fetchall()
    assert sorted(audits) == [
        ("mcp.discovery", 200),
        ("mcp.invoke", 200),
        ("responses.create", 200),
    ]


def test_lost_mcp_response_stays_unknown_across_application_restart_and_is_not_replayed() -> None:
    incident_id = "inc-investigator-unknown"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP(lose_response=True)
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        first = _start(client, incident_id, "investigation-unknown-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]

    restarted_port = _free_port()
    restarted = _application(f"http://127.0.0.1:{restarted_port}", llm=llm, mcp=mcp)
    with (
        _serve(restarted, restarted_port) as base_url,
        httpx.Client(base_url=base_url, timeout=15) as client,
    ):
        replay = _start(client, incident_id, "investigation-unknown-0001")
        assert replay.status_code == 200
    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    receipts = _receipts(event_payloads)
    assert len(llm.requests) == 1 and len(mcp.calls) == 1
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert not any(
        event.get("transition_id") == "continue_investigation" for event in event_payloads
    )
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "unknown"),
    ]
    assert receipts[-1]["mcp_request_ids"]
    assert _active_state(run_id)[0]["current_state"] == "investigating"


def test_concurrent_idempotent_start_does_not_terminalize_active_dispatch_or_redispatch() -> None:
    incident_id = "inc-investigator-concurrent"
    _add_incident(incident_id)
    _grant_run_access()
    entered, release = threading.Event(), threading.Event()
    llm, mcp = BlockingLLM(entered, release), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url:
        with httpx.Client(base_url=base_url, timeout=15) as client:
            _add_agent_mcp_grants(client, "positive")
        with ThreadPoolExecutor(max_workers=1) as executor:
            first_future = executor.submit(
                lambda: _start_with_http(base_url, incident_id, "investigation-concurrent-0001")
            )
            assert entered.wait(10), "first request never entered the governed provider"
            with httpx.Client(base_url=base_url, timeout=15) as client:
                replay = _start(client, incident_id, "investigation-concurrent-0001")
            assert replay.status_code == 200
            _, pending_payloads = _grant_receipt_from_any_run(incident_id)
            pending = _receipts(pending_payloads)
            assert [(receipt["phase"], receipt["status"]) for receipt in pending] == [
                ("intent", "pending")
            ]
            assert llm.calls_started == 1 and llm.requests == [] and mcp.calls == []
            release.set()
            first = first_future.result(timeout=15)
    assert first.status_code == 201
    _, event_payloads = _grant_receipt_from_any_run(incident_id)
    receipts = _receipts(event_payloads)
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "success"),
    ]
    assert llm.calls_started == 2 and len(llm.requests) == 2 and len(mcp.calls) == 1


def test_restart_with_orphaned_intent_marks_unknown_without_redispatch() -> None:
    incident_id = "inc-investigator-crashed"
    _add_incident(incident_id)
    command_id = "investigation-crashed-0001"
    run_id = _create_started_run_with_pending_receipt(incident_id, command_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        replay = _start(client, incident_id, command_id)
    assert replay.status_code == 200 and replay.json()["run_id"] == run_id
    _, event_payloads = _grant_receipt_from_any_run(incident_id)
    receipts = _receipts(event_payloads)
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "unknown"),
    ]
    assert receipts[-1]["reason_code"] == "producer_interrupted"
    assert llm.requests == [] and mcp.calls == []


@pytest.mark.parametrize(
    ("final_outcome", "persisted_fields"),
    [
        (
            {"action": "request_human", "reason": "A person should review this result."},
            {"reason": "A person should review this result."},
        ),
        (
            {"action": "conclude", "summary": "The synthetic signal is accounted for."},
            {
                "summary": "The synthetic signal is accounted for.",
                "supporting_evidence": [],
            },
        ),
    ],
)
def test_event_only_outcomes_are_persisted_without_inventing_a_transition(
    final_outcome: dict[str, Any], persisted_fields: dict[str, str]
) -> None:
    incident_id = f"inc-investigator-event-only-{final_outcome['action']}"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = ScriptedLLM(final_outcome), ScriptedMCP()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "positive")
        response = _start(client, incident_id, "investigation-event-only-0001")
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        timeline = client.get(
            f"/v1/incidents/{incident_id}/runs/{run_id}/events",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )
        assert timeline.status_code == 200
    incident_state, event_payloads, _ = _database_rows(incident_id, run_id)
    run_state, run_version = _active_state(run_id)
    result_event = next(event for event in event_payloads if event.get("outcome", {}).get("action"))
    assert result_event["outcome"] == {
        "action": final_outcome["action"],
        **persisted_fields,
        "evidence_ids": result_event["outcome"]["evidence_ids"],
    }
    assert result_event["outcome"]["evidence_ids"]
    assert (
        result_event["evidence_references"][0]["evidence_id"]
        == result_event["outcome"]["evidence_ids"][0]
    )
    assert (
        result_event["evidence_references"][0]["request_id"]
        in _receipts(event_payloads)[-1]["mcp_request_ids"]
    )
    assert [
        event.get("transition_id") for event in event_payloads if event.get("transition_id")
    ] == ["start_investigation"]
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert response.json()["current_state"] == run_state["current_state"] == "investigating"
    assert run_version == 1 and _receipts(event_payloads)[-1]["status"] == "success"
    assert persisted_fields[next(iter(persisted_fields))] not in timeline.text


def _start_with_http(base_url: str, incident_id: str, idempotency_key: str) -> httpx.Response:
    with httpx.Client(base_url=base_url, timeout=15) as client:
        return _start(client, incident_id, idempotency_key)


def test_real_app_process_crash_and_success_replay_do_not_redispatch() -> None:
    crashed_incident = "inc-investigator-process-crash"
    crash_key = "investigation-process-crash-0001"
    _add_incident(crashed_incident)
    _grant_run_access()

    with _controlled_upstream(block_second_llm=True) as (upstream_url, upstream):
        first_port = _free_port()
        first_process = _spawn_application(first_port, upstream_url)
        first_pid = first_process.pid
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{first_port}", timeout=15) as client:
                _add_agent_mcp_grants(client, "positive")

            with ThreadPoolExecutor(max_workers=1) as executor:
                start_future = executor.submit(
                    _start_with_http,
                    f"http://127.0.0.1:{first_port}",
                    crashed_incident,
                    crash_key,
                )
                assert upstream.llm_blocked.wait(20), "external LLM response was not held"
                witness_at_crash = _read_witness(upstream.witness_path)
                assert witness_at_crash == [
                    {"kind": "llm", "sequence": 1},
                    {"kind": "mcp", "sequence": 1, "tool": "query_prometheus"},
                    {"kind": "llm", "sequence": 2},
                ]

                first_process.send_signal(signal.SIGKILL)
                first_exit = first_process.wait(timeout=15)
                assert first_exit == -signal.SIGKILL
                with pytest.raises(httpx.HTTPError):
                    start_future.result(timeout=10)

            upstream.release_llm.set()
            run_identity, pending_events = _grant_receipt_from_any_run(crashed_incident)
            crashed_run_id = run_identity["run_id"]
            pending_receipts = _receipts(pending_events)
            assert [(item["phase"], item["status"]) for item in pending_receipts] == [
                ("intent", "pending")
            ]

            retry_port = _free_port()
            retry_process = _spawn_application(retry_port, upstream_url)
            retry_pid = retry_process.pid
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{retry_port}", timeout=20) as client:
                    replay = _start(client, crashed_incident, crash_key)
            finally:
                retry_exit = _stop_app_process(retry_process)

            incident_state, crash_events, _ = _database_rows(crashed_incident, crashed_run_id)
            crash_receipts = _receipts(crash_events)
            run_state, run_version = _active_state(crashed_run_id)
            witness_after_retry = _read_witness(upstream.witness_path)
            assert replay.status_code == 200 and replay.json()["run_id"] == crashed_run_id
            assert [(item["phase"], item["status"]) for item in crash_receipts] == [
                ("intent", "pending"),
                ("outcome", "unknown"),
            ]
            assert crash_receipts[-1]["reason_code"] == "producer_interrupted"
            assert incident_state["state"] == "investigating"
            assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
            assert run_state["current_state"] == "investigating" and run_version == 1
            assert not any(event.get("outcome", {}).get("action") for event in crash_events)
            assert witness_after_retry == witness_at_crash
            assert upstream.counts == {"llm": 2, "mcp": 1}
            print(
                "CRASH_RESTART_PROOF "
                f"app_pid={first_pid} app_exit={first_exit} restart_pid={retry_pid} "
                f"restart_exit={retry_exit} retry_http={replay.status_code} "
                f"run_id={crashed_run_id} receipt_statuses="
                f"{[item['status'] for item in crash_receipts]} "
                f"run_state={run_state['current_state']} run_version={run_version} "
                f"upstream_witnesses={json.dumps(witness_after_retry, sort_keys=True)}"
            )
        finally:
            if first_process.poll() is None:
                first_process.kill()
                first_process.wait(timeout=10)

    successful_incident = "inc-investigator-process-success"
    success_key = "investigation-process-success-0001"
    _add_incident(successful_incident)
    with _controlled_upstream(block_second_llm=False) as (upstream_url, upstream):
        first_port = _free_port()
        first_process = _spawn_application(first_port, upstream_url)
        first_pid = first_process.pid
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{first_port}", timeout=20) as client:
                started = _start(client, successful_incident, success_key)
            assert started.status_code == 201, started.text
            success_run_id = started.json()["run_id"]
            witness_before_restart = _read_witness(upstream.witness_path)
            assert [item["kind"] for item in witness_before_restart] == ["llm", "mcp", "llm"]
        finally:
            first_exit = _stop_app_process(first_process)

        retry_port = _free_port()
        retry_process = _spawn_application(retry_port, upstream_url)
        retry_pid = retry_process.pid
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{retry_port}", timeout=20) as client:
                replay = _start(client, successful_incident, success_key)
        finally:
            retry_exit = _stop_app_process(retry_process)

        incident_state, success_events, _ = _database_rows(successful_incident, success_run_id)
        success_receipts = _receipts(success_events)
        witness_after_replay = _read_witness(upstream.witness_path)
        assert replay.status_code == 200 and replay.json()["run_id"] == success_run_id
        assert [(item["phase"], item["status"]) for item in success_receipts] == [
            ("intent", "pending"),
            ("outcome", "success"),
        ]
        assert len(incident_state["hypotheses"]) == 1 and len(incident_state["evidence"]) == 1
        assert witness_after_replay == witness_before_restart
        assert upstream.counts == {"llm": 2, "mcp": 1}
        print(
            "SUCCESS_REPLAY_PROOF "
            f"first_pid={first_pid} first_exit={first_exit} retry_pid={retry_pid} "
            f"retry_exit={retry_exit} initial_http={started.status_code} "
            f"replay_http={replay.status_code} run_id={success_run_id} "
            f"receipt_statuses={[item['status'] for item in success_receipts]} "
            f"hypotheses={len(incident_state['hypotheses'])} "
            f"evidence={len(incident_state['evidence'])} "
            f"upstream_witnesses={json.dumps(witness_after_replay, sort_keys=True)}"
        )


def test_compose_investigator_uses_the_seeded_logical_model_alias() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["api"]["environment"]["INVESTIGATOR_MODEL_ALIAS"] == ("triage-agent")


def test_final_turn_hypothesis_is_persisted_without_an_unavailable_transition() -> None:
    incident_id = "inc-investigator-final-turn"
    _add_incident(incident_id)
    _grant_run_access()
    llm, mcp = BlockingFinalTurnLLM(threading.Event(), threading.Event()), ScriptedMCP()
    llm.release.set()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=30) as client:
        _add_agent_mcp_grants(client, "positive")
        response = _start(client, incident_id, "investigation-final-turn-0001")
        detail = client.get(
            f"/v1/incidents/{incident_id}",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )
        timeline = client.get(
            f"/v1/incidents/{incident_id}/timeline",
            headers={"Authorization": f"Bearer {HUMAN_KEY}"},
        )

    assert response.status_code == 201
    assert detail.status_code == timeline.status_code == 200
    run_id = response.json()["run_id"]
    incident_state, event_payloads, decisions = _database_rows(incident_id, run_id)
    run_state, run_version = _active_state(run_id)
    receipts = _receipts(event_payloads)
    result_event = next(
        event
        for event in event_payloads
        if event.get("outcome", {}).get("action") == "propose_hypothesis"
    )
    assert len(llm.requests) == 6 and len(mcp.calls) == 5
    assert len(incident_state["hypotheses"]) == 1 and len(incident_state["evidence"]) == 5
    hypothesis = incident_state["hypotheses"][0]
    evidence = next(
        item
        for item in incident_state["evidence"]
        if item["evidence_id"] in hypothesis["supporting_evidence"]
    )
    assert hypothesis["statement"] == "A synthetic signal is confirmed on the final turn."
    assert hypothesis["confidence"] == "medium" and hypothesis["status"] == "open"
    assert hypothesis["supporting_evidence"] == [evidence["evidence_id"]]
    assert evidence["source"] == "grafana-mcp" and evidence["tool"] == "query_prometheus"
    assert evidence["datasource_uid"] == "webstore-metrics"
    assert evidence["query"] == "rate(http_requests_total[5m])"
    assert evidence["time_window"] == "now" and evidence["summary"]
    assert incident_state["state"] == run_state["current_state"] == "investigating"
    assert run_version == 1
    assert result_event["outcome"] == {
        "action": "propose_hypothesis",
        "confidence": "medium",
        "statement": "A synthetic signal is confirmed on the final turn.",
        "supporting_evidence": [result_event["evidence_references"][0]["evidence_id"]],
        "evidence_ids": [item["evidence_id"] for item in result_event["evidence_references"]],
    }
    assert len(result_event["evidence_references"]) == len(incident_state["evidence"])
    assert (
        result_event["evidence_references"][0]["evidence_id"]
        == incident_state["evidence"][0]["evidence_id"]
    )
    for reference, persisted in zip(
        result_event["evidence_references"], incident_state["evidence"], strict=True
    ):
        assert reference == {
            "evidence_id": persisted["evidence_id"],
            "source": persisted["source"],
            "tool": persisted["tool"],
            "datasource_uid": persisted["datasource_uid"],
            "query": persisted["query"],
            "time_window": persisted["time_window"],
            "summary": persisted["summary"],
            "request_id": persisted["request_id"],
        }
    assert [
        event.get("transition_id") for event in event_payloads if event.get("transition_id")
    ] == ["start_investigation"]
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "success"),
    ]
    assert receipts[-1]["result_status"] == "completed"
    assert {item["request_id"] for item in incident_state["evidence"]} == set(
        receipts[-1]["mcp_request_ids"]
    )
    assert len(decisions) == 3 and decisions[-1]["reason"] == "accepted investigation result"
    assert result_event["decision_id"] == next(
        event["decision_id"]
        for event in event_payloads
        if event.get("dispatch_receipt", {}).get("phase") == "outcome"
    )
    assert "A synthetic signal is confirmed on the final turn." not in detail.text + timeline.text
    assert evidence["query"] not in detail.text + timeline.text
    assert evidence["summary"] not in detail.text + timeline.text

    async def propose_mitigation_from_persisted_context() -> tuple[Any, Any]:
        database = Database(DATABASE_URL)
        runtime = IncidentRuntime(
            load_incident_workflow(ROOT / "agent/workflows/incident-response.yaml"),
            lambda: PostgresIncidentUnitOfWork(database),
        )
        try:
            reconstructed = await runtime.reconstruct(incident_id, run_id)
            mitigation = await runtime.execute(
                IncidentCommand(
                    command_id="investigation-final-turn-followup",
                    incident_id=incident_id,
                    run_id=run_id,
                    transition_id="propose_mitigation",
                    actor="agent",
                    outcome="propose_mitigation",
                    inputs={
                        "incident_patch": {
                            "mitigation_strategy": {
                                "mitigation_id": "mit_t10_final_turn",
                                "description": "Synthetic mitigation proposal.",
                                "steps": ["Keep the change simulated."],
                                "risk": "low",
                                "verification_check": "The synthetic signal remains stable.",
                                "approval_status": "pending",
                                "execution_mode": "simulated",
                                "based_on_hypothesis": hypothesis["hypothesis_id"],
                                "created_by": "agent",
                                "created_at": NOW.isoformat(),
                            }
                        }
                    },
                )
            )
            return reconstructed, mitigation
        finally:
            await database.dispose()

    reconstructed, mitigation = asyncio.run(propose_mitigation_from_persisted_context())
    assert reconstructed.incident_state == incident_state
    assert reconstructed.incident_version == 2 and reconstructed.run_version == 1
    assert mitigation.incident.state["state"] == "mitigating"
    assert (
        mitigation.incident.state["mitigation_strategy"]["based_on_hypothesis"]
        == hypothesis["hypothesis_id"]
    )


def test_late_investigation_result_cannot_cross_terminal_unknown_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = "inc-investigator-late-result"
    _add_incident(incident_id)
    _grant_run_access()
    entered, release = threading.Event(), threading.Event()
    llm, mcp = BlockingFinalTurnLLM(entered, release), ScriptedMCP()
    captured: dict[str, int] = {}
    original_claim = PostgresIncidentUnitOfWork.claim_run_dispatch

    async def claim_and_record_backend(
        work: PostgresIncidentUnitOfWork, *args: Any, **kwargs: Any
    ) -> str:
        result = await original_claim(work, *args, **kwargs)
        if result == "claimed":
            assert work._dispatch_connection is not None
            captured["pid"] = int(
                await work._dispatch_connection.scalar(text("SELECT pg_backend_pid()"))
            )
        return result

    monkeypatch.setattr(PostgresIncidentUnitOfWork, "claim_run_dispatch", claim_and_record_backend)
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    command_id = "investigation-late-result-0001"
    with _serve(app, port) as base_url:
        with httpx.Client(base_url=base_url, timeout=30) as client:
            _add_agent_mcp_grants(client, "positive")
        with ThreadPoolExecutor(max_workers=1) as executor:
            first_future = executor.submit(
                lambda: _start_with_http(base_url, incident_id, command_id)
            )
            assert entered.wait(15), "producer did not reach the final model response"
            with psycopg.connect(DATABASE_URL) as connection:
                terminated = connection.execute(
                    "SELECT pg_terminate_backend(%s)", (captured["pid"],)
                ).fetchone()[0]
            assert terminated is True
            with httpx.Client(base_url=base_url, timeout=15) as client:
                replay = _start(client, incident_id, command_id)
            assert replay.status_code == 200
            run_id = replay.json()["run_id"]
            _, before_events, _ = _database_rows(incident_id, run_id)
            assert [
                (receipt["phase"], receipt["status"]) for receipt in _receipts(before_events)
            ] == [("intent", "pending"), ("outcome", "unknown")]
            release.set()
            first = first_future.result(timeout=20)

    assert first.status_code == 201
    incident_state, event_payloads, decisions = _database_rows(incident_id, run_id)
    receipts = _receipts(event_payloads)
    assert len(llm.requests) == 6 and len(mcp.calls) == 5
    assert incident_state["hypotheses"] == [] and incident_state["evidence"] == []
    assert incident_state["state"] == "investigating"
    assert [
        event.get("transition_id") for event in event_payloads if event.get("transition_id")
    ] == ["start_investigation"]
    assert not any("outcome" in event for event in event_payloads)
    assert [(receipt["phase"], receipt["status"]) for receipt in receipts] == [
        ("intent", "pending"),
        ("outcome", "unknown"),
    ]
    assert len(decisions) == 3
    assert decisions[-1]["reason"] == "interrupted investigation dispatch"


def test_cancelled_dispatch_lock_commit_does_not_leave_a_pooled_session_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id, command_id = "inc-investigator-cancelled-lock", "investigation-cancelled-lock-0001"
    _add_incident(incident_id)
    run_id = _create_started_run_with_pending_receipt(incident_id, command_id)

    class CancelDuringCommit:
        def __init__(self, connection: Any) -> None:
            self.connection = connection

        def __getattr__(self, name: str) -> Any:
            return getattr(self.connection, name)

        async def commit(self) -> None:
            raise asyncio.CancelledError

    async def claim(database: Database) -> str:
        now = datetime.now(UTC)
        arguments = {
            "intent_decision": DecisionDraft("dec_cancel_intent", {}, now, run_id),
            "intent_event": EventDraft(
                "evt_cancel_intent",
                "dispatch_receipt",
                {
                    "dispatch_receipt": {
                        "dispatch_id": run_id,
                        "phase": "intent",
                        "status": "pending",
                    }
                },
                now,
            ),
            "interrupted_decision": DecisionDraft("dec_cancel_unknown", {}, now, run_id),
            "interrupted_event": EventDraft(
                "evt_cancel_unknown",
                "dispatch_receipt",
                {
                    "dispatch_receipt": {
                        "dispatch_id": run_id,
                        "phase": "outcome",
                        "status": "unknown",
                    }
                },
                now,
            ),
        }
        original_connect = AsyncEngine.connect

        async def connect_with_cancel(engine: AsyncEngine) -> Any:
            return CancelDuringCommit(await original_connect(engine))

        with monkeypatch.context() as patcher:
            patcher.setattr(AsyncEngine, "connect", connect_with_cancel)
            with pytest.raises(asyncio.CancelledError):
                async with PostgresIncidentUnitOfWork(database) as work:
                    await work.claim_run_dispatch(incident_id, run_id, **arguments)
        lock_name = PostgresIncidentUnitOfWork._dispatch_lock_name(incident_id, run_id)
        async with database.engine.connect() as connection:
            leaked = await connection.scalar(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_name, 147))"),
                {"lock_name": lock_name},
            )
            if leaked:
                await connection.scalar(
                    text("SELECT pg_advisory_unlock(hashtextextended(:lock_name, 147))"),
                    {"lock_name": lock_name},
                )
            assert leaked is False
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:lock_name, 147))"),
                {"lock_name": lock_name},
            )
            assert acquired is True
            assert (
                await connection.scalar(
                    text("SELECT pg_advisory_unlock(hashtextextended(:lock_name, 147))"),
                    {"lock_name": lock_name},
                )
                is True
            )
        return "released"

    async def exercise() -> str:
        database = Database(DATABASE_URL)
        try:
            return await claim(database)
        finally:
            await database.dispose()

    assert asyncio.run(exercise()) == "released"
