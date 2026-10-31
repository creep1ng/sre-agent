"""GET /v1/alerts: fixed server-owned rules evaluated through the governed Grafana MCP path.

``alert.read`` gates the list; each rule runs through ``MCPGatewayService.invoke`` with the
caller's credential, so ``mcp.invoke`` authorization and audit are unchanged. Callers never
supply PromQL. A firing rule becomes one canonical alert (incident-state ``$defs/alert``) whose
id derives from the instant this process first saw the episode firing: stable across polls,
new after recovery. A window without samples keeps an open episode listed with its last
value (no flapping); only an ``ok`` evaluation ends it. Episodes are in memory; an API restart
starts a new one. The summary also says where the rule's evidence lives (metric, labels, log
index and field): it is the only alert text an investigation receives, and without it the
model guessed field names, found nothing and the run ended without a mitigation. Each listed
alert carries its triage decision (incident-state 1.1.0) read from the triage store.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.gateway.mcp import MCPGatewayService
from sre_agent.incident.signals import SOURCE
from sre_agent.triage.store import TriageRepository

DETECTOR = "sre-agent-alert-rules"
WORKFLOW = ("incident_workflow", "incident-response")
# Triage store status -> alert triage_status; an alert without a stored decision is `new`.
TRIAGE_STATUS = {
    "open": "triaging",
    "declared": "declared",
    "linked": "linked",
    "dismissed": "dismissed",
}


@dataclass(frozen=True, slots=True)
class AlertRule:
    rule_id: str
    description: str
    service: str
    severity: str
    signal: str
    window: str
    threshold: float
    expr: str
    evidence: str


def _evidence_hint(service: str, span: str) -> str:
    return (
        "Evidence: Prometheus datasource webstore-metrics, metric traces_span_metrics_calls_total"
        f' with service_name="{service}", span_name="{span}" and status_code="STATUS_CODE_ERROR"'
        " for the errors; logs in datasource webstore-logs, index otel-logs-*, field"
        f' resource.service.name:"{service}".'
    )


def _error_ratio(service: str, span: str, window: str) -> str:
    calls = f'traces_span_metrics_calls_total{{service_name="{service}",span_name="{span}"'
    errors = f'{calls},status_code="STATUS_CODE_ERROR"}}'
    return f"sum(increase({errors}[{window}])) / sum(increase({calls}}}[{window}]))"


_ORDERS = 'checkout_requests_total{service_namespace="sre-agent",service_name="sre-checkout"'
RULES = (
    AlertRule(
        rule_id="checkout-payment-error-rate",
        description="checkout payment calls failing",
        service="checkout",
        severity="sev1",
        signal="oteldemo.PaymentService/Charge",
        window="2m",
        threshold=0.05,
        expr=_error_ratio("checkout", "oteldemo.PaymentService/Charge", "2m"),
        evidence=_evidence_hint("checkout", "oteldemo.PaymentService/Charge"),
    ),
    # The demo's second service (#721) pushes its own counter every 5 s, so 30 s is a full
    # window; span metrics flush every 60 s, too late for an alert within a minute of a deploy.
    # A healthy release has no 5xx series at all, hence `or vector(0)`: only an `ok` evaluation
    # closes an episode, and a missing numerator would read as no data.
    AlertRule(
        rule_id="checkout-orders-error-rate",
        description="sre-checkout orders failing",
        service="sre-checkout",
        severity="sev2",
        signal="checkout.requests",
        window="30s",
        threshold=0.1,
        expr=f'(sum(increase({_ORDERS},http_response_status_code=~"5.."}}[30s])) or vector(0))'
        f" / sum(increase({_ORDERS}}}[30s]))",
        evidence="Evidence: Prometheus datasource webstore-metrics, metric checkout_requests_total"
        ' with service_namespace="sre-agent" and service_name="sre-checkout":'
        " http_response_status_code counts the answers and service_version names the release"
        " that served them. The service sends no logs and no traces. Its recent deploys and"
        " rollbacks: tool midnight_recent_changes with service sre-checkout.",
    ),
)


class AlertSourceInvalid(Exception):
    """The governed MCP answer is not one numeric sample (or none)."""


def _sample(result: dict[str, Any]) -> float | None:
    rows = result.get("result")
    if not isinstance(rows, list) or len(rows) > 1:
        raise AlertSourceInvalid
    if not rows:
        return None
    value = rows[0].get("value") if isinstance(rows[0], dict) else None
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[1], str):
        raise AlertSourceInvalid
    try:
        number = float(value[1])
    except ValueError:
        raise AlertSourceInvalid from None
    return None if math.isnan(number) else number


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class LiveAlertsService:
    def __init__(self, sessions: Any, mcp: MCPGatewayService | None) -> None:
        self._sessions = sessions
        self._mcp = mcp
        self._episodes: dict[str, tuple[datetime, float]] = {}

    def _error(self, request_id: str, status: int, code: str, retryable: bool) -> JSONResponse:
        headers = {"Retry-After": "15"} if retryable else {}
        headers |= {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        return JSONResponse(
            {
                "error": {"code": code, "message": code.replace("_", " ").capitalize() + "."},
                "request_id": request_id,
                "retryable": retryable,
            },
            status_code=status,
            headers=headers,
        )

    async def list_alerts(self, authorization: str | None) -> JSONResponse:
        request_id = str(uuid4())
        try:
            _, evaluation = await authorize_governed_access(
                self._sessions, authorization, "alert.read", *WORKFLOW
            )
        except AuthenticationFailed:
            return self._error(request_id, 401, "authentication_failed", False)
        except Exception:
            return self._error(request_id, 503, "storage_unavailable", True)
        if evaluation.decision.decision != "allow":
            return self._error(request_id, 403, "not_authorized", False)
        if self._mcp is None:
            return self._error(request_id, 503, "alert_source_unavailable", True)
        evaluated_at = datetime.now(UTC)
        alerts: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        for rule in RULES:
            response = await self._mcp.invoke(
                "query_prometheus",
                {
                    "datasource_uid": "webstore-metrics",
                    "expr": rule.expr,
                    "query_type": "instant",
                    "end_time": "now",
                },
                authorization,
            )
            if response.status_code in {401, 403}:
                return self._error(request_id, 403, "alert_source_forbidden", False)
            if response.status_code in {503, 504}:
                return self._error(request_id, 503, "alert_source_unavailable", True)
            try:
                if response.status_code != 200:
                    raise AlertSourceInvalid
                value = _sample(json.loads(response.body))
            except (AlertSourceInvalid, ValueError):
                return self._error(request_id, 502, "alert_source_invalid", False)
            state = "no_data" if value is None else "ok"
            if value is not None and value > rule.threshold:
                state = "firing"
                started = self._episodes.get(rule.rule_id, (evaluated_at, value))[0]
                self._episodes[rule.rule_id] = (started, value)
            elif state == "ok":
                self._episodes.pop(rule.rule_id, None)
            if rule.rule_id in self._episodes:
                started, last = self._episodes[rule.rule_id]
                alerts.append(self._alert(rule, last, started, evaluated_at, stale=value is None))
            rules.append({"rule_id": rule.rule_id, "state": state, "value": value})
        try:
            await self._attach_triage(alerts)
        except Exception:
            return self._error(request_id, 503, "storage_unavailable", True)
        return JSONResponse(
            {"evaluated_at": _iso(evaluated_at), "rules": rules, "alerts": alerts},
            headers={"Cache-Control": "no-store"},
        )

    async def _attach_triage(self, alerts: list[dict[str, Any]]) -> None:
        if not alerts:
            return
        async with self._sessions() as session:
            repository = TriageRepository(session)
            for alert in alerts:
                decision = await repository.get(alert["alert_id"]) or {}
                alert["triage_status"] = TRIAGE_STATUS.get(decision.get("status"), "new")
                alert["incident_id"] = decision.get("incident_id")

    @staticmethod
    def _alert(
        rule: AlertRule, value: float, started: datetime, evaluated_at: datetime, stale: bool
    ) -> dict[str, Any]:
        episode = f"{rule.rule_id}:{started.isoformat()}".encode()
        fingerprint = hashlib.sha256(episode).hexdigest()[:12]
        return {
            "alert_id": f"alt-{rule.service}-{fingerprint}",
            "service": rule.service,
            "severity": rule.severity,
            "status": "new",
            "observed_at": _iso(started),
            "summary": f"{rule.description}: {value:.0%} errors over the last {rule.window}"
            f" (threshold {rule.threshold:.0%}). {rule.evidence}",
            "source": SOURCE,
            "origin": {
                "signal": rule.signal,
                "condition": f"{rule.rule_id}: error ratio {value:.2f} > {rule.threshold}"
                + (" (last value; no samples in the latest window)" if stale else ""),
                "detector": DETECTOR,
                "observed_at": _iso(evaluated_at),
            },
        }


def alerts_router(service: LiveAlertsService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/alerts")
    async def list_alerts(request: Request) -> JSONResponse:
        return await service.list_alerts(request.headers.get("authorization"))

    return router
