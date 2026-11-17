"""Fixtures shared by the PostgreSQL-backed tests, and the split of the suite into CI shards."""

import os
from collections import Counter
from collections.abc import Iterator

import pytest
from database_support import DATABASE_URL, migrate_database
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.settings import Settings

# The shared assertions in this support module report like the ones written in a test file.
pytest.register_assert_rewrite("incident_http_testkit")

# Seconds each file of 3 s or more took in one run of the suite (junit report, 2026-11-16); a test
# of any other file costs about SECONDS_PER_TEST. A stale number only unbalances the shards.
SLOW_FILE_SECONDS = {
    "tests/test_external_effects_e2e.py": 72,
    "tests/test_incident_investigator_http.py": 40,
    "tests/test_consumption_acceptance.py": 26,
    "tests/test_mitigation_verification_http.py": 11,
    "tests/test_mitigation_execution_http.py": 11,
    "tests/test_control_acceptance.py": 10,
    "tests/test_incident_restart_reads.py": 8,
    "tests/test_audit_reads_http.py": 7,
    "tests/test_usage_read_acceptance.py": 7,
    "tests/test_triage_http.py": 6,
    "tests/test_skill_migration_compatibility.py": 6,
    "tests/test_bok_http.py": 4,
    "tests/test_demo_provision_http.py": 4,
    "tests/test_responses.py": 4,
    "tests/test_investigator_demo.py": 3,
    "tests/test_incident_run_context.py": 3,
}
SECONDS_PER_TEST = 0.035


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep only the files of shard `PYTEST_SHARD=<index>/<total>`, as the CI unit job sets it.

    Whole files, so a module keeps its database to itself, and each file goes to exactly one
    shard: the heaviest file first, each to the shard with the least estimated time so far.
    """
    selection = os.environ.get("PYTEST_SHARD")
    if not selection:
        return
    try:
        index, total = (int(part) for part in selection.split("/"))
    except ValueError:
        raise pytest.UsageError(f"PYTEST_SHARD must be <index>/<total>: {selection!r}") from None
    if not 1 <= index <= total:
        raise pytest.UsageError(f"PYTEST_SHARD index must be within 1..{total}, not {index}")
    tests = Counter(item.nodeid.split("::")[0] for item in items)
    seconds = {
        path: SLOW_FILE_SECONDS.get(path, SECONDS_PER_TEST * count) for path, count in tests.items()
    }
    load = [0.0] * total
    shard_of = {}
    for path in sorted(seconds, key=lambda path: (-seconds[path], path)):
        shard_of[path] = load.index(min(load))
        load[shard_of[path]] += seconds[path]
    kept, dropped = [], []
    for item in items:
        (kept if shard_of[item.nodeid.split("::")[0]] == index - 1 else dropped).append(item)
    config.hook.pytest_deselected(items=dropped)
    items[:] = kept


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
