import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_harness_uses_read_only_contracts_and_ephemeral_dependencies() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    entrypoint = (ROOT / "docker" / "harness-entrypoint.sh").read_text()

    assert "./schemas:/source/schemas:ro" in compose
    assert "./scripts:/source/scripts:ro" in compose
    assert "/workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755" in compose
    assert "harness_node_modules" not in compose
    assert "npm ci" not in entrypoint
    assert "cp -R /source/schemas /workspace/schemas" in entrypoint
    assert "cp -R /opt/tooling/node_modules/. /workspace/node_modules/" in entrypoint
    assert "ln -s /workspace/node_modules /workspace/schemas/tooling/node_modules" in entrypoint


def test_harness_preserves_issue_10_conformance_command() -> None:
    compose = (ROOT / "compose.yaml").read_text()

    expected = (
        '["npm", "--prefix", "schemas/tooling", "run", "conformance", '
        '"--", "--consumer", "issue-10"]'
    )
    assert expected in compose


def test_all_repository_checks_have_containerized_compose_interfaces() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    dockerfile = (ROOT / "docker" / "api.Dockerfile").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "python-checks:" in compose
    assert "target: checks" in compose
    assert "./scripts:/source/scripts:ro" in compose
    assert "FROM base AS checks" in dockerfile
    assert "COPY tests ./tests" in dockerfile
    assert "COPY agent ./agent" in dockerfile
    assert "COPY docs ./docs" in dockerfile
    assert "COPY .github ./.github" in dockerfile
    assert "docker compose --profile checks" in readme


def test_python_checks_uses_disposable_database_without_demo_dependency() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    checks = compose.split("  python-checks:", 1)[1].split("  python-checks-db:", 1)[0]
    checks_db = compose.split("  python-checks-db:", 1)[1].split("  harness:", 1)[0]

    assert "python-checks-db:" in checks
    assert "migrate:" not in checks
    assert "@python-checks-db:5432/python_checks" in checks
    assert "/var/lib/postgresql/data" in checks_db
    assert "ports:" not in checks_db
    assert "postgres_data" not in checks_db


def test_ci_runs_the_documented_python_checks_command() -> None:
    command = "docker compose --profile checks run --build --rm python-checks"
    readme = (ROOT / "README.md").read_text()
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert command in readme
    assert f"run: {command}" in workflow


@pytest.mark.parametrize(
    ("demo_url", "test_url"),
    [
        (
            "postgresql://admin:secret@db:5432/demo",
            "postgresql://tester:other@db:5432/demo",
        ),
        ("postgresql://admin@db:5432/demo", "postgresql://tester@db/demo"),
    ],
)
def test_database_isolation_guard_rejects_same_database_endpoint(
    demo_url: str, test_url: str
) -> None:
    environment = os.environ | {
        "DEMO_DATABASE_URL": demo_url,
        "TEST_DATABASE_URL": test_url,
    }

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "assert_test_database_isolated.py")],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "Refusing to run tests against the demo database" in result.stderr


def test_issue_14_harness_is_deterministic_and_provider_secret_free() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    harness = compose.split("  issue-14-harness:", 1)[1].split("  live-smoke:", 1)[0]
    live_smoke = compose.split("  live-smoke:", 1)[1].split("volumes:", 1)[0]

    assert '["pytest", "-q", "tests/test_responses.py"]' in harness
    assert "issue-14-db" in harness
    assert not any(line.strip().startswith("OPENROUTER_API_KEY:") for line in harness.splitlines())
    assert not any(
        line.strip().startswith("OPENROUTER_API_KEY:") for line in live_smoke.splitlines()
    )
    assert "OPENROUTER_API_CONFIGURED" in live_smoke
