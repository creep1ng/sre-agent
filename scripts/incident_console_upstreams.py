#!/usr/bin/env python3
"""API of the RC-2 incident page journeys (#870, #708, #709): the real application, with the
model and Grafana MCP scripted. Each model reply waits STEP_SECONDS, so the console sees the run
work.

The model reads the metrics, the logs and, when it is offered, the service's recent changes,
then proposes a hypothesis citing all of them with a verdict and a finding each, and a rollback:
in words for a service with no catalog, as `deployment.rollback` to 1.4.0 for an enrolled one.
An enrolled service whose alert carries `[e2e:reinicio]` gets `deployment.restart` instead.
An alert whose summary carries `[e2e:falla]` gets two replies that are not JSON first, so its
first investigation ends with `investigation_invalid_output` and a human retry succeeds. The
hypothesis carries a short title when the prompt asks for one; `[e2e:titulo]` gets a title on
two lines and over 60 characters, which the API drops.

The `postmortem` objective (#711) gets the four narrative sections, written from the facts it
was given; `[e2e:sin-borrador]` gets a reply that is not JSON, so the draft composed from the
record stands.
"""

import asyncio
import json
import os
import re
import secrets
from collections import Counter

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

STEP_SECONDS = float(os.environ.get("STEP_SECONDS", "2"))
STATE = re.compile(r"^State: (.*)$", re.MULTILINE)
FACTS = re.compile(r"^Facts: (.*)$", re.MULTILINE)
CHANGES = "midnight_recent_changes"
ERRORS = (
    'increase(traces_span_metrics_calls_total{{service_name="{}",'
    'status_code="STATUS_CODE_ERROR"}}[5m])'
)
FINDINGS = {
    "query_prometheus": "Unos 9,8 errores en 5 min tanto en `Charge` como en `PlaceOrder`",
    "query_elasticsearch": "Los cobros fallan con `context deadline exceeded`",
    CHANGES: "`checkout` desplegó la `1.5.0` minutos antes de la alerta",
}
# As long as the walkthrough's real hypothesis (2026-11-02): in labelled lines when the prompt
# asks for them (#870), else in one paragraph as before.
PARTS = (
    "el despliegue de `checkout` `1.5.0` rompió los cobros contra `payment`.",
    "la `1.5.0` llama a `oteldemo.PaymentService/Charge` con un plazo de 200 ms; `payment` tarda "
    "más, la llamada vence con `context deadline exceeded` y `oteldemo.CheckoutService/PlaceOrder` "
    "termina con `STATUS_CODE_ERROR`, lo que eleva la tasa de spans con error de `checkout`.",
    "que `payment` también falle sin pasar por `checkout`, o que los errores empiecen antes del "
    "despliegue de la `1.5.0`.",
)


def title(summary: str) -> str:
    """The incident's short title (#870); `[e2e:titulo]` gets one the API must refuse."""
    if "[e2e:titulo]" in summary:
        return "Fallan los cobros en checkout\nporque el despliegue 1.5.0 vence el plazo de payment"
    return "Fallan los cobros en checkout"


def statement(prompt: str) -> str:
    labels = ("Causa", "Mecanismo", "La refutaría")
    if "**Causa:**" in prompt:
        return "\n".join(f"**{label}:** {part}" for label, part in zip(labels, PARTS, strict=True))
    labels = ("Causa", "Mecanismo", "Observación que la refutaría")
    return " ".join(f"{label}: {part}" for label, part in zip(labels, PARTS, strict=True))


failures: Counter[str] = Counter()


def arguments(tool: str, service: str) -> dict:
    if tool == "query_prometheus":
        return {"datasource_uid": "webstore-metrics", "query_type": "instant", "end_time": "now",
                "expr": f"sum by (span_name) ({ERRORS.format(service)})"}  # fmt: skip
    if tool == "query_elasticsearch":
        return {"datasource_uid": "webstore-logs", "index": "otel-logs-*", "limit": 10,
                "query": f'resource.service.name:"{service}"', "start_time": "now-15m",
                "end_time": "now"}  # fmt: skip
    return {"service": service}


def decide(state: dict, prompt: str) -> dict:
    incident, collected = state["incident"], state["collected_evidence"]
    if incident["hypotheses"]:
        # An enrolled service (#722) is mitigated with one of its catalog operations.
        offers = (state.get("service_operations") or {}).get("operations", [])
        offered = {item["operation"] for item in offers}
        service = incident["alert"]["service"]
        operation = (
            {"service": service, "operation": "deployment.rollback",
             "parameters": {"to_tag": "1.4.0"}}
            if "deployment.rollback" in offered else None
        )  # fmt: skip
        # A rollback runs once: `[e2e:reinicio]` asks for the restart, which runs every time (#710).
        if "[e2e:reinicio]" in incident["alert"]["summary"] and "deployment.restart" in offered:
            operation = {"service": service, "operation": "deployment.restart", "parameters": {}}
        return {
            "action": "propose_mitigation",
            **({"operation": operation} if operation else {}),
            "description": "Volver `checkout` a la `1.4.0`",
            "steps": [
                "Desplegar de nuevo la `1.4.0` de `checkout`.",
                "Vigilar las llamadas con error de `checkout`.",
            ],
            "risk": "low",
            "verification_check": "Las llamadas con error de checkout vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
        }
    tools = ["query_prometheus", "query_elasticsearch"] + ([CHANGES] if CHANGES in prompt else [])
    for tool in tools:
        if tool not in {item["tool"] for item in collected}:
            service = incident["alert"]["service"]
            return {"action": "use_tool", "tool": tool, "arguments": arguments(tool, service)}
    return {
        "action": "propose_hypothesis",
        **({"title": title(incident["alert"]["summary"])} if '"title"' in prompt else {}),
        "statement": statement(prompt),
        "confidence": "medium",
        "supporting_evidence": [item["evidence_id"] for item in collected],
        "verdicts": {
            item["evidence_id"]: {"verdict": "supports", "finding": FINDINGS[item["tool"]]}
            for item in collected
        },
    }


def postmortem(prompt: str) -> str:
    facts = json.loads(FACTS.findall(prompt)[-1])
    if "[e2e:sin-borrador]" in (facts["alert"]["summary"] or ""):
        return "Esta respuesta no es JSON."
    service, ran = facts["alert"]["service"], facts["mitigation"]["ran"] or {}
    return json.dumps({
        "what_happened": f"Los clientes no pudieron pagar: `{service}` fallaba al cobrar.",
        "probable_cause": "El despliegue de `checkout` `1.5.0` rompió los cobros contra "
        "`payment`; la investigación lo sustentó con métricas, logs y cambios recientes.",
        "what_we_did": f"Una persona aprobó {facts['mitigation']['plan']}; el deploy-executor "
        f"lo ejecutó ({ran.get('outcome')}).",
        "how_we_verified": "Una persona confirmó que el servicio quedó estable.",
    })  # fmt: skip


class ScriptedModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        await asyncio.sleep(STEP_SECONDS)
        if "Objective: postmortem" in request.input:
            text = postmortem(request.input)
            return ProviderResult(
                response_id=f"resp_{secrets.token_hex(8)}",
                model=request.model,
                text=text,
                provider=request.provider,
            )
        state = json.loads(STATE.findall(request.input)[-1])
        incident = state["incident"]
        text = json.dumps(decide(state, request.input))
        if "[e2e:falla]" in incident["alert"]["summary"] and failures[incident["incident_id"]] < 2:
            failures[incident["incident_id"]] += 1
            text = "Esta respuesta no es JSON."
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=text,
            provider=request.provider,
        )


# What the OTel demo's log index returns: whole documents, resource attributes included, so a
# summary is cut at 8000 characters as in a real run.
RESOURCE = {
    "host.arch": "amd64", "host.name": "ip-10-0-0-12", "os.type": "linux",
    "service.namespace": "opentelemetry-demo", "service.version": "1.5.0",
    "telemetry.sdk.language": "go", "telemetry.sdk.name": "opentelemetry",
}  # fmt: skip
LOGS = [
    ("ERROR", "failed to charge card: rpc error: code = DeadlineExceeded desc = context deadline"),
    ("ERROR", "[PlaceOrder] payment failed: context deadline exceeded"),
    ("INFO", "[PlaceOrder] user_id=4f1c currency=USD"),
]  # fmt: skip


def documents(service: str) -> list[dict]:
    return [
        {
            "_index": "otel-logs-2026-11-02",
            "_source": {
                "@timestamp": f"2026-11-02T22:0{7 - index // 3}:{59 - index:02d}.{index:03d}Z",
                "body": body,
                "resource": {**RESOURCE, "service.name": service},
                "severity": {"text": level},
                "traceId": secrets.token_hex(16),
            },
        }
        for index, (level, body) in enumerate(LOGS * 7)
    ]


class ScriptedMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name == "query_elasticsearch":
            service = re.search(r'"([^"]+)"', arguments.get("query", "")) or None
            return {"total": 20, "documents": documents(service[1] if service else "checkout")}
        by = "span_name" if "span_name" in arguments.get("expr", "") else "service_name"
        series = (
            {"oteldemo.PaymentService/Charge": "9.758699999999997",
             "oteldemo.CheckoutService/PlaceOrder": "9.758699999999997"}
            if by == "span_name"
            else {"checkout": "12", "frontend": "24.5", "payment": "0"}
        )  # fmt: skip
        return {
            "resultType": "vector",
            "result": [
                {"metric": {by: name}, "value": [1761800000, value]}
                for name, value in series.items()
            ],
        }


if __name__ == "__main__":
    application = create_application(llm_provider=ScriptedModel(), mcp_client=ScriptedMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
