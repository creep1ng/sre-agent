"""Launch a real control-plane API against an explicitly isolated test database."""

import asyncio
import os
from urllib.parse import urlsplit

import psycopg
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import Request

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings


def database_identity(url: str) -> tuple[str | None, int, str]:
    parsed = urlsplit(url)
    return parsed.hostname, parsed.port or 5432, parsed.path.rstrip("/")


def isolated_alembic_config(database_url: str) -> Config:
    """Make the guarded test DSN authoritative over Alembic's ambient override."""
    os.environ["DATABASE_URL"] = database_url
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def main() -> None:
    database_url = os.environ.get("BROWSER_API_TEST_DATABASE_URL", "")
    demo_url = os.environ.get("DEMO_DATABASE_URL", "")
    if not database_url or not demo_url:
        raise SystemExit("BROWSER_API_TEST_DATABASE_URL and DEMO_DATABASE_URL are required")
    if database_identity(database_url) == database_identity(demo_url):
        raise SystemExit("Refusing to run the browser consumer test against the demo database")

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")

    command.upgrade(isolated_alembic_config(database_url), "head")

    async def bootstrap() -> None:
        database = Database(database_url)
        try:
            await seed(database, SeedSettings.from_environment(os.environ))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE credentials SET status = 'revoked', revoked_at = now() "
            "WHERE principal_id = 'demo-human'"
        )
        connection.commit()

    app = create_application(Settings(database_url, audit_hmac_key=os.environ["AUDIT_HMAC_KEY"]))

    @app.get("/__test/forwarded-headers", include_in_schema=False)
    async def forwarded_headers(request: Request) -> dict[str, bool]:
        """Expose presence only; never echo header values into browser test evidence."""
        return {
            "cookie": "cookie" in request.headers,
            "origin": "origin" in request.headers,
        }

    uvicorn.run(app, host="0.0.0.0", port=4174, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
