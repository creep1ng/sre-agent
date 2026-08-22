from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_harness_uses_read_only_contracts_and_ephemeral_dependencies() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    entrypoint = (ROOT / "docker" / "harness-entrypoint.sh").read_text()

    assert "./schemas:/workspace/schemas:ro" in compose
    assert "/workspace/node_modules:rw,nosuid,size=384m" in compose
    assert "harness_node_modules" not in compose
    assert "npm ci" not in entrypoint
    assert "cp -a /opt/tooling/node_modules/. /workspace/node_modules/" in entrypoint


def test_harness_preserves_issue_10_conformance_command() -> None:
    compose = (ROOT / "compose.yaml").read_text()

    expected = (
        '["npm", "--prefix", "schemas/tooling", "run", "conformance", '
        '"--", "--consumer", "issue-10"]'
    )
    assert expected in compose
