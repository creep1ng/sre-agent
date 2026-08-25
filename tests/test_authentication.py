import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from sre_agent.gateway.authentication import (
    AuthenticationFailed,
    authenticate_principal,
    authentication_failed_handler,
)
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.api_keys import hash_api_key
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import CredentialRow, PrincipalRow
from sre_agent.persistence.repositories import CredentialRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
KEYS = {
    "incident-harness": "sre_inci_0123456789abcdefghijklmnop",
    "admin-human": "sre_admn_0123456789abcdefghijklmnop",
    "revoked-agent": "sre_revo_0123456789abcdefghijklmnop",
    "expired-agent": "sre_expi_0123456789abcdefghijklmnop",
    "inactive-agent": "sre_nact_0123456789abcdefghijklmnop",
}


@pytest.fixture(scope="module")
def authentication_database() -> Database:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    database = Database(DATABASE_URL)

    async def insert_fixtures() -> None:
        async with database.transaction() as session:
            for principal_id in KEYS:
                session.add(
                    PrincipalRow(
                        principal_id=principal_id,
                        kind="human" if principal_id == "admin-human" else "agent",
                        display_name=principal_id,
                        status="inactive" if principal_id == "inactive-agent" else "active",
                        created_at=NOW - timedelta(days=1),
                        updated_at=NOW - timedelta(days=1),
                    )
                )
            await session.flush()
            for principal_id, key in KEYS.items():
                revoked = principal_id == "revoked-agent"
                expires_at = NOW - timedelta(seconds=1) if principal_id == "expired-agent" else None
                session.add(
                    CredentialRow(
                        credential_id=f"credential-{principal_id}",
                        principal_id=principal_id,
                        prefix=key[:8],
                        key_hash=hash_api_key(key),
                        status="revoked" if revoked else "active",
                        created_at=NOW - timedelta(days=1),
                        expires_at=expires_at,
                        revoked_at=NOW if revoked else None,
                    )
                )

    import asyncio

    asyncio.run(insert_fixtures())
    yield database
    asyncio.run(database.dispose())


def protected_app(database: Database, calls: dict[str, int]) -> FastAPI:
    app = FastAPI()
    app.state.session_provider = database.sessions
    app.add_exception_handler(AuthenticationFailed, authentication_failed_handler)

    @app.get("/protected")
    async def protected(
        context: Annotated[PrincipalContext, Depends(authenticate_principal)],
    ) -> PrincipalContext:
        calls["resources"] += 1
        calls["upstream"] += 1
        return context

    return app


@pytest.mark.parametrize("principal_id", ["incident-harness", "admin-human"])
def test_bearer_key_resolves_agent_and_human_through_the_same_dependency(
    authentication_database: Database, principal_id: str
) -> None:
    calls = {"resources": 0, "upstream": 0}
    with TestClient(protected_app(authentication_database, calls)) as client:
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {KEYS[principal_id]}"}
        )
    assert response.status_code == 200
    assert response.json()["principal"]["principal_id"] == principal_id
    assert response.json()["credential_id"] == f"credential-{principal_id}"
    assert calls == {"resources": 1, "upstream": 1}


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic value",
        "Bearer malformed",
        "Bearer sre_unkn_0123456789abcdefghijklmnop",
        f"Bearer {KEYS['revoked-agent']}",
        f"Bearer {KEYS['expired-agent']}",
        f"Bearer {KEYS['inactive-agent']}",
    ],
)
def test_all_authentication_failures_are_uniform_and_stop_before_resources_or_upstream(
    authentication_database: Database, authorization: str | None
) -> None:
    calls = {"resources": 0, "upstream": 0}
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _params, _context, _many) -> None:
        statements.append(statement)

    event.listen(
        authentication_database.engine.sync_engine, "before_cursor_execute", capture_statement
    )
    headers = {"X-Request-ID": "20000000-0000-4000-8000-000000000001"}
    if authorization is not None:
        headers["Authorization"] = authorization
    with TestClient(protected_app(authentication_database, calls)) as client:
        response = client.get("/protected", headers=headers)
    event.remove(
        authentication_database.engine.sync_engine, "before_cursor_execute", capture_statement
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {"code": "authentication_failed", "message": "Authentication failed."},
        "request_id": "20000000-0000-4000-8000-000000000001",
        "retryable": False,
    }
    assert calls == {"resources": 0, "upstream": 0}
    assert all(" grants" not in statement.lower() for statement in statements)
    assert all(" resources" not in statement.lower() for statement in statements)
    assert authorization is None or authorization not in response.text


@pytest.mark.asyncio
async def test_revocation_is_idempotent_and_immediately_prevents_authentication(
    authentication_database: Database,
) -> None:
    async with authentication_database.transaction() as session:
        first = await CredentialRepository(session).revoke("credential-incident-harness", now=NOW)
        second = await CredentialRepository(session).revoke(
            "credential-incident-harness", now=NOW + timedelta(hours=1)
        )
    assert first is not None and second is not None
    assert first == second and second.revoked_at == NOW
    calls = {"resources": 0, "upstream": 0}
    with TestClient(protected_app(authentication_database, calls)) as client:
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {KEYS['incident-harness']}"}
        )
    assert response.status_code == 401
    assert calls == {"resources": 0, "upstream": 0}
