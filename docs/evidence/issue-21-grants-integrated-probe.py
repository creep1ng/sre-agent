"""Issue #21 integrated probe: create -> allow -> revoke -> deny (S2+S3).

POST /v1/grants, GET /v1/principals and DELETE /v1/grants/{id} on real
FastAPI + PostgreSQL without harness restart: create (201), allow (the
grantee credential drives GET /v1/principals through the real
authorization boundary and the governed list returns 200), revoke (204
with the row kept revoked) and deny (the same grantee credential through
the same boundary now returns 403 after revoke). Prints ONLY the JSON
transcript.
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
AUDIT_KEY = "issue21-integrated-audit-key"
NS = "probe-21-integrated"
GRANT_ID = f"{NS}-g1"
HUMAN = f"{NS}-human"


def sql_setup() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active') "
            "ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'principals', 'active') "
            "ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO principals (principal_id, kind, display_name, "
            "status, created_at, updated_at) VALUES ('admin-human', "
            "'human', 'Admin', 'active', now(), now()) "
            "ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO grants (grant_id, principal_id, action, "
            "resource_type, resource_id, effect, status, created_at) "
            "VALUES ('grant-admin-human-admin-write-grants', "
            "'admin-human', 'admin.write', 'administrative_control', "
            "'grants', 'allow', 'active', now()) ON CONFLICT DO NOTHING"
        )
        conn.execute("DELETE FROM grants WHERE grant_id LIKE 'probe-21-integrated-%'")
        conn.execute("DELETE FROM credentials WHERE principal_id LIKE 'probe-21-integrated-%'")
        conn.execute("DELETE FROM principals WHERE principal_id LIKE 'probe-21-integrated-%'")
        conn.execute(
            "INSERT INTO principals (principal_id, kind, display_name, "
            "status, created_at, updated_at) VALUES (%s, 'human', %s, "
            "'active', now(), now())",
            (HUMAN, HUMAN),
        )


async def mint_key(principal_id: str) -> str:
    database = Database(DATABASE_URL)
    try:
        async with database.sessions() as session:
            issued = await CredentialRepository(session).issue(principal_id)
            await session.commit()
            return issued.key
    finally:
        await database.dispose()


def main() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    sql_setup()
    admin_key = asyncio.run(mint_key("admin-human"))
    grantee_key = asyncio.run(mint_key(HUMAN))
    auth = {"Authorization": f"Bearer {admin_key}"}
    grantee = {"Authorization": f"Bearer {grantee_key}"}
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    cases = []
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/v1/grants",
            json={
                "grant_id": GRANT_ID,
                "principal_id": HUMAN,
                "action": "admin.read",
                "resource": {
                    "resource_type": "administrative_control",
                    "resource_id": "principals",
                },
                "effect": "allow",
            },
            headers={**auth, "Idempotency-Key": uuid.uuid4().hex},
        )
        cases.append({"case": "create probe grant", "status": created.status_code})
        allowed = client.get("/v1/principals?limit=100", headers=grantee)
        allowed_items = allowed.json().get("items", [])
        effective = allowed.status_code == 200 and any(
            item.get("principal_id") == "admin-human" for item in allowed_items
        )
        cases.append(
            {
                "case": "allow governed principals list as grantee",
                "status": allowed.status_code,
                "boundary_effective": effective,
            }
        )
        revoked = client.delete(f"/v1/grants/{GRANT_ID}", headers=auth)
        cases.append({"case": "revoke probe grant", "status": revoked.status_code})
        listed = client.get(f"/v1/grants?principal_id={HUMAN}&limit=100", headers=auth)
        items = listed.json().get("items", [])
        kept = any(
            item.get("grant_id") == GRANT_ID and item.get("status") == "revoked" for item in items
        )
        cases.append(
            {
                "case": "read lifecycle kept",
                "status": listed.status_code,
                "row_kept": kept,
            }
        )
        denied = client.get("/v1/principals?limit=100", headers=grantee)
        cases.append(
            {
                "case": "deny governed principals list after revoke",
                "status": denied.status_code,
                "error_code": denied.json().get("error", {}).get("code"),
                "boundary_denied": denied.status_code == 403,
            }
        )
        again = client.delete(f"/v1/grants/{GRANT_ID}", headers=auth)
        cases.append({"case": "double revoke converges", "status": again.status_code})
        unknown = client.delete(f"/v1/grants/{NS}-no-such", headers=auth)
        cases.append(
            {
                "case": "revoke unknown grant",
                "status": unknown.status_code,
                "error_code": unknown.json().get("error", {}).get("code"),
            }
        )
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT count(*) FROM grants WHERE grant_id = %s", (GRANT_ID,)
        ).fetchone()[0]
    cases.append({"case": "grant row never deleted", "grant_rows": rows})
    print(json.dumps({"cases": cases}, indent=2))


if __name__ == "__main__":
    main()
