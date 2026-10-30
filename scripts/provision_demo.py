"""Prepare only explicit demo grants using the existing governed ControlService.

Run in the seed container, after the ordinary and MCP seeds. No provider/MCP
secret is needed. Revoked or conflicting grants fail closed; this is not a
second seed nor an authority repair tool. Partial progress is safe to rerun.
"""

import asyncio
import os
import sys

from provision_incident_workflow import CATALOG_BODY, _granted, build_service, provision

# The enrolled operations mitigation.execute grants are over (#722). The agent may roll
# sre-checkout back, what the demo's failure needs; the restart stays an operation it may not
# run. Not `checkout`: that is the store's service, which has no catalog.
SERVICE_OPERATIONS = {
    "sre-checkout:deployment.rollback": "Roll sre-checkout back to an earlier release.",
    "sre-checkout:deployment.restart": "Restart sre-checkout on its current release.",
}


def service_operation(resource_id, description):
    return {
        "resource_type": "service_operation",
        "resource_id": resource_id,
        "owner_id": "executor-platform",
        "source": "deploy_executor",
        "source_ref": "deploy-executor@1.0.0",
        "status": "active",
        "discoverability": {
            "display_name": resource_id,
            "visibility": "private",
            "description": description,
            "tags": ["executor", resource_id.split(":")[0]],
        },
    }


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
    # mitigation) and the postmortem text are behind run.read_context, apart from run.read.
    # The postmortem draft asks the model as the operator, through the triage-agent alias.
    for grant_id, action, resource in (
        ("grant-demo-human-run-read-context-incident-response", "run.read_context", workflow),
        (
            "grant-demo-human-invoke-triage-agent",
            "invoke",
            {"resource_type": "llm_model", "resource_id": "triage-agent"},
        ),
    ):
        yield {
            "grant_id": grant_id,
            "principal_id": "demo-human",
            "action": action,
            "resource": resource,
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
    yield {
        "grant_id": "grant-setup-agent-sre-checkout-deployment-rollback",
        "principal_id": "incident-harness",
        "action": "mitigation.execute",
        "resource": {
            "resource_type": "service_operation",
            "resource_id": "sre-checkout:deployment.rollback",
        },
        "effect": "allow",
    }


async def _already_active(service, body):
    """The same authority is already active, whatever grant id an operator gave it by hand."""
    from sre_agent.persistence.repositories import GrantRepository

    resource = body["resource"]
    async with service.sessions() as session:
        found = await GrantRepository(session).find_active(
            body["principal_id"], body["action"], resource["resource_type"], resource["resource_id"]
        )
    return found is not None


async def _cataloged(service, body):
    """The catalog holds this operation as given, whether this run or an earlier one added it."""
    from sre_agent.persistence.repositories import CatalogRepository

    async with service.sessions() as session:
        entry = await CatalogRepository(session).get(body["resource_type"], body["resource_id"])
    names = ("status", "owner_id", "source", "source_ref")
    return entry is not None and all(getattr(entry, name) == body[name] for name in names)


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
    for resource_id, description in SERVICE_OPERATIONS.items():
        body = service_operation(resource_id, description)
        response = await service.create_catalog_resource(body, bearer, "setup-v1-" + resource_id)
        # 409: an earlier run cataloged it. As given is convergence; anything else fails closed.
        if response.status_code not in (201, 409) or not await _cataloged(service, body):
            raise RuntimeError("operation catalog conflict: " + resource_id)
    for body in demo_grants():
        response = await service.create_grant(body, bearer, "setup-v1-" + body["grant_id"])
        if response.status_code == 201 and await _granted(service, body):
            continue
        # 409: the authority exists already. Active is convergence; revoked fails closed.
        if response.status_code == 409 and await _already_active(service, body):
            continue
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
