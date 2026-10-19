"""Live alert inbox over the governed MCP path, written before the endpoint.

Failure modes: anonymous caller; no alert.read; no mcp.invoke on query_prometheus; MCP
unavailable; empty result; malformed sample; id changing within an episode or reused by the
next; unaudited evaluation; an alert triage cannot declare. Real PostgreSQL, seeds, grants and
audit; only the Grafana MCP upstream is scripted.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.mcp import MCPUpstreamUnavailable
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed, seed_mcp_demo
from sre_agent.settings import Settings

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from provision_demo import provision_demo  # noqa: E402
from provision_incident_workflow import build_service  # noqa: E402

URL = os.environ["TEST_DATABASE_URL"]
NAMES = ("ADMIN_HUMAN", "DEMO_HUMAN", "INCIDENT_HARNESS", "RESTRICTED_HARNESS")
KEYS = {
    name + "_API_KEY": "sre_" + prefix + "0123456789abcdefghijklmnopqrstuv"
    for name, prefix in zip(NAMES, ("admin", "human", "agent", "deny0"), strict=True)
}
ROUTE = (("MODEL", "openai/gpt-4o-mini"), ("PROVIDER", "openai"))
ALERT_KEYS = {"alert_id", "service", "severity", "status", "observed_at", "summary", "source"}


class ScriptedMCP:
    def __init__(self) -> None:
        self.next: Any = {"data": []}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        if isinstance(self.next, Exception):
            raise self.next
        return self.next


def ratio(value: str) -> dict[str, Any]:
    return {"data": [{"metric": {}, "value": [1792380000.0, value]}]}


def prepare_database() -> None:
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        for (table,) in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'"):
            conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        conn.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", URL)
    command.upgrade(cfg, "head")
    routes = {f"{a}_AGENT_{p}": v for a in ("TRIAGE", "REMEDIATION") for p, v in ROUTE}
    settings = SeedSettings.from_environment({**KEYS, **routes})

    async def prepare() -> None:
        db = Database(URL)
        try:
            await seed(db, settings)
            await seed_mcp_demo(db)
            await provision_demo(
                build_service(db, b"x" * 32), "Bearer " + KEYS["ADMIN_HUMAN_API_KEY"]
            )
        finally:
            await db.dispose()

    asyncio.run(prepare())


def mcp_invocations() -> int:
    with psycopg.connect(URL) as conn:
        sql = "SELECT count(*) FROM audit_events WHERE operation='mcp.invoke'"
        return conn.execute(sql).fetchone()[0]


def test_live_alerts_are_governed_stable_per_episode_and_triageable() -> None:
    prepare_database()
    mcp = ScriptedMCP()
    app = create_application(
        settings=Settings(
            database_url=URL,
            audit_hmac_key="x" * 32,
            grafana_mcp_endpoint="http://grafana-mcp:8000/mcp",
            grafana_mcp_token="scripted-token",
        ),
        mcp_client=mcp,
    )
    with TestClient(app) as client:

        def alerts(key: str | None = "DEMO_HUMAN_API_KEY") -> Any:
            headers = {"Authorization": "Bearer " + KEYS[key]} if key else {}
            return client.get("/v1/alerts", headers=headers)

        # Anonymous and ungranted callers never reach the upstream.
        assert alerts(None).status_code == 401
        denied = alerts("RESTRICTED_HARNESS_API_KEY")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "not_authorized"
        # incident-harness may invoke MCP but has no alert.read.
        assert alerts("INCIDENT_HARNESS_API_KEY").status_code == 403
        assert mcp.calls == []

        # No traffic: empty result is "no data", never an invented alert.
        audited = mcp_invocations()
        empty = alerts()
        assert empty.status_code == 200, empty.text
        assert empty.json()["alerts"] == []
        assert [rule["state"] for rule in empty.json()["rules"]] == ["no_data"]
        assert mcp_invocations() == audited + 1
        assert mcp.calls[-1][0] == "query_prometheus"

        # Healthy traffic below the threshold.
        mcp.next = ratio("0")
        assert alerts().json()["alerts"] == []

        # Upstream down: retryable 503, nothing invented.
        mcp.next = MCPUpstreamUnavailable()
        down = alerts()
        assert (down.status_code, down.json()["retryable"]) == (503, True)
        assert down.json()["error"]["code"] == "alert_source_unavailable"

        # Malformed samples fail closed.
        for malformed in (
            {"data": [{"metric": {}, "value": [1792380000.0, "not-a-number"]}]},
            {"data": [{"metric": {}}]},
            {"data": [{"metric": {}, "value": [1, "1"]}, {"metric": {}, "value": [1, "1"]}]},
        ):
            mcp.next = malformed
            bad = alerts()
            assert bad.status_code == 502, malformed
            assert bad.json()["error"]["code"] == "alert_source_invalid"

        # Firing: one canonical alert, same id and observed_at on every poll.
        mcp.next = ratio("1")
        first = alerts()
        assert first.status_code == 200, first.text
        [alert] = first.json()["alerts"]
        assert set(alert) == ALERT_KEYS | {"origin"}
        assert (alert["service"], alert["severity"], alert["status"]) == ("checkout", "sev1", "new")
        assert first.json()["rules"][0]["state"] == "firing"
        [again] = alerts().json()["alerts"]
        assert {k: again[k] for k in ("alert_id", "observed_at")} == {
            k: alert[k] for k in ("alert_id", "observed_at")
        }

        # A window without samples keeps the open episode listed (no flapping).
        mcp.next = {"data": []}
        gap = alerts().json()
        assert gap["rules"][0]["state"] == "no_data"
        assert [item["alert_id"] for item in gap["alerts"]] == [alert["alert_id"]]
        assert "no samples" in gap["alerts"][0]["origin"]["condition"]
        mcp.next = ratio("1")

        # Triage accepts the live id and the operator-confirmed alert facts.
        context = {key: alert[key] for key in ("service", "summary", "observed_at", "source")}
        declared = client.post(
            f"/v1/alerts/{alert['alert_id']}/triage/commands",
            headers={
                "Authorization": "Bearer " + KEYS["DEMO_HUMAN_API_KEY"],
                "Idempotency-Key": "live-alert-declare-" + os.urandom(8).hex(),
            },
            json={
                "operation": "triage_declare",
                "expected_version": 1,
                "reason": "Checkout cannot charge payments.",
                "severity": "sev1",
                "impact": "Customers cannot pay.",
                "alert_context": {**context, "severity": alert["severity"]},
            },
        )
        assert declared.status_code == 201, declared.text

        # Resolution ends the episode; the next one gets a new id.
        mcp.next = ratio("0")
        assert alerts().json()["alerts"] == []
        mcp.next = ratio("1")
        [next_episode] = alerts().json()["alerts"]
        assert next_episode["alert_id"] != alert["alert_id"]

        # Without mcp.invoke on query_prometheus the governed path denies.
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(
                "UPDATE grants SET status='revoked'"
                " WHERE grant_id='grant-demo-human-mcp-query-prometheus'"
            )
        calls = len(mcp.calls)
        forbidden = alerts()
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "alert_source_forbidden"
        assert len(mcp.calls) == calls
