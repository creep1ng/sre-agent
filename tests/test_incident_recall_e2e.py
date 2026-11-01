"""Issue #773 end to end: a closed incident is recalled, with its source, by the next one.

Real FastAPI over HTTP and real PostgreSQL; the model and the Grafana MCP answer are scripted
unless RECALL_REAL_LLM=1, which sends the investigations after the first to OpenRouter. The
first incident is investigated and closed through the postmortem flow. Ways this can fail:
1. The second investigation of the same service and signal does not receive the memory, or
   receives it without the postmortem it came from, so the citation links nowhere.
2. The recorded hypothesis cites the memory, but the incident evidence does not keep the link.
3. A memory the outcome does not cite is still kept as evidence of the current incident.
4. A service without history receives the memories of another service, or can cite one.
5. The extra latency and prompt size of recall go unmeasured.
The run leaves `recall.json` in RECALL_ARTIFACT_DIR/issue-773 (default: the temp dir).
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from typing import Any

import httpx
import psycopg
from test_incident_investigator_http import (  # noqa: F401  (module fixture)
    AUDIT_KEY,
    DATABASE_URL,
    HUMAN_KEY,
    NOW,
    SEED_ENV,
    ScriptedMCP,
    _add_agent_mcp_grants,
    _free_port,
    _grant_run_access,
    _incident,
    _serve,
    migrated_database,
)
from test_incident_memory_e2e import ARTIFACTS, CONTENT, _grant_context_read

from sre_agent.application import create_application
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.memories import PostgresIncidentMemoryRepository
from sre_agent.settings import Settings

REAL = os.environ.get("RECALL_REAL_LLM") == "1"
SIGNAL = "checkout.requests"
SUMMARY = (
    "sre-checkout orders failing: 42% errors over the last 30s (threshold 10%). Evidence:"
    " Prometheus datasource webstore-metrics, metric checkout_requests_total with"
    ' service_namespace="sre-agent" and service_name="sre-checkout": http_response_status_code'
    " counts the answers and service_version names the release that served them."
)
ROLLBACK = CONTENT["strategy"]
APPROVE = {
    "action": "run.approve",
    "resource": {"type": "incident_workflow", "id": "incident-response"},
}
FAILING = [{"metric": {"service_version": "1.5.0", "code": "500"}, "value": [0, "0.42"]}]


def add_incident(incident_id: str, service: str) -> None:
    state = _incident(incident_id)
    state["alert"] |= {
        "alert_id": f"alt-{incident_id}",
        "service": service,
        "summary": SUMMARY.replace("sre-checkout", service),
        "origin": {"signal": SIGNAL},
    }

    async def add() -> None:
        database = Database(DATABASE_URL)
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(incident_id, state, now=NOW)
        await database.dispose()

    asyncio.run(add())


def application(base_url: str, llm: Any) -> Any:
    settings = Settings.from_environment(
        SEED_ENV
        | {
            "DATABASE_URL": DATABASE_URL,
            "AUDIT_HMAC_KEY": AUDIT_KEY,
            "INVESTIGATOR_GATEWAY_URL": base_url,
            "INVESTIGATOR_GATEWAY_API_KEY": SEED_ENV["INCIDENT_HARNESS_API_KEY"],
            "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
            "INVESTIGATOR_OUTPUT_LANGUAGE": "en",
        }
    )
    return create_application(
        settings, llm_provider=llm, mcp_client=ScriptedMCP(response={"data": {"result": FAILING}})
    )


def incident_state(incident_id: str) -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state FROM incident.incidents WHERE incident_id=%s", (incident_id,)
        ).fetchone()
    return row[0]


class Operator:
    """The demo human driving the incident flow over HTTP, as the console does."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.auth = {"Authorization": f"Bearer {HUMAN_KEY}"}
        _grant_context_read()

    def detail(self, incident_id: str) -> dict[str, Any]:
        response = self.client.get(f"/v1/incidents/{incident_id}", headers=self.auth)
        assert response.status_code == 200, response.text
        return response.json()

    def start(self, incident_id: str, objective: str) -> str:
        response = self.client.post(
            f"/v1/incidents/{incident_id}/runs",
            headers=self.auth | {"Idempotency-Key": f"memory-{objective}-{incident_id}"},
            json={"workflow_version": "1.0.0", "objective": objective},
        )
        assert response.status_code == 201, response.text
        return response.json()["run_id"]

    def command(self, incident_id: str, run_id: str, command: str, **extra: Any) -> None:
        body = {
            "command": command,
            "expected_incident_version": self.detail(incident_id)["version"],
            "actor": "human",
            "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
            **extra,
        }
        response = self.client.post(
            f"/v1/incidents/{incident_id}/runs/{run_id}/commands",
            headers=self.auth | {"Idempotency-Key": f"memory-{command}-{run_id}"},
            json=body,
        )
        assert response.status_code in {200, 201, 202}, response.text

    def close_with_postmortem(self, incident_id: str, run_id: str) -> None:
        """Approve, verify, write and approve the postmortem, then close."""
        self.command(incident_id, run_id, "approve_mitigation")
        self.command(incident_id, run_id, "verification_passed")
        postmortem_run = self.start(incident_id, "postmortem")
        with psycopg.connect(DATABASE_URL) as connection:
            [(event_id,)] = connection.execute(
                "SELECT event_id FROM incident.run_events WHERE run_id=%s", (postmortem_run,)
            ).fetchall()
        cited = [{"event_id": event_id, "description": "Postmortem opened."}]
        content = CONTENT | {"timeline": cited, "actions_taken": cited}
        path = f"/v1/incidents/{incident_id}/postmortem"
        draft = {"expected_version": 0, "content": content}
        assert self.client.put(path, headers=self.auth, json=draft).status_code == 201
        review = {"version": 1, "outcome": "approved"}
        reviewed = self.client.post(f"{path}/reviews", headers=self.auth, json=review)
        assert reviewed.status_code == 201
        self.command(incident_id, postmortem_run, "close_incident", authorization=APPROVE)
        assert self.detail(incident_id)["state"] == "closed"


def _state_of(prompt: str) -> dict[str, Any]:
    return json.loads(prompt.split("State: ", 1)[1].splitlines()[0])


class RecallLLM:
    """Evidence, a hypothesis citing it and each memory, then the mitigation a memory names.
    With a real provider, every incident after the first goes to it."""

    def __init__(self, real: Any = None) -> None:
        self.requests: list[ProviderRequest] = []
        self.results: list[tuple[str, ProviderResult]] = []
        self.real = real
        self.foreign: str | None = None  # sre-checkout's memory, cited once by sre-payments

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        state = _state_of(request.input)
        incident = state["incident"]
        if self.real is not None and incident["incident_id"] != "inc-recall-first":
            result = await self.real.create(request)
            self.results.append((incident["incident_id"], result))
            return result
        evidence = state["collected_evidence"] + incident["evidence"]
        memories = [item for item in evidence if item["source"] == "incident_memory"]
        observed = [item["evidence_id"] for item in evidence if item not in memories]
        if not incident["hypotheses"] and not observed:
            expr = "sum by (service_version) (rate(checkout_requests_total[5m]))"
            arguments = {
                "datasource_uid": "webstore-metrics",
                "expr": expr,
                "query_type": "instant",
            }
            action: dict[str, Any] = {
                "action": "use_tool",
                "tool": "query_prometheus",
                "arguments": arguments | {"end_time": "now"},
            }
        elif not incident["hypotheses"]:
            cited = observed[:1]
            if incident["incident_id"] != "inc-recall-uncited":
                cited += [item["evidence_id"] for item in memories]
            if incident["incident_id"] == "inc-recall-other" and "rejected" not in request.input:
                cited += [self.foreign] if self.foreign else []
            action = {
                "action": "propose_hypothesis",
                "statement": "Release 1.5.0 of the service answers HTTP 500 on orders.",
                "confidence": "high",
                "supporting_evidence": cited,
            }
        else:
            applied = [
                line.removeprefix("Mitigation approved: ").split(" Steps: ")[0]
                for item in memories
                for line in item["summary"].splitlines()
                if line.startswith("Mitigation approved: ")
            ]
            action = {
                "action": "propose_mitigation",
                "description": applied[0] if applied else ROLLBACK,
                "steps": ["Roll back the deployment to 1.4.0."],
                "risk": "low",
                "verification_check": "The 5xx ratio of checkout_requests_total returns to 0.",
                "based_on_hypothesis": incident["hypotheses"][0]["hypothesis_id"],
            }
        reply = {"response_id": f"resp_recall_{len(self.requests):04d}", "text": json.dumps(action)}
        return ProviderResult(model=request.model, provider=request.provider, **reply)


def _inputs(llm: RecallLLM, incident_id: str) -> list[str]:
    return [r.input for r in llm.requests if f'"incident_id": "{incident_id}"' in r.input]


def _references(incident_id: str) -> list[str]:
    """Evidence ids the incident's investigation_result events reference."""
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT payload->'evidence_references' FROM incident.run_events"
            " WHERE incident_id=%s AND kind='investigation_result'",
            (incident_id,),
        ).fetchall()
    return [item["evidence_id"] for (references,) in rows for item in references or []]


def _recall_latency_ms(rounds: int = 20) -> list[float]:
    async def measure() -> list[float]:
        database = Database(DATABASE_URL)
        timings = []
        for _ in range(rounds):
            async with database.sessions() as session:
                began = time.perf_counter()
                await PostgresIncidentMemoryRepository(session).recall(
                    "sre-checkout", SIGNAL, SUMMARY, "inc-recall-latency"
                )
                timings.append((time.perf_counter() - began) * 1000)
        await database.dispose()
        return timings

    return asyncio.run(measure())


def _cited(state: dict[str, Any]) -> list[str]:
    return [ref for hyp in state["hypotheses"] for ref in hyp["supporting_evidence"]]


def test_a_closed_incident_is_recalled_with_its_source_by_the_same_service_only() -> None:
    real = None
    if REAL:
        client = httpx.AsyncClient(base_url="https://openrouter.ai", timeout=60)
        real = OpenRouterProvider(client, api_key=os.environ["OPENROUTER_API_KEY"])
    llm = RecallLLM(real)
    _grant_run_access()
    for incident_id, service in (
        ("inc-recall-first", "sre-checkout"),
        ("inc-recall-second", "sre-checkout"),
        ("inc-recall-other", "sre-payments"),
        ("inc-recall-uncited", "sre-checkout"),
    ):
        add_incident(incident_id, service)
    port = _free_port()
    with (
        _serve(application(f"http://127.0.0.1:{port}", llm), port) as base_url,
        httpx.Client(base_url=base_url, timeout=120) as client,
    ):
        _add_agent_mcp_grants(client, "recall")
        operator = Operator(client)

        # 1. The first incident is investigated without memory and closed through the postmortem.
        first_run = operator.start("inc-recall-first", "investigate")
        assert "incident_memory" not in json.dumps(incident_state("inc-recall-first")["evidence"])
        operator.close_with_postmortem("inc-recall-first", first_run)
        [change] = client.get("/v1/incident-memory/changes", headers=operator.auth).json()[
            "changes"
        ]
        memory_evidence = llm.foreign = f"ev_{change['memory_id']}"

        # 2. Same service and signal: the memory reaches the investigator with its source record.
        operator.start("inc-recall-second", "investigate")
        second_input = _inputs(llm, "inc-recall-second")[0]
        recalled = [
            item
            for item in _state_of(second_input)["collected_evidence"]
            if item["source"] == "incident_memory"
        ]
        assert [(item["evidence_id"], item["query"]) for item in recalled] == [
            (memory_evidence, change["source_record"])
        ]
        second = incident_state("inc-recall-second")
        kept = {item["evidence_id"]: item for item in second["evidence"]}
        assert kept[memory_evidence]["query"] == change["source_record"]
        assert memory_evidence in _cited(second), second["hypotheses"]
        assert memory_evidence in _references("inc-recall-second")
        mitigation = (second.get("mitigation_strategy") or {}).get("description")

        # 3. Another service with the same words receives nothing from sre-checkout, and the
        # scripted model's citation of sre-checkout's existing memory is rejected.
        operator.start("inc-recall-other", "investigate")
        other_inputs = _inputs(llm, "inc-recall-other")
        assert other_inputs and not any("incident_memory" in text for text in other_inputs)
        other = incident_state("inc-recall-other")
        other_memories = [item for item in other["evidence"] if item["source"] == "incident_memory"]
        assert other_memories == []
        uncitable = None
        if not REAL:
            rejected = f"unknown references: {memory_evidence}"
            assert any(rejected in text for text in other_inputs)
            assert memory_evidence not in _cited(other) + _references("inc-recall-other")
            uncitable = {"rejected": rejected, "recorded": _cited(other)}

        # 4. A recalled memory the outcome does not cite stays out of the incident's evidence.
        uncited_report = None
        if not REAL:
            operator.start("inc-recall-uncited", "investigate")
            recalled_ids = [
                item["evidence_id"]
                for item in _state_of(_inputs(llm, "inc-recall-uncited")[0])["collected_evidence"]
                if item["source"] == "incident_memory"
            ]
            assert recalled_ids == [memory_evidence]
            uncited = incident_state("inc-recall-uncited")
            kept = [item["evidence_id"] for item in uncited["evidence"]]
            assert memory_evidence not in kept + _references("inc-recall-uncited")
            uncited_report = {"recalled": recalled_ids, "kept_evidence": kept}

    # 5. What recall costs: the query, and the prompt it adds to every turn.
    with psycopg.connect(DATABASE_URL) as connection:
        [(table_rows,)] = connection.execute(
            "SELECT count(*) FROM incident.incident_memories"
        ).fetchall()
    latency = _recall_latency_ms()
    with_memory, no_memory = len(second_input), len(_inputs(llm, "inc-recall-other")[0])
    report = {
        "memory_change": change,
        "second_investigation": {
            "recalled": [
                {"evidence_id": item["evidence_id"], "query": item["query"]} for item in recalled
            ],
            "hypotheses": second["hypotheses"],
            "mitigation": mitigation,
        },
        "other_service_memories": len(other_memories),
        "uncitable": uncitable,
        "uncited": uncited_report,
        "mode": "openrouter" if REAL else "scripted",
        "cost": {
            "recall_query_ms": {
                "p50": round(statistics.median(latency), 2),
                "max": round(max(latency), 2),
                "rounds": len(latency),
                "table_rows": table_rows,
            },
            "first_turn_input_chars": {"with_memory": with_memory, "without_memory": no_memory},
            "extra_tokens_per_turn_estimate": round((with_memory - no_memory) / 4),
            "provider_usage": [
                {"incident_id": incident_id} | result.consumption.model_dump(mode="json")
                for incident_id, result in llm.results
                if result.consumption is not None
            ],
        },
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "recall.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
