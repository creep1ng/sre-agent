"""Create private issue-23 evidence credentials and a genuine pre-provenance row."""

import asyncio
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    PrincipalRepository,
)

DATABASE_URL = os.environ["DATABASE_URL"]
KEY_FILE = Path(os.environ["T23_CREDENTIALS_FILE"])
PRINCIPALS = {
    "op-e2e": (
        "human",
        (
            "alert.triage",
            "alert.dismiss",
            "alert.associate",
            "run.read",
            "incident.declare",
            "alert.read",
        ),
    ),
    "op-nogrant": ("human", ()),
    "op-noread": ("human", ("alert.dismiss",)),
    "producer-e2e": ("agent", ("alert.dismiss", "alert.associate", "run.read")),
    "producer-nogrant": ("agent", ()),
}


def migrate_with_legacy_row() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "20260923_13")
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO alert_triage (alert_id,status,incident_id,expected_version,reason,"
            "severity,actor,decided_at) VALUES (%s,'dismissed',NULL,2,%s,NULL,%s,now())",
            ("al-t23-legacy", "Historical decision before provenance tracking.", "producer-e2e"),
        )
    command.upgrade(config, "head")


async def seed() -> None:
    database = Database(DATABASE_URL)
    keys: dict[str, str] = {}
    try:
        async with database.transaction() as session:
            principals = PrincipalRepository(session)
            credentials = CredentialRepository(session)
            grants = GrantRepository(session)
            for principal_id, (kind, _actions) in PRINCIPALS.items():
                await principals.create(principal_id, kind, principal_id)
                keys[principal_id] = (await credentials.issue(principal_id)).key

            await session.execute(
                text(
                    "INSERT INTO resources (resource_type,resource_id,status,updated_at,owner_id,"
                    "source,source_ref,display_name,visibility,description,tags) VALUES "
                    "('incident_workflow','incident-response','active',now(),'op-e2e',"
                    "'incident_workflow','incident-response@1.0.0','Incident response workflow',"
                    "'private','','[]')"
                )
            )
            for principal_id, (_kind, actions) in PRINCIPALS.items():
                for index, action in enumerate(actions):
                    await grants.create(
                        f"t23-{principal_id}-{index}",
                        principal_id,
                        action,
                        "incident_workflow",
                        "incident-response",
                    )
    finally:
        await database.dispose()
    values = {
        "E2E_TRIAGE_API_KEY": keys["op-e2e"],
        "E2E_NOGRANT_API_KEY": keys["op-nogrant"],
        "E2E_OP_NOREAD_API_KEY": keys["op-noread"],
        "E2E_EXTERNAL_API_KEY": keys["producer-e2e"],
        "E2E_EXTERNAL_NOGRANT_API_KEY": keys["producer-nogrant"],
        "E2E_TRIAGE_LEGACY_ALERT_ID": "al-t23-legacy",
    }
    KEY_FILE.write_text("".join(f"{name}={value}\n" for name, value in values.items()))
    KEY_FILE.chmod(0o600)
    print("Seeded five synthetic principals and a pre-provenance legacy decision.")


if __name__ == "__main__":
    migrate_with_legacy_row()
    asyncio.run(seed())
