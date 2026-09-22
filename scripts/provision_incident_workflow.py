"""Provision the stable incident workflow resource and its run.read grant.

Issue #189 chain A2. Uses only the governed API (catalog.create then
grants.create); no direct inserts. Deterministic idempotency keys make
re-runs converge instead of duplicating.

Operator usage (inside the checks container):

    ADMIN_API_KEY=<admin-key> AUDIT_KEY_HEX=<64 hex> \\
        python scripts/provision_incident_workflow.py
    ADMIN_API_KEY=<admin-key> AUDIT_KEY_HEX=<64 hex> \\
        python scripts/provision_incident_workflow.py --revoke

The PO-approved constants below are the single source for the workflow
resource and the demo-human grant; A3/A4 reuse them.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

CATALOG_BODY = {
    "resource_type": "incident_workflow",
    "resource_id": "incident-response",
    "owner_id": "papiarcacamilo",
    "source": "incident_workflow",
    "source_ref": "incident-response@1.0.0",
    "status": "active",
    "discoverability": {
        "display_name": "Incident response workflow",
        "visibility": "private",
        "description": "Stable governed incident workflow resource.",
        "tags": ["incident", "workflow"],
    },
}
GRANT_BODY = {
    "grant_id": "grant-demo-human-run-read-incident-response",
    "principal_id": "demo-human",
    "action": "run.read",
    "resource": {"resource_type": "incident_workflow", "resource_id": "incident-response"},
    "effect": "allow",
}
CATALOG_IDEMPOTENCY_KEY = "incident-workflow-provision-catalog-v1"
GRANT_IDEMPOTENCY_KEY = "incident-workflow-provision-grant-v1"


@dataclass
class ProvisionResult:
    catalog_status: int
    grant_status: int


def build_service(database, audit_key: bytes):
    from sre_agent.control.service import ControlService
    from sre_agent.gateway.audit import AuditProjector
    from sre_agent.gateway.responses import PostgresAuditStore

    return ControlService(
        database.sessions, PostgresAuditStore(database.sessions), AuditProjector(audit_key)
    )


async def provision(service, bearer: str) -> ProvisionResult:
    catalog = await service.create_catalog_resource(CATALOG_BODY, bearer, CATALOG_IDEMPOTENCY_KEY)
    grant = await service.create_grant(GRANT_BODY, bearer, GRANT_IDEMPOTENCY_KEY)
    return ProvisionResult(catalog.status_code, grant.status_code)


async def revoke_run_read(service, bearer: str) -> int:
    response = await service.revoke_grant(GRANT_BODY["grant_id"], bearer)
    return response.status_code


async def _run(*, revoke: bool) -> int:
    from sre_agent.persistence.database import Database

    database_url = os.environ.get("DATABASE_URL")
    admin_key = os.environ.get("ADMIN_API_KEY")
    audit_hex = os.environ.get("AUDIT_KEY_HEX", "")
    if not database_url or not admin_key or len(audit_hex) != 64:
        print(
            "provision: DATABASE_URL, ADMIN_API_KEY and 64-hex AUDIT_KEY_HEX are required",
            file=sys.stderr,
        )
        return 2
    try:
        audit_key = bytes.fromhex(audit_hex)
    except ValueError:
        print("provision: AUDIT_KEY_HEX must be hex", file=sys.stderr)
        return 2
    database = Database(database_url)
    try:
        service = build_service(database, audit_key)
        bearer = f"Bearer {admin_key}"
        if revoke:
            status = await revoke_run_read(service, bearer)
            print(json.dumps({"revoke_status": status}))
            return 0 if status == 204 else 1
        result = await provision(service, bearer)
        print(
            json.dumps(
                {"catalog_status": result.catalog_status, "grant_status": result.grant_status}
            )
        )
        return 0 if (result.catalog_status, result.grant_status) == (201, 201) else 1
    finally:
        await database.dispose()


def main() -> int:
    import asyncio

    return asyncio.run(_run(revoke="--revoke" in sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
