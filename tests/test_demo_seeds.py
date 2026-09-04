import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.persistence.api_keys import verify_api_key
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import KEY_ENV, SeedConflict, SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
ENV = {
    "ADMIN_HUMAN_API_KEY": "sre_admn_0123456789abcdefghijklmnop",
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
    "RESTRICTED_HARNESS_API_KEY": "sre_rest_0123456789abcdefghijklmnop",
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
}


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


def test_seed_settings_reject_placeholders_and_malformed_values() -> None:
    invalid = (
        ("TRIAGE_AGENT_MODEL", "<lab/model>"),
        ("TRIAGE_AGENT_MODEL", "missing-slash"),
        ("TRIAGE_AGENT_PROVIDER", "<provider>"),
        ("ADMIN_HUMAN_API_KEY", "change-me"),
        ("ADMIN_HUMAN_API_KEY", "sre_" + "a" * 129),
    )
    for field, value in invalid:
        with pytest.raises(ValueError):
            SeedSettings.from_environment(ENV | {field: value})
    exact_maximum = SeedSettings.from_environment(ENV | {"ADMIN_HUMAN_API_KEY": "sre_" + "a" * 128})
    assert len(exact_maximum.keys[0]) == 132


@pytest.mark.asyncio
async def test_seed_rerun_converges_without_rotation_or_secret_persistence() -> None:
    settings = SeedSettings.from_environment(ENV)
    database = Database(DATABASE_URL)
    assert await seed(database, settings) is True
    with psycopg.connect(DATABASE_URL) as connection:
        before = connection.execute(
            "SELECT credential_id, key_hash FROM credentials ORDER BY credential_id"
        ).fetchall()
    assert await seed(database, settings) is False
    with psycopg.connect(DATABASE_URL) as connection:
        counts = [
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("principals", "credentials", "resources", "grants")
        ]
        after = connection.execute(
            "SELECT credential_id, key_hash FROM credentials ORDER BY credential_id"
        ).fetchall()
        grant = connection.execute(
            "SELECT principal_id, action FROM grants WHERE action='invoke' ORDER BY grant_id"
        ).fetchone()
        resource = connection.execute(
            "SELECT concrete_model, inference_provider FROM resources "
            "WHERE resource_type='llm_model'"
        ).fetchone()
        admin_resources = connection.execute(
            "SELECT count(*) FROM resources WHERE resource_type='administrative_control'"
        ).fetchone()[0]
        admin_grants = connection.execute(
            "SELECT count(*) FROM grants WHERE action LIKE 'admin.%'"
        ).fetchone()[0]
        stored = repr(connection.execute("SELECT prefix, key_hash FROM credentials").fetchall())
    await database.dispose()
    assert counts == [4, 4, 3, 5]
    assert admin_resources == 2
    assert admin_grants == 4
    assert before == after
    by_id = dict(before)
    seeded_principals = (
        "admin-human",
        "demo-human",
        "incident-harness",
        "restricted-harness",
    )
    assert all(
        verify_api_key(ENV[name], by_id[f"credential-{principal}"])
        for name, principal in zip(KEY_ENV, seeded_principals, strict=True)
    )
    assert grant == ("incident-harness", "invoke")
    assert resource == ("openai/gpt-4o-mini", "openai")
    assert all(secret not in stored for secret in ENV.values())


@pytest.mark.asyncio
async def test_seed_conflict_is_atomic_and_secret_free() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE principals SET display_name='conflict' WHERE principal_id='admin-human'"
        )
        connection.commit()
        before = connection.execute("SELECT count(*), min(display_name) FROM principals").fetchone()
    database = Database(DATABASE_URL)
    with pytest.raises(SeedConflict) as captured:
        await seed(database, SeedSettings.from_environment(ENV))
    await database.dispose()
    with psycopg.connect(DATABASE_URL) as connection:
        after = connection.execute("SELECT count(*), min(display_name) FROM principals").fetchone()
    message = str(captured.value)
    assert before == after
    assert message == "seed_state_conflict: principals.display_name"
    assert all(secret not in message for secret in ENV.values())


def test_unmigrated_application_reports_safely_without_mutating_schema() -> None:
    schema = "seed_unmigrated_test"
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        connection.execute(f"CREATE SCHEMA {schema}")
    dsn = f"{DATABASE_URL}?options=-csearch_path%3D{schema}"
    with TestClient(create_application(Settings(dsn))) as client:
        response = client.get("/health/ready")
    with psycopg.connect(DATABASE_URL) as connection:
        tables = connection.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname=%s", (schema,)
        ).fetchone()[0]
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "dependency": "postgresql"}
    assert tables == 0
