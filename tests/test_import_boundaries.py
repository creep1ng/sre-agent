"""Regression proof that Import Linter analyzes the candidate source tree."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")


@dataclass(frozen=True)
class CopiedCandidate:
    source_root: Path
    config: Path

    def lint(self) -> subprocess.CompletedProcess[str]:
        environment = os.environ | {
            "PYTHONPATH": str(self.source_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        return subprocess.run(
            [str(LINT_IMPORTS), "--config", str(self.config), "--no-cache"],
            capture_output=True,
            check=False,
            cwd=self.config.parent,
            env=environment,
            text=True,
        )


@pytest.fixture
def copied_candidate(tmp_path: Path) -> CopiedCandidate:
    """Create a source candidate that cannot resolve the installed package first."""

    source_root = tmp_path / "src"
    shutil.copytree(ROOT / "src", source_root)
    config = tmp_path / ".importlinter"
    shutil.copy2(ROOT / ".importlinter", config)
    return CopiedCandidate(source_root=source_root, config=config)


def test_import_linter_allows_persistence_incident_adapter(
    copied_candidate: CopiedCandidate,
) -> None:
    result = copied_candidate.lint()

    assert result.returncode == 0, result.stdout + result.stderr


def test_import_linter_rejects_direct_incident_runtime_persistence_import(
    copied_candidate: CopiedCandidate,
) -> None:
    runtime = copied_candidate.source_root / "sre_agent" / "incident" / "runtime.py"
    runtime.write_text(
        runtime.read_text(encoding="utf-8") + "\nfrom sre_agent.persistence import repositories\n",
        encoding="utf-8",
    )

    result = copied_candidate.lint()

    assert result.returncode != 0
    assert "Incident core does not use concrete adapters BROKEN" in result.stdout


def test_import_linter_rejects_indirect_incident_runtime_persistence_import(
    copied_candidate: CopiedCandidate,
) -> None:
    probe = copied_candidate.source_root / "sre_agent" / "incident" / "boundary_probe.py"
    probe.write_text("from sre_agent.persistence import repositories\n", encoding="utf-8")
    runtime = copied_candidate.source_root / "sre_agent" / "incident" / "runtime.py"
    runtime.write_text(
        runtime.read_text(encoding="utf-8") + "\nfrom . import boundary_probe\n",
        encoding="utf-8",
    )

    result = copied_candidate.lint()

    assert result.returncode != 0
    assert "sre_agent.incident.runtime -> sre_agent.incident.boundary_probe" in result.stdout
