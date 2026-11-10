"""Builders shared by the PostgreSQL-backed triage tests."""

from datetime import UTC, datetime

from sre_agent.governance.dto import Principal

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def _principal(pid: str) -> Principal:
    return Principal(
        principal_id=pid,
        kind="human",
        display_name=pid,
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
