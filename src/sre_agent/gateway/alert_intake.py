"""POST /v1/alert-intake/grafana: Grafana Alerting's webhook contact point (issue #765).

Midnight builds no detection: the user's Grafana rules fire and this route records what they
send. The contact point authenticates with the integration's own secret as a Bearer value; a
wrong or missing secret gets 401 and leaves only an audit event, before the body is read. The
body, its alerts and their labels are capped. Each alert is one episode, keyed by Grafana's
fingerprint and the instant it started firing: a repeated delivery adds to the same episode and
`resolved` closes it.
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

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import AuditStore
from sre_agent.persistence.database import Database
from sre_agent.triage.service import SEVERITIES

SOURCE = "grafana"
DEFAULT_SEVERITY = "sev3"
# Grafana's conventional severity label values, and Midnight's own.
SEVERITY = {"critical": "sev1", "warning": "sev2", "info": "sev3"} | {s: s for s in SEVERITIES}
MAX_BODY_BYTES = 512 * 1024
MAX_ALERTS = 100
MAX_LABELS = 64
MAX_LABEL_KEY = 128
MAX_LABEL_VALUE = 1024
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


def _labels_fit(alert: Any) -> bool:
    labels = alert.get("labels") if isinstance(alert, dict) else None
    return not isinstance(labels, dict) or (
        len(labels) <= MAX_LABELS
        and all(
            len(str(key)) <= MAX_LABEL_KEY and len(str(value)) <= MAX_LABEL_VALUE
            for key, value in labels.items()
        )
    )


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
    labels = {str(key): str(value) for key, value in labels.items()}
    rule = (labels.get("alertname") or "grafana-alert")[:200]
    service = (labels.get("service_name") or labels.get("service") or "unknown")[:200]
    severity = SEVERITY.get(labels.get("severity", "").strip().lower(), DEFAULT_SEVERITY)
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
        *,
        secret: str,
        audit: AuditStore,
        projector: AuditProjector,
    ) -> None:
        self._database = database
        self._secret = secret.encode()
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

    async def receive(self, request: Request) -> JSONResponse:
        request_id = uuid4()
        started = monotonic()
        if not self._authentic(request.headers.get("authorization")):
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
        body = await _bounded_body(request)
        if body is None:
            return self._error(413, "payload_too_large", request_id)
        try:
            raw = json.loads(body)
        except ValueError:
            raw = None
        alerts = raw.get("alerts") if isinstance(raw, dict) else None
        if not isinstance(alerts, list):
            return self._error(422, "invalid_payload", request_id)
        if len(alerts) > MAX_ALERTS or not all(_labels_fit(alert) for alert in alerts):
            return self._error(413, "payload_too_large", request_id)
        group_key = raw.get("groupKey") if isinstance(raw.get("groupKey"), str) else None
        episodes = [episode for alert in alerts if (episode := _episode(alert, group_key))]
        try:
            recorded = [await self._record(episode) for episode in episodes]
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


async def _bounded_body(request: Request) -> bytes | None:
    """The body, or None past MAX_BODY_BYTES, by its declared length or by the bytes read."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            return None
    return bytes(body)


def alert_intake_router(service: AlertIntakeService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/alert-intake/grafana")
    async def receive(request: Request) -> JSONResponse:
        return await service.receive(request)

    return router
