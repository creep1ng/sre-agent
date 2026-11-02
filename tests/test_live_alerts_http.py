"""Live alert inbox, written before the endpoint; since #765 its alerts come from intake.

Failure modes: anonymous caller; no alert.read; an alert invented without a delivery; id
changing within an episode or reused by the next; a resolved episode left in the live list; an
alert triage cannot declare; a triage decision missing from the list, reported without its
incident, or carried over to the next episode; the demo's own checkout alerting under a service
name a store rule also emits (#722). Real PostgreSQL, seeds, grants and audit; Grafana's
deliveries are posted to intake, whose operator is unset so the console triages. With
LIVE_ALERTS_TRANSCRIPT set, the GET /v1/alerts bodies of the triage journey are written there
as the review artifact.
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
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
SECRET = "grafana-intake-" + "s" * 24
# Relative to now: the list keeps an episode resolved only within the last day.
NOW = datetime.now(UTC).replace(microsecond=0)


def ago(minutes: int) -> str:
    return (NOW - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def grafana(status: str, service: str, starts_at: str, rule: str = "service-error-rate") -> Any:
    """One Grafana Alerting webhook delivery with a single alert."""
    alert = {
        "status": status,
        "fingerprint": f"{rule}-{service}",
        "startsAt": starts_at,
        "endsAt": ago(60) if status == "resolved" else "0001-01-01T00:00:00Z",
        "labels": {"alertname": rule, "service_name": service, "severity": "critical"},
        "annotations": {"summary": f"{service}: 100% of spans failed over the last 2 min."},
    }
    return {"groupKey": f"{rule}:{service}", "status": status, "alerts": [alert]}


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


def test_live_alerts_are_governed_stable_per_episode_and_triageable() -> None:
    prepare_database()
    app = create_application(
        settings=Settings(
            database_url=URL,
            audit_hmac_key="x" * 32,
            alert_intake_secret=SECRET,
            alert_intake_principal_id=None,
        )
    )
    with TestClient(app) as client:

        def deliver(payload: Any) -> None:
            headers = {"Authorization": "Bearer " + SECRET}
            response = client.post("/v1/alert-intake/grafana", json=payload, headers=headers)
            assert response.status_code == 200, response.text

        def alerts(key: str | None = "DEMO_HUMAN_API_KEY") -> Any:
            headers = {"Authorization": "Bearer " + KEYS[key]} if key else {}
            return client.get("/v1/alerts", headers=headers)

        # Anonymous and ungranted callers see nothing.
        assert alerts(None).status_code == 401
        denied = alerts("RESTRICTED_HARNESS_API_KEY")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "not_authorized"
        # incident-harness may invoke MCP but has no alert.read.
        assert alerts("INCIDENT_HARNESS_API_KEY").status_code == 403

        # Nothing delivered: an empty list, never an invented alert.
        empty = alerts()
        assert empty.status_code == 200, empty.text
        assert (empty.json()["alerts"], empty.json()["resolved"]) == ([], [])

        # Firing: one canonical alert, same id and observed_at on every poll and redelivery.
        deliver(grafana("firing", "checkout", ago(90)))
        first = alerts()
        assert first.status_code == 200, first.text
        [alert] = first.json()["alerts"]
        assert set(alert) == ALERT_KEYS | {"origin", "triage_status", "incident_id"}
        assert (alert["service"], alert["severity"], alert["status"]) == ("checkout", "sev1", "new")
        assert (alert["triage_status"], alert["incident_id"]) == ("new", None)
        assert alert["origin"]["condition"] == "service-error-rate: firing"
        deliver(grafana("firing", "checkout", ago(90)))
        [again] = alerts().json()["alerts"]
        assert {k: again[k] for k in ("alert_id", "observed_at")} == {
            k: alert[k] for k in ("alert_id", "observed_at")
        }

        # Triage accepts the live id and the operator-confirmed alert facts.
        def command(alert_id: str, operation: str, **body: Any) -> Any:
            return client.post(
                f"/v1/alerts/{alert_id}/triage/commands",
                headers={
                    "Authorization": "Bearer " + KEYS["DEMO_HUMAN_API_KEY"],
                    "Idempotency-Key": f"live-alert-{operation}-" + os.urandom(8).hex(),
                },
                json={"operation": operation, "expected_version": 1, **body},
            )

        transcript: list[dict[str, Any]] = []

        def listed(alert_id: str, step: str) -> tuple[str, str | None]:
            body = alerts().json()
            transcript.append({"step": step, "response": body})
            [item] = body["alerts"]
            assert item["alert_id"] == alert_id
            return item["triage_status"], item["incident_id"]

        assert listed(alert["alert_id"], "firing, untriaged") == ("new", None)
        context = {key: alert[key] for key in ("service", "summary", "observed_at", "source")}
        declared = command(
            alert["alert_id"],
            "triage_declare",
            reason="Checkout cannot charge payments.",
            severity="sev1",
            impact="Customers cannot pay.",
            alert_context={**context, "severity": alert["severity"]},
        )
        assert declared.status_code == 201, declared.text
        incident_id = declared.json()["incident_id"]
        assert listed(alert["alert_id"], "after triage_declare") == ("declared", incident_id)

        # Resolution ends the episode; the next one gets a new id.
        deliver(grafana("resolved", "checkout", ago(90)))
        ended = alerts().json()
        assert ended["alerts"] == []
        assert [item["alert_id"] for item in ended["resolved"]] == [alert["alert_id"]]
        deliver(grafana("firing", "checkout", ago(30)))
        [next_episode] = alerts().json()["alerts"]
        assert next_episode["alert_id"] != alert["alert_id"]

        # The next episode starts untriaged; opening and dismissing it show in the list.
        assert listed(next_episode["alert_id"], "next episode") == ("new", None)
        opened = command(next_episode["alert_id"], "open_triage")
        assert opened.status_code == 200, opened.text
        assert listed(next_episode["alert_id"], "after open_triage") == ("triaging", None)
        dismissed = command(next_episode["alert_id"], "triage_dismiss", reason="Load test noise.")
        assert dismissed.status_code == 200, dismissed.text
        assert listed(next_episode["alert_id"], "after triage_dismiss") == ("dismissed", None)
        if path := os.environ.get("LIVE_ALERTS_TRANSCRIPT"):
            Path(path).write_text(json.dumps(transcript, indent=2) + "\n")

        # The demo's own checkout alerts as sre-checkout, which no store rule emits (#722).
        rule = "sre-checkout-orders-error-rate"
        deliver(grafana("firing", "sre-checkout", ago(29), rule))
        [ours] = [item for item in alerts().json()["alerts"] if item["service"] == "sre-checkout"]
        assert ours["origin"]["condition"] == f"{rule}: firing"
