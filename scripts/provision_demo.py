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
        "change.read",
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
        ("change.read", "incident_workflow", "incident-response"),
    ):
        yield {
            "grant_id": "grant-setup-agent-" + resource,
            "principal_id": "incident-harness",
            "action": action,
            "resource": {"resource_type": kind, "resource_id": resource},
            "effect": "allow",
        }


def executor_changes_grant():
    return {
        "grant_id": "grant-setup-deploy-executor-change-write",
        "principal_id": "deploy-executor",
        "action": "change.write",
        "resource": {"resource_type": "incident_workflow", "resource_id": "incident-response"},
        "effect": "allow",
    }


async def provision_executor_changes(service, bearer, key):
    """The deploy-executor's own credential (#770): change.write only, from the key in .env.

    The control API issues random keys, so the credential row is written here, as the seed writes
    the other demo keys; an existing one must hold this same key or provisioning fails closed.
    """
    from datetime import UTC, datetime

    from sre_agent.persistence.api_keys import api_key_prefix, hash_api_key, verify_api_key
    from sre_agent.persistence.models import CredentialRow

    body = {"principal_id": "deploy-executor", "kind": "agent", "display_name": "Deploy executor"}
    response = await service.create_principal(body, bearer, "setup-v1-principal-deploy-executor")
    if response.status_code not in (200, 201, 409):
        raise RuntimeError("deploy-executor principal conflict")
    async with service.sessions() as session, session.begin():
        stored = await session.get(CredentialRow, "credential-deploy-executor")
        if stored is None:
            now = datetime.now(UTC)
            session.add(
                CredentialRow(
                    credential_id="credential-deploy-executor",
                    principal_id="deploy-executor",
                    prefix=api_key_prefix(key),
                    key_hash=hash_api_key(key),
                    status="active",
                    created_at=now,
                )
            )
        elif stored.status != "active" or not verify_api_key(key, stored.key_hash):
            raise RuntimeError("deploy-executor credential conflict")
    grant = executor_changes_grant()
    response = await service.create_grant(grant, bearer, "setup-v1-" + grant["grant_id"])
    if not (response.status_code in (201, 409) and await _already_active(service, grant)):
        raise RuntimeError("demo grant conflict: " + grant["grant_id"])


async def _already_active(service, body):
    """The same authority is already active, whatever grant id an operator gave it by hand."""
    from sre_agent.persistence.repositories import GrantRepository

    resource = body["resource"]
    async with service.sessions() as session:
        found = await GrantRepository(session).find_active(
            body["principal_id"], body["action"], resource["resource_type"], resource["resource_id"]
        )
    return found is not None


async def provision_demo(service, bearer, executor_changes_key=None):
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
        if response.status_code == 201 and await _granted(service, body):
            continue
        # 409: the authority exists already. Active is convergence; revoked fails closed.
        if response.status_code == 409 and await _already_active(service, body):
            continue
        raise RuntimeError("demo grant conflict: " + body["grant_id"])
    if executor_changes_key:
        await provision_executor_changes(service, bearer, executor_changes_key)


async def main():
    from sre_agent.persistence.api_keys import is_api_key
    from sre_agent.persistence.database import Database

    if not all(
        os.environ.get(name) for name in ("DATABASE_URL", "ADMIN_HUMAN_API_KEY", "AUDIT_HMAC_KEY")
    ):
        print("provision: database/admin/audit configuration required", file=sys.stderr)
        return 2
    executor_changes_key = os.environ.get("DEPLOY_EXECUTOR_CHANGES_API_KEY", "")
    if executor_changes_key and not is_api_key(executor_changes_key):
        print("provision: DEPLOY_EXECUTOR_CHANGES_API_KEY must be an sre_ key", file=sys.stderr)
        return 2
    db = Database(os.environ["DATABASE_URL"])
    try:
        await provision_demo(
            build_service(db, os.environ["AUDIT_HMAC_KEY"].encode()),
            "Bearer " + os.environ["ADMIN_HUMAN_API_KEY"],
            executor_changes_key,
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
