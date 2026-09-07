"""Safety regression for the destructive browser consumer harness."""

import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location(
    "browser_api_test_server", Path(__file__).parents[1] / "scripts/browser_api_test_server.py"
)
assert spec is not None and spec.loader is not None
server = module_from_spec(spec)
spec.loader.exec_module(server)


def test_isolated_browser_database_overrides_ambient_migration_url(monkeypatch) -> None:
    isolated = "postgresql://browser@127.0.0.1:55448/browser_api_test"
    monkeypatch.setenv("DATABASE_URL", "postgresql://live@127.0.0.1:5432/live")

    config = server.isolated_alembic_config(isolated)

    assert os.environ["DATABASE_URL"] == isolated
    assert config.get_main_option("sqlalchemy.url") == isolated
