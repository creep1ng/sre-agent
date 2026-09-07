import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
sys.path.insert(0, str(ROOT / "scripts"))

from validate_ci_hardening import validate  # noqa: E402


def test_ci_workflow_satisfies_hardening_invariants() -> None:
    assert validate(WORKFLOW.read_text()) == []


def test_validator_rejects_mutable_actions_and_jobs_without_timeouts() -> None:
    workflow = """permissions:
  contents: read
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

    errors = validate(workflow)

    assert "job unsafe must set a positive timeout-minutes" in errors
    assert any("full SHA" in error for error in errors)


def test_validator_checks_timeout_when_runs_on_is_not_first() -> None:
    workflow = """permissions:
  contents: read
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
jobs:
  reordered:
    name: Reordered job
    runs-on: ubuntu-latest
    steps: []
"""

    assert "job reordered must set a positive timeout-minutes" in validate(workflow)


def test_validator_rejects_secret_references() -> None:
    workflow = WORKFLOW.read_text().replace(
        "jobs:\n", "env:\n  TOKEN: ${{ secrets.EXAMPLE }}\njobs:\n"
    )

    assert "pull-request CI must not reference repository secrets" in validate(workflow)


def test_validator_rejects_expanded_permissions() -> None:
    workflow = WORKFLOW.read_text().replace("contents: read", "contents: write")

    assert "workflow permissions must remain contents: read" in validate(workflow)
