"""Reset the PostgreSQL test database by schema and migrate it with Alembic."""

import os

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)


def alembic_config(url: str = DATABASE_URL) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


def alembic_head() -> str:
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert head is not None
    return head


def reset_database(url: str = DATABASE_URL) -> None:
    """Drop every schema the tests or migrations created and recreate an empty `public`.

    Dropping a schema drops its tables, sequences, functions such as `reject_audit_mutation()`
    and the `alembic_version` table with it, so a new table or schema needs no change here.
    Roles are cluster-global and survive; the migrations create them only when they are absent.
    """
    with psycopg.connect(url, autocommit=True) as connection:
        schemas = connection.execute(
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname <> 'information_schema' AND nspname NOT LIKE 'pg\\_%'"
        ).fetchall()
        for (schema,) in schemas:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")


def migrate_database(url: str = DATABASE_URL, revision: str = "head") -> Config:
    """Reset the database, upgrade it to `revision` and return the Alembic configuration."""
    reset_database(url)
    config = alembic_config(url)
    command.upgrade(config, revision)
    return config
