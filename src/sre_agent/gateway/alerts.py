"""GET /v1/alerts: the alert episodes that came in through intake (issue #765).

``alert.read`` gates the list. Midnight evaluates no rule of its own: the user's Grafana sends
its alerts to ``POST /v1/alert-intake/grafana`` and every episode recorded there is listed here
under its episode id: firing ones in ``alerts``, the live view, and those resolved in the last
day in ``resolved``, so a consumer tells them apart without leaving the canonical alert shape
(incident-state ``$defs/alert``). Each alert carries its triage decision (incident-state 1.1.0)
read from the triage store: an episode intake declared or linked shows up as such, one intake
could not open stays ``new`` for the operator.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access

INTAKE_DETECTOR = "grafana-alerting"
WORKFLOW = ("incident_workflow", "incident-response")
# Triage store status -> alert triage_status; an alert without a stored decision is `new`.
TRIAGE_STATUS = {
    "open": "triaging",
    "declared": "declared",
    "linked": "linked",
    "dismissed": "dismissed",
}
_EPISODES = text("""
SELECT e.*, t.status AS triage, t.incident_id AS triage_incident_id
FROM incident.alert_episodes e LEFT JOIN alert_triage t ON t.alert_id = e.episode_id
WHERE e.status = 'firing' OR e.resolved_at > now() - interval '1 day'
ORDER BY e.last_received_at DESC LIMIT 100""")


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class LiveAlertsService:
    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions

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
        evaluated_at = datetime.now(UTC)
        try:
            async with self._sessions() as session:
                episodes = [self._episode(row) for row in await session.execute(_EPISODES)]
        except Exception:
            return self._error(request_id, 503, "storage_unavailable", True)
        alerts = [alert for firing, alert in episodes if firing]
        resolved = [alert for firing, alert in episodes if not firing]
        return JSONResponse(
            {"evaluated_at": _iso(evaluated_at), "alerts": alerts, "resolved": resolved},
            headers={"Cache-Control": "no-store"},
        )

    @staticmethod
    def _episode(row: Any) -> tuple[bool, dict[str, Any]]:
        """One intake episode as a canonical alert, and whether it is still firing."""
        row = row._mapping
        firing = row["status"] == "firing"
        resolved = row["resolved_at"] or row["last_received_at"]
        return firing, {
            "alert_id": row["episode_id"],
            "service": row["service"],
            "severity": row["severity"],
            "status": "new",
            "observed_at": _iso(row["starts_at"]),
            "summary": row["summary"],
            "source": row["source"],
            "origin": {
                "signal": row["rule"],
                "condition": f"{row['rule']}: "
                + ("firing" if firing else f"resolved at {_iso(resolved)}"),
                "detector": INTAKE_DETECTOR,
                "observed_at": _iso(row["last_received_at"]),
            },
            "triage_status": TRIAGE_STATUS.get(row["triage"], "new"),
            "incident_id": row["triage_incident_id"],
        }


def alerts_router(service: LiveAlertsService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/alerts")
    async def list_alerts(request: Request) -> JSONResponse:
        return await service.list_alerts(request.headers.get("authorization"))

    return router
