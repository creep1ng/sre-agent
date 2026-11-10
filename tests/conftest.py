"""Fixtures shared by the PostgreSQL-backed tests."""

from collections.abc import Iterator

import pytest
from database_support import DATABASE_URL, migrate_database
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.settings import Settings

# The shared assertions in this support module report like the ones written in a test file.
pytest.register_assert_rewrite("incident_http_testkit")


@pytest.fixture(scope="module")
def migrated_database() -> None:
    """Give the module an empty database migrated to the Alembic head."""
    migrate_database(DATABASE_URL)


@pytest.fixture
def client(audit_key: str) -> Iterator[TestClient]:
    """A client of the real application on the test database, with the module's `audit_key`."""
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=audit_key))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
