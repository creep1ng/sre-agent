"""CA2/4/6 controlled HTTP/PostgreSQL journey, authored before provisioner.

Failure modes: missing direct agent MCP grants; inherited human authority;
operator lacks triage/run grants; restricted identity gains authority; repeat
rotates credentials/duplicates grants/loses incidents; revoked grants silently
reactivated; provisioning errors leak credentials. No external or paid calls.
"""

import asyncio
import os
import sys
from pathlib import Path

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
KEYS = {
    name: "sre_" + prefix + "0123456789abcdefghijklmnopqrstuv"
    for name, prefix in zip(
        (
            "ADMIN_HUMAN_API_KEY",
            "DEMO_HUMAN_API_KEY",
            "INCIDENT_HARNESS_API_KEY",
            "RESTRICTED_HARNESS_API_KEY",
        ),
        ("admin", "human", "agent", "deny0"),
        strict=True,
    )
}


def test_demo_permissions_converge_and_http_journey_remains_governed():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        for (table,) in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'"):
            conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        conn.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", URL)
    command.upgrade(cfg, "head")
    settings = SeedSettings.from_environment(
        {
            **KEYS,
            "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
            "TRIAGE_AGENT_PROVIDER": "openai",
            "REMEDIATION_AGENT_MODEL": "openai/gpt-4o-mini",
            "REMEDIATION_AGENT_PROVIDER": "openai",
        }
    )

    async def prepare():
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

    def snapshot():
        with psycopg.connect(URL) as conn:
            return tuple(
                conn.execute(sql).fetchall()
                for sql in (
                    "SELECT principal_id FROM principals ORDER BY 1",
                    "SELECT credential_id,key_hash FROM credentials ORDER BY 1",
                    "SELECT grant_id,status FROM grants ORDER BY 1",
                    "SELECT incident_id,state FROM incident.incidents ORDER BY 1",
                )
            )

    app = create_application(settings=Settings(database_url=URL, audit_hmac_key="x" * 32))
    with TestClient(app) as client:

        def request(method, path, key="DEMO_HUMAN_API_KEY", body=None):
            headers = {
                "Authorization": "Bearer " + KEYS[key],
                "Idempotency-Key": "setup-proof-" + os.urandom(12).hex(),
            }
            response = client.request(method, path, headers=headers, json=body)
            print(f"{key.removesuffix('_API_KEY')}: {method} {path} -> HTTP {response.status_code}")
            return response

        triage = {"operation": "open_triage", "expected_version": 1}
        path = "/v1/alerts/al-setup-proof/triage/commands"
        assert request("POST", path, "RESTRICTED_HARNESS_API_KEY", triage).status_code == 403
        assert request("POST", path, body=triage).status_code == 200
        declared = request(
            "POST",
            path,
            body={
                "operation": "triage_declare",
                "expected_version": 1,
                "severity": "sev2",
                "reason": "Controlled setup proof",
                "impact": "Synthetic checkout errors",
                "alert_context": {
                    "service": "checkout",
                    "summary": "Synthetic alert",
                    "observed_at": "2026-10-13T10:00:00-05:00",
                    "source": "setup-proof",
                    "severity": "sev2",
                },
            },
        )
        assert declared.status_code == 201, declared.text
        incident = declared.json()["incident_id"]
        started = request(
            "POST",
            f"/v1/incidents/{incident}/runs",
            body={"workflow_version": "1.0.0", "objective": "investigate"},
        )
        assert started.status_code == 201, started.text
        run = started.json()["run_id"]
        for suffix in ("", "/events"):
            path = f"/v1/incidents/{incident}/runs/{run}" + suffix
            assert request("GET", path).status_code == 200
            assert request("GET", path, "RESTRICTED_HARNESS_API_KEY").status_code == 403
        audit = request("GET", "/v1/audit-events?principal_id=demo-human", "ADMIN_HUMAN_API_KEY")
        assert audit.status_code == 200
        before = snapshot()
        asyncio.run(prepare())
        assert snapshot() == before
        with psycopg.connect(URL) as conn:
            grants = conn.execute(
                "SELECT action,resource_id FROM grants WHERE "
                "principal_id='incident-harness' AND action LIKE 'mcp.%'"
            ).fetchall()
            assert set(grants) == {
                ("mcp.discovery", "grafana-mcp"),
                ("mcp.invoke", "query_prometheus"),
                ("mcp.invoke", "query_elasticsearch"),
            }
            conn.execute(
                "UPDATE grants SET status='revoked' WHERE grant_id='grant-setup-human-alert-read'"
            )
        asyncio.run(prepare())
        with psycopg.connect(URL) as conn:
            status = conn.execute(
                "SELECT status FROM grants WHERE grant_id='grant-setup-human-alert-read'"
            ).fetchone()
            assert status == ("revoked",), "revoked grant must not be restored"
            conn.execute(
                "UPDATE grants SET status='active' WHERE grant_id='grant-setup-human-alert-read'"
            )
            conn.execute(
                "UPDATE resources SET status='inactive' WHERE "
                "resource_type='incident_workflow' AND resource_id='incident-response'"
            )
        try:
            asyncio.run(prepare())
        except RuntimeError as error:
            assert "workflow" in str(error)
        else:
            raise AssertionError("inactive workflow must not be presented as ready")
    print("CA2/4/6: convergence, real triage/run reads, audit and denial passed (no LLM).")
