"""Durable alert triage decisions (issue #23, chain C2a storage)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text


class TriageRepository:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def get(self, alert_id: str) -> Any | None:
        row = (
            (
                await self._session.execute(
                    text("SELECT * FROM alert_triage WHERE alert_id=:alert_id"),
                    {"alert_id": alert_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row else None

    async def write(
        self,
        *,
        alert_id: str,
        expected_version: int | None,
        status: str,
        incident_id: str | None,
        reason: str | None,
        severity: str | None,
        actor: str,
        decided_at: datetime,
    ) -> Any | None:
        params = {
            "alert_id": alert_id,
            "status": status,
            "incident_id": incident_id,
            "reason": reason,
            "severity": severity,
            "actor": actor,
            "decided_at": decided_at,
            "expected_version": expected_version,
        }
        if expected_version is None:
            result = await self._session.execute(
                text(
                    "INSERT INTO alert_triage (alert_id, status, incident_id,"
                    " expected_version, reason, severity, actor, decided_at)"
                    " VALUES (:alert_id, :status, :incident_id, 1, :reason,"
                    " :severity, :actor, :decided_at) ON CONFLICT DO NOTHING"
                ),
                params,
            )
        else:
            result = await self._session.execute(
                text(
                    "UPDATE alert_triage SET status=:status, incident_id=:incident_id,"
                    " expected_version=expected_version+1, reason=:reason,"
                    " severity=:severity, actor=:actor, decided_at=:decided_at"
                    " WHERE alert_id=:alert_id AND expected_version=:expected_version"
                ),
                params,
            )
        return await self.get(alert_id) if result.rowcount == 1 else None
