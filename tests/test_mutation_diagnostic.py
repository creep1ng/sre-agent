import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from summarize_mutation_diagnostic import summarize  # noqa: E402, I001


ACTUAL_MUTMUT_STATS = {
    "killed": 77,
    "survived": 6,
    "total": 83,
    "no_tests": 0,
    "skipped": 0,
    "suspicious": 0,
    "timeout": 0,
    "check_was_interrupted_by_user": 0,
    "segfault": 0,
}


def test_actual_mutmut_cicd_schema_preserves_each_counter() -> None:
    summary = summarize(run_status=0, export_status=0, stats=ACTUAL_MUTMUT_STATS)

    assert summary.outcome == "completed"
    assert summary.killed == 77
    assert summary.survived == 6
    assert summary.total == 83
    assert summary.no_tests == 0
    assert summary.skipped == 0
    assert summary.suspicious == 0
    assert summary.mutant_timeouts == 0
    assert summary.interrupted_mutants == 0
    assert summary.segfaults == 0
    assert summary.run_error is None
    assert summary.export_error is None
    assert summary.incomplete is False


def test_timeout_is_incomplete_even_when_cicd_stats_exist() -> None:
    summary = summarize(run_status=124, export_status=0, stats=ACTUAL_MUTMUT_STATS)

    assert summary.outcome == "incomplete"
    assert summary.incomplete is True
    assert summary.killed == 77
    assert summary.survived == 6
    assert summary.mutant_timeouts == 0


def test_run_error_is_distinct_from_mutant_timeout_and_missing_stats() -> None:
    summary = summarize(run_status=2, export_status=1, stats=None)

    assert summary.outcome == "errors"
    assert summary.incomplete is False
    assert summary.killed is None
    assert summary.mutant_timeouts is None
    assert summary.run_error == "exit status 2"
    assert summary.export_error == "exit status 1"


def test_missing_stats_is_an_error_even_when_commands_return_success() -> None:
    summary = summarize(run_status=0, export_status=0, stats=None)

    assert summary.outcome == "errors"
    assert summary.incomplete is False
    assert summary.run_error is None
    assert summary.export_error == "statistics file unavailable or invalid"


def test_mutmut_copies_the_package_root_but_mutates_authorization_only() -> None:
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'source_paths = ["src"]' in config
    assert 'only_mutate = ["src/sre_agent/governance/authorization.py"]' in config
    assert 'pytest_add_cli_args_test_selection = ["tests/test_authorization.py"]' in config


def test_workflow_reads_mutmut_export_file_not_exporter_stdout() -> None:
    workflow = (ROOT / ".github" / "workflows" / "quality-diagnostics.yml").read_text(
        encoding="utf-8"
    )

    assert "mutants/mutmut-cicd-stats.json" in workflow
    assert '--export-status "${export_status}"' in workflow


def test_checks_image_context_allows_the_mutation_workflow_only() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "!.github/workflows/quality-diagnostics.yml" in dockerignore
