"""Fixtures shared by the PostgreSQL-backed tests."""

import pytest
from database_support import DATABASE_URL, migrate_database


@pytest.fixture(scope="module")
def migrated_database() -> None:
    """Give the module an empty database migrated to the Alembic head."""
    migrate_database(DATABASE_URL)
