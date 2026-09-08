"""Render a safe, explicit outcome for the bounded mutmut diagnostic."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MutationSummary:
    outcome: str
    killed: int | None
    survived: int | None
    total: int | None
    no_tests: int | None
    skipped: int | None
    suspicious: int | None
    mutant_timeouts: int | None
    interrupted_mutants: int | None
    segfaults: int | None
    run_error: str | None
    export_error: str | None
    incomplete: bool


_COUNTERS = {
    "killed": "killed",
    "survived": "survived",
    "total": "total",
    "no_tests": "no_tests",
    "skipped": "skipped",
    "suspicious": "suspicious",
    "mutant_timeouts": "timeout",
    "interrupted_mutants": "check_was_interrupted_by_user",
    "segfaults": "segfault",
}


def _valid_counter(stats: dict[str, Any] | None, name: str) -> int | None:
    if stats is None:
        return None
    value = stats.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _counters(stats: dict[str, Any] | None) -> dict[str, int | None]:
    return {field: _valid_counter(stats, key) for field, key in _COUNTERS.items()}


def _has_complete_schema(stats: dict[str, Any] | None) -> bool:
    return stats is not None and all(
        _valid_counter(stats, key) is not None for key in _COUNTERS.values()
    )


def summarize(run_status: int, export_status: int, stats: dict[str, Any] | None) -> MutationSummary:
    """Classify process, export, and per-mutant outcomes without conflating them."""
    counters = _counters(stats)
    run_error = None if run_status in (0, 124) else f"exit status {run_status}"
    export_error = None if export_status == 0 else f"exit status {export_status}"
    if export_error is None and not _has_complete_schema(stats):
        export_error = "statistics file unavailable or invalid"

    incomplete = run_status == 124
    if incomplete:
        outcome = "incomplete"
    elif run_error is not None or export_error is not None:
        outcome = "errors"
    else:
        outcome = "completed"

    return MutationSummary(
        outcome=outcome,
        run_error=run_error,
        export_error=export_error,
        incomplete=incomplete,
        **counters,
    )


def _read_stats(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _display(value: int | None) -> str:
    return str(value) if value is not None else "unavailable"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-status", type=int, required=True)
    parser.add_argument("--export-status", type=int, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    args = parser.parse_args()

    summary = summarize(args.run_status, args.export_status, _read_stats(args.stats))
    print("## Authorization mutation diagnostic")
    print(f"Outcome: {summary.outcome}")
    print(f"Run status: {args.run_status}")
    print(f"Stats export status: {args.export_status}")
    print(f"Run error: {summary.run_error or 'none'}")
    print(f"Stats export error: {summary.export_error or 'none'}")
    print(f"Killed: {_display(summary.killed)}")
    print(f"Survived: {_display(summary.survived)}")
    print(f"Total: {_display(summary.total)}")
    print(f"No-test mutants: {_display(summary.no_tests)}")
    print(f"Skipped mutants: {_display(summary.skipped)}")
    print(f"Suspicious mutants: {_display(summary.suspicious)}")
    print(f"Mutant timeouts: {_display(summary.mutant_timeouts)}")
    print(f"Interrupted mutants: {_display(summary.interrupted_mutants)}")
    print(f"Segfaults: {_display(summary.segfaults)}")
    print(f"Incomplete: {'yes' if summary.incomplete else 'no'}")


if __name__ == "__main__":
    main()
