"""POST /v1/alert-intake/grafana: Grafana Alerting's webhook contact point (issue #765).

Midnight builds no detection: the user's Grafana rules fire and this route records what they
send. The contact point authenticates with the integration's own secret as a Bearer value; a
wrong or missing secret gets 401 and leaves only an audit event. Each alert is one episode,
keyed by Grafana's fingerprint and the instant it started firing: a repeated delivery adds to
the same episode and `resolved` closes it. A new firing episode joins the open incident of its
notification group or service, or else declares one through the triage command, which starts
the investigation (#704); the dispatch runs after the response, as the console's declare does.
The integration acts for one configured operator, and the triage decision names `grafana` as
the responsible system, so the timeline never claims a human decided it.
"""

import hashlib
import hmac
import json
import logging
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import String

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import AuditStore
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import PrincipalRepository
from sre_agent.triage.service import (
    ELIGIBLE,
    SEVERITIES,
    InvestigationDispatcher,
    TriageError,
    TriageService,
)

SOURCE = "grafana"
DEFAULT_SEVERITY = "sev3"
_FRACTION = re.compile(r"(\.\d{6})\d+")
_SLUG = re.compile(r"[^a-z0-9]+")
_log = logging.getLogger(__name__)

_UPSERT = text("""
INSERT INTO incident.alert_episodes (episode_id, source, fingerprint, starts_at, rule, service,
  severity, status, summary, labels, group_key, received_count, first_received_at,
  last_received_at, resolved_at)
VALUES (:episode_id, :source, :fingerprint, :starts_at, :rule, :service, :severity, :status,
  :summary, CAST(:labels AS jsonb), :group_key, 1, :now, :now, :resolved_at)
ON CONFLICT (source, fingerprint, starts_at) DO UPDATE SET
  received_count = alert_episodes.received_count + 1,
  last_received_at = EXCLUDED.last_received_at,
  status = CASE WHEN alert_episodes.status = 'resolved' THEN 'resolved' ELSE EXCLUDED.status END,
  resolved_at = COALESCE(alert_episodes.resolved_at, EXCLUDED.resolved_at)
RETURNING *""")
# The incident a new episode joins: one still open, opened by an episode of the same notification
# group or the same service that is still firing.
_TARGET = text("""
SELECT e.incident_id FROM incident.alert_episodes e
JOIN incident.incidents i ON i.incident_id = e.incident_id
WHERE e.status = 'firing' AND e.episode_id <> :episode_id
  AND (e.group_key = :group_key OR e.service = :service)
  AND i.state->>'state' = ANY(:states)
ORDER BY e.first_received_at LIMIT 1""").bindparams(bindparam("states", type_=ARRAY(String())))
_OPENED = text(
    "UPDATE incident.alert_episodes SET incident_id = :incident_id,"
    " investigation_run_id = :run_id WHERE episode_id = :episode_id"
)


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or value.startswith("0001-"):
        return None
    try:
        moment = datetime.fromisoformat(_FRACTION.sub(r"\1", value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(UTC) if moment.tzinfo is not None else None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _episode(alert: Any, group_key: str | None) -> dict[str, Any] | None:
    """Normalize one Grafana alert; None when it lacks what an episode needs."""
    if not isinstance(alert, dict):
        return None
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    fingerprint = alert.get("fingerprint")
    starts_at = _instant(alert.get("startsAt"))
    status = alert.get("status")
    if not isinstance(fingerprint, str) or not 1 <= len(fingerprint) <= 128 or starts_at is None:
        return None
    if status not in {"firing", "resolved"}:
        return None
    labels = {str(key): str(value)[:200] for key, value in labels.items()}
    rule = (labels.get("alertname") or "grafana-alert")[:200]
    service = (labels.get("service_name") or labels.get("service") or "unknown")[:200]
    severity = labels.get("severity")
    if severity not in SEVERITIES:
        severity = DEFAULT_SEVERITY
    summary = " ".join(
        part for part in (_text(annotations, "summary"), _text(annotations, "description")) if part
    )
    digest = hashlib.sha256(f"{SOURCE}\0{fingerprint}\0{_iso(starts_at)}".encode()).hexdigest()
    slug = _SLUG.sub("-", service.lower()).strip("-")[:24] or "service"
    return {
        "episode_id": f"alt-{slug}-{digest[:16]}",
        "source": SOURCE,
        "fingerprint": fingerprint,
        "starts_at": starts_at,
        "rule": rule,
        "service": service,
        "severity": severity,
        "status": status,
        "summary": (summary or f"Grafana rule {rule} is {status} on {service}.")[:2000],
        "labels": labels,
        "group_key": group_key,
        "resolved_at": _instant(alert.get("endsAt")) if status == "resolved" else None,
    }


class AlertIntakeService:
    def __init__(
        self,
        database: Database,
        workflow: IncidentWorkflow,
        investigator: InvestigationDispatcher | None,
        *,
        secret: str,
        principal_id: str,
        audit: AuditStore,
        projector: AuditProjector,
    ) -> None:
        self._database = database
        self._triage = TriageService(database, workflow)
        self._investigator = investigator
        self._secret = secret.encode()
        self._principal_id = principal_id
        self._audit = audit
        self._projector = projector

    def _authentic(self, authorization: str | None) -> bool:
        scheme, _, value = (authorization or "").partition(" ")
        return scheme.casefold() == "bearer" and hmac.compare_digest(
            value.strip().encode(), self._secret
        )

    @staticmethod
    def _error(status: int, code: str, request_id: Any) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        return JSONResponse(
            {"error": {"code": code}, "request_id": str(request_id), "retryable": status == 503},
            status_code=status,
            headers=headers,
        )

    async def receive(
        self, raw: Any, authorization: str | None, background: BackgroundTasks
    ) -> JSONResponse:
        request_id = uuid4()
        started = monotonic()
        if not self._authentic(authorization):
            try:
                await self._audit.append(
                    self._projector.control_event(
                        request_id,
                        401,
                        max(0, int((monotonic() - started) * 1000)),
                        "authentication",
                        operation="credentials.authenticate",
                        action="authenticate",
                        reason="authentication_failed",
                    )
                )
            except Exception:
                _log.exception("alert intake: the rejected delivery could not be audited")
            return self._error(401, "authentication_failed", request_id)
        alerts = raw.get("alerts") if isinstance(raw, dict) else None
        if not isinstance(alerts, list):
            return self._error(422, "invalid_payload", request_id)
        group_key = raw.get("groupKey") if isinstance(raw.get("groupKey"), str) else None
        episodes = [episode for alert in alerts if (episode := _episode(alert, group_key))]
        try:
            async with self._database.sessions() as session:
                principal = await PrincipalRepository(session).get(self._principal_id)
            if principal is None or principal.status != "active":
                return self._error(503, "intake_operator_unavailable", request_id)
            recorded = [await self._record(episode) for episode in episodes]
            for row in recorded:
                if row["status"] == "firing" and row["incident_id"] is None:
                    await self._open_or_join(row, principal, background)
        except Exception:
            _log.exception("alert intake: storage failed")
            return self._error(503, "storage_unavailable", request_id)
        keys = ("episode_id", "status", "received_count", "incident_id")
        episodes = [{key: row[key] for key in keys} for row in recorded]
        return JSONResponse({"request_id": str(request_id), "episodes": episodes})

    async def _record(self, episode: dict[str, Any]) -> dict[str, Any]:
        values = episode | {"labels": json.dumps(episode["labels"]), "now": datetime.now(UTC)}
        async with self._database.transaction() as session:
            return dict((await session.execute(_UPSERT, values)).mappings().one())

    async def _open_or_join(
        self, row: dict[str, Any], principal: Any, background: BackgroundTasks
    ) -> None:
        keys = ("episode_id", "group_key", "service")
        lookup = {key: row[key] for key in keys} | {"states": sorted(ELIGIBLE)}
        async with self._database.transaction() as session:
            target = (await session.execute(_TARGET, lookup)).scalar_one_or_none()
        # Every input below comes from the stored episode, so a redelivery after a crash
        # replays the same triage command instead of conflicting with it.
        command: dict[str, Any] = {
            "alert_id": row["episode_id"],
            "expected_version": 1,
            "idempotency_key": f"grafana-intake:{row['episode_id']}",
            "responsible_system": SOURCE,
        }
        if target is not None:
            command |= {
                "operation": "triage_link",
                "reason": f"Grafana rule {row['rule']} on {row['service']} joins open incident.",
                "target_incident_id": target,
            }
        else:
            command |= {
                "operation": "triage_declare",
                "reason": f"Grafana rule {row['rule']} fired on {row['service']}.",
                "severity": row["severity"],
                "impact": f"Grafana rule {row['rule']} is firing on {row['service']}.",
                "alert_context": {
                    "service": row["service"],
                    "summary": row["summary"],
                    "observed_at": _iso(row["starts_at"]),
                    "source": SOURCE,
                    "severity": row["severity"],
                },
            }
        try:
            result = await self._triage.execute(principal, **command)
        except TriageError as error:
            # The episode stays in the inbox without an incident; the operator decides.
            _log.warning("alert intake: %s not opened: %s", row["episode_id"], error.code)
            return
        incident_id, run_id = result.incident_id, result.investigation_run_id
        opened = {"episode_id": row["episode_id"], "incident_id": incident_id, "run_id": run_id}
        async with self._database.transaction() as session:
            await session.execute(_OPENED, opened)
        row["incident_id"] = incident_id
        if not result.replayed and incident_id and run_id and self._investigator is not None:
            background.add_task(self._investigator.dispatch, incident_id, run_id)


def alert_intake_router(service: AlertIntakeService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/alert-intake/grafana")
    async def receive(request: Request, background: BackgroundTasks) -> JSONResponse:
        try:
            raw = await request.json()
        except Exception:
            raw = None
        return await service.receive(raw, request.headers.get("authorization"), background)

    return router
