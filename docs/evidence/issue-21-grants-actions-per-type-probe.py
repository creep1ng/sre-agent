"""Issue #21 per-type actions probe: backend contract truth for the grants selector.

Containerized proof that every action the fixed per-type selector offers is
creatable live (201) and every legacy flat action it removed is rejected
(422). Uses real FastAPI + PostgreSQL in the checks profile with synthetic
probe-21-pertype-* rows; prints ONLY the JSON transcript.
"""

import asyncio
import json
import os
import uuid

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://python_checks@python-checks-db:5432/python_checks",
)
AUDIT_KEY = "issue21-pertype-audit-key"
NS = "probe-21-pertype"

# Backend truth mirrored by public/admin/grants.js GRANT_ADMITTED_ACTIONS
# (mirror of GRANT_ADMITTED_ACTIONS in src/sre_agent/control/service.py).
ADMITTED = {
    "llm_model": "invoke",
    "mcp_server": "mcp.invoke",
    "mcp_tool": "mcp.invoke",
    "skill": "invoke",
    "bok_collection": "bok.search",
    "incident_workflow": "run.start",
    "administrative_control": "admin.read",
}
RESOURCES = {
    "llm_model": f"{NS}-llm",
    "mcp_server": f"{NS}-mcp-server",
    "mcp_tool": f"{NS}-mcp-tool",
    "skill": f"{NS}-skill",
    "bok_collection": f"{NS}-bok",
    "incident_workflow": f"{NS}-workflow",
    "administrative_control": f"{NS}-admin-target",
}
HUMAN = f"{NS}-human"


def sql_setup() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active') "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO principals (principal_id, kind, display_name, status, "
            "created_at, updated_at) VALUES ('admin-human', 'human', 'Admin', "
            "'active', now(), now()) ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, "
            "resource_id, effect, status, created_at) VALUES "
            "('grant-admin-human-admin-write-grants', 'admin-human', 'admin.write', "
            "'administrative_control', 'grants', 'allow', 'active', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute("DELETE FROM grants WHERE grant_id LIKE 'probe-21-pertype-%'")
        connection.execute(
            "DELETE FROM idempotency_records WHERE canonical_path = '/v1/grants' "
            "AND outcome ->> 'resource_id' LIKE 'probe-21-pertype-%'"
        )
        connection.execute("DELETE FROM credentials WHERE principal_id LIKE 'probe-21-pertype-%'")
        connection.execute("DELETE FROM principals WHERE principal_id LIKE 'probe-21-pertype-%'")
        connection.execute("DELETE FROM resources WHERE resource_id LIKE 'probe-21-pertype-%'")
        connection.execute(
            "INSERT INTO principals (principal_id, kind, display_name, status, "
            "created_at, updated_at) VALUES (%s, 'human', %s, 'active', now(), now())",
            (HUMAN, HUMAN),
        )
        catalog_meta = {
            "llm_model": ("alias-probe-llm", "model_alias"),
            "mcp_server": ("mcp-platform", "mcp"),
            "mcp_tool": ("mcp-platform", "mcp"),
            "skill": ("admin-human", "skill"),
            "bok_collection": ("bok-platform", "bok"),
            "incident_workflow": ("admin-human", "incident_workflow"),
        }
        for resource_type, resource_id in RESOURCES.items():
            if resource_type == "administrative_control":
                connection.execute(
                    "INSERT INTO resources (resource_type, resource_id, status) "
                    "VALUES (%s, %s, 'active')",
                    (resource_type, resource_id),
                )
            elif resource_type == "llm_model":
                alias = f"alias-{resource_id}"
                connection.execute(
                    "INSERT INTO resources (resource_type, resource_id, status, "
                    "model_alias_id, alias, concrete_model, router, "
                    "inference_provider, owner_id, source, source_ref, "
                    "display_name, visibility, description, tags) VALUES "
                    "('llm_model', %s, 'active', %s, %s, 'openai/gpt-4o-mini', "
                    "'openrouter', 'openai', %s, 'model_alias', %s, %s, "
                    "'private', '', '[]')",
                    (resource_id, alias, resource_id, alias, alias, resource_id),
                )
            else:
                owner_id, source = catalog_meta[resource_type]
                connection.execute(
                    "INSERT INTO resources (resource_type, resource_id, status, "
                    "owner_id, source, source_ref, display_name, visibility, "
                    "description, tags) VALUES (%s, %s, 'active', %s, %s, %s, "
                    "%s, 'private', '', '[]')",
                    (
                        resource_type,
                        resource_id,
                        owner_id,
                        source,
                        resource_id,
                        resource_id,
                    ),
                )


async def mint_admin_key() -> str:
    database = Database(DATABASE_URL)
    try:
        async with database.sessions() as session:
            issued = await CredentialRepository(session).issue("admin-human")
            await session.commit()
            return issued.key
    finally:
        await database.dispose()


def counts(grant_id: str) -> tuple[int, int]:
    with psycopg.connect(DATABASE_URL) as connection:
        grants = connection.execute(
            "SELECT count(*) FROM grants WHERE grant_id = %s", (grant_id,)
        ).fetchone()[0]
        bindings = connection.execute(
            "SELECT count(*) FROM idempotency_records "
            "WHERE canonical_path = '/v1/grants' AND outcome ->> 'resource_id' = %s",
            (grant_id,),
        ).fetchone()[0]
    return grants, bindings


def main() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    sql_setup()
    admin_key = asyncio.run(mint_admin_key())
    auth = {"Authorization": f"Bearer {admin_key}"}
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    cases = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for resource_type, action in ADMITTED.items():
            resource_id = RESOURCES[resource_type]
            grant_id = f"{NS}-g-{resource_type}"
            response = client.post(
                "/v1/grants",
                json={
                    "grant_id": grant_id,
                    "principal_id": HUMAN,
                    "action": action,
                    "resource": {
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                    },
                    "effect": "allow",
                },
                headers={**auth, "Idempotency-Key": uuid.uuid4().hex},
            )
            grant_rows, bindings = counts(grant_id)
            cases.append(
                {
                    "case": f"admitted {action} on {resource_type}",
                    "status": response.status_code,
                    "error_code": response.json().get("error", {}).get("code"),
                    "grant_rows": grant_rows,
                    "idempotency_bindings": bindings,
                }
            )
        # Legacy flat actions are admitted by nothing: authenticate must 422
        # on every type (the old selector offered it everywhere).
        for resource_type in ADMITTED:
            resource_id = RESOURCES[resource_type]
            grant_id = f"{NS}-r-auth-{resource_type}"
            response = client.post(
                "/v1/grants",
                json={
                    "grant_id": grant_id,
                    "principal_id": HUMAN,
                    "action": "authenticate",
                    "resource": {
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                    },
                    "effect": "allow",
                },
                headers={**auth, "Idempotency-Key": uuid.uuid4().hex},
            )
            grant_rows, bindings = counts(grant_id)
            cases.append(
                {
                    "case": f"rejected authenticate on {resource_type}",
                    "status": response.status_code,
                    "error_code": response.json().get("error", {}).get("code"),
                    "grant_rows": grant_rows,
                    "idempotency_bindings": bindings,
                }
            )
        # The old flat list offered bare invoke for incident_workflow, which
        # the backend never admitted: it must still 422 (defense in depth).
        response = client.post(
            "/v1/grants",
            json={
                "grant_id": f"{NS}-r-invoke-workflow",
                "principal_id": HUMAN,
                "action": "invoke",
                "resource": {
                    "resource_type": "incident_workflow",
                    "resource_id": RESOURCES["incident_workflow"],
                },
                "effect": "allow",
            },
            headers={**auth, "Idempotency-Key": uuid.uuid4().hex},
        )
        grant_rows, bindings = counts(f"{NS}-r-invoke-workflow")
        cases.append(
            {
                "case": "rejected bare invoke on incident_workflow",
                "status": response.status_code,
                "error_code": response.json().get("error", {}).get("code"),
                "grant_rows": grant_rows,
                "idempotency_bindings": bindings,
            }
        )
    print(json.dumps({"issue": 21, "cases": cases}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
