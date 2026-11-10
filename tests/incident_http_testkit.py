"""Helpers shared by the PostgreSQL-backed incident HTTP tests."""

from typing import Any

from database_support import DATABASE_URL
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.settings import Settings


def _client() -> TestClient:
    return TestClient(create_application(Settings(DATABASE_URL)))


def _assert_run_lookup_is_scoped(
    statements: list[tuple[str, Any]], *, incident_id: str, run_id: str
) -> None:
    run_queries = [
        (statement.lower(), parameters)
        for statement, parameters in statements
        if "from incident.runs" in statement.lower()
    ]
    assert run_queries
    for statement, parameters in run_queries:
        normalized = " ".join(statement.split())
        assert "where run_id=" in normalized and "and incident_id=" in normalized, normalized
        assert run_id in str(parameters)
        assert incident_id in str(parameters)
    assert not any(
        "from incident.snapshots" in query.lower() or "from incident.run_events" in query.lower()
        for query, _ in statements
    )
