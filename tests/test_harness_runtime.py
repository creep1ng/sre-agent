from pathlib import Path

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
    assert "docker compose --profile checks" in readme
