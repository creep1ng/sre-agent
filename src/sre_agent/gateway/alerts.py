"""GET /v1/alerts: fixed server-owned rules evaluated through the governed Grafana MCP path.

``alert.read`` gates the list; each rule runs through ``MCPGatewayService.invoke`` with the
caller's credential, so ``mcp.invoke`` authorization and audit are unchanged. Callers never
supply PromQL. A firing rule becomes one canonical alert (incident-state ``$defs/alert``) whose
id derives from the instant this process first saw the episode firing: stable across polls,
new after recovery. Episodes are in memory; an API restart starts a new one.
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

DETECTOR = "sre-agent-alert-rules"
WORKFLOW = ("incident_workflow", "incident-response")


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


def _error_ratio(service: str, span: str, window: str) -> str:
    calls = f'traces_span_metrics_calls_total{{service_name="{service}",span_name="{span}"'
    errors = f'{calls},status_code="STATUS_CODE_ERROR"}}'
    return f"sum(increase({errors}[{window}])) / sum(increase({calls}}}[{window}]))"


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
        self._episodes: dict[str, datetime] = {}

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
                started = self._episodes.setdefault(rule.rule_id, evaluated_at)
                alerts.append(self._alert(rule, value, started, evaluated_at))
            elif state == "ok":
                self._episodes.pop(rule.rule_id, None)
            rules.append({"rule_id": rule.rule_id, "state": state, "value": value})
        return JSONResponse(
            {"evaluated_at": _iso(evaluated_at), "rules": rules, "alerts": alerts},
            headers={"Cache-Control": "no-store"},
        )

    @staticmethod
    def _alert(
        rule: AlertRule, value: float, started: datetime, evaluated_at: datetime
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
            f" (threshold {rule.threshold:.0%})",
            "source": SOURCE,
            "origin": {
                "signal": rule.signal,
                "condition": f"{rule.rule_id}: error ratio {value:.2f} > {rule.threshold}",
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
