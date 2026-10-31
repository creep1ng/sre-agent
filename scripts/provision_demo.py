"""Prepare only explicit demo grants using the existing governed ControlService.

Run in the seed container, after the ordinary and MCP seeds. No provider/MCP
secret is needed. A revoked setup grant is reported as drift and left revoked;
conflicting grants fail closed. This is not a second seed nor an authority repair
tool. Partial progress is safe to rerun.
"""

import asyncio
import os
import sys

from provision_incident_workflow import (
    APPROVE_GRANT_BODY,
    CATALOG_BODY,
    COMMAND_GRANT_BODY,
    GRANT_BODY,
    START_GRANT_BODY,
    _granted,
    build_service,
    provision,
)


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


async def _already_active(service, body):
    """The same authority is already active, whatever grant id an operator gave it by hand."""
    from sre_agent.persistence.repositories import GrantRepository

    resource = body["resource"]
    async with service.sessions() as session:
        found = await GrantRepository(session).find_active(
            body["principal_id"], body["action"], resource["resource_type"], resource["resource_id"]
        )
    return found is not None


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
    if existing.catalog_status != 201:
        raise RuntimeError("workflow provisioning conflict; inspect existing workflow/grants")
    for status, active, body in (
        (existing.grant_status, existing.run_read_active, GRANT_BODY),
        (existing.start_grant_status, existing.run_start_active, START_GRANT_BODY),
        (existing.command_grant_status, existing.run_command_active, COMMAND_GRANT_BODY),
        (existing.approve_grant_status, existing.run_approve_active, APPROVE_GRANT_BODY),
    ):
        if not (status == 201 and active) and not await _drifted(service, body):
            raise RuntimeError("workflow grant conflict: " + body["grant_id"])
    for body in demo_grants():
        response = await service.create_grant(body, bearer, "setup-v1-" + body["grant_id"])
        if response.status_code == 201 and await _granted(service, body):
            continue
        # The authority is active already, maybe under another id: convergence.
        if await _already_active(service, body) or await _drifted(service, body):
            continue
        raise RuntimeError("demo grant conflict: " + body["grant_id"])


async def _drifted(service, body):
    """An operator revoked this setup grant: report the drift and leave it revoked (#759)."""
    from sre_agent.persistence.repositories import GrantRepository

    async with service.sessions() as session:
        persisted = await GrantRepository(session).get(body["grant_id"])
    if persisted is None or persisted.status != "revoked":
        return False
    if await _already_active(service, body):
        return True
    print(f"seed drift: grant {body['grant_id']} is revoked; left revoked")
    return True


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
