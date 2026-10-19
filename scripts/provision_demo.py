"""Prepare only explicit demo grants using the existing governed ControlService.

Run in the seed container, after the ordinary and MCP seeds. No provider/MCP
secret is needed. Revoked or conflicting grants fail closed; this is not a
second seed nor an authority repair tool. Partial progress is safe to rerun.
"""

import asyncio
import os
import sys

from provision_incident_workflow import CATALOG_BODY, _granted, build_service, provision


def demo_grants():
    workflow = {"resource_type": "incident_workflow", "resource_id": "incident-response"}
    for action in (
        "alert.read",
        "alert.triage",
        "alert.dismiss",
        "alert.associate",
        "incident.declare",
    ):
        yield {
            "grant_id": "grant-setup-human-" + action.replace(".", "-"),
            "principal_id": "demo-human",
            "action": action,
            "resource": workflow,
            "effect": "allow",
        }
    # The operator approves a mitigation it can read: the reasoning (hypothesis, evidence,
    # mitigation) is behind run.read_context, apart from run.read.
    yield {
        "grant_id": "grant-demo-human-run-read-context-incident-response",
        "principal_id": "demo-human",
        "action": "run.read_context",
        "resource": workflow,
        "effect": "allow",
    }
    for action, kind, resource in (
        ("mcp.discovery", "mcp_server", "grafana-mcp"),
        ("mcp.invoke", "mcp_tool", "query_prometheus"),
        ("mcp.invoke", "mcp_tool", "query_elasticsearch"),
    ):
        yield {
            "grant_id": "grant-setup-agent-" + resource,
            "principal_id": "incident-harness",
            "action": action,
            "resource": {"resource_type": kind, "resource_id": resource},
            "effect": "allow",
        }


async def provision_demo(service, bearer):
    from sre_agent.persistence.repositories import CatalogRepository

    existing = await provision(service, bearer)
    async with service.sessions() as session:
        catalog = await CatalogRepository(session).get("incident_workflow", "incident-response")
    if catalog is None or any(
        getattr(catalog, name) != CATALOG_BODY[name]
        for name in ("status", "owner_id", "source", "source_ref")
    ):
        raise RuntimeError("workflow catalog conflict; retain state and review through domain API")
    if not all(
        (
            existing.catalog_status == 201,
            existing.grant_status == 201,
            existing.start_grant_status == 201,
            existing.command_grant_status == 201,
            existing.approve_grant_status == 201,
            existing.run_read_active,
            existing.run_start_active,
            existing.run_command_active,
            existing.run_approve_active,
        )
    ):
        raise RuntimeError("workflow provisioning conflict; inspect existing workflow/grants")
    for body in demo_grants():
        response = await service.create_grant(body, bearer, "setup-v1-" + body["grant_id"])
        # 409 with the same active grant already persisted is convergence, not a conflict.
        if response.status_code not in (201, 409) or not await _granted(service, body):
            raise RuntimeError("demo grant conflict: " + body["grant_id"])


async def main():
    from sre_agent.persistence.database import Database

    if not all(
        os.environ.get(name) for name in ("DATABASE_URL", "ADMIN_HUMAN_API_KEY", "AUDIT_HMAC_KEY")
    ):
        print("provision: database/admin/audit configuration required", file=sys.stderr)
        return 2
    db = Database(os.environ["DATABASE_URL"])
    try:
        await provision_demo(
            build_service(db, os.environ["AUDIT_HMAC_KEY"].encode()),
            "Bearer " + os.environ["ADMIN_HUMAN_API_KEY"],
        )
    except Exception:
        # Third-party exception text may contain connection details or credentials.
        print(
            "provision: conflict/unavailable; inspect domain state, then rerun; "
            "no cleanup performed",
            file=sys.stderr,
        )
        return 1
    finally:
        await db.dispose()
    print("demo permissions converged; restricted identity unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
