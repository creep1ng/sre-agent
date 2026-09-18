"""The investigator demo scenarios end with their expected statuses (issue #185)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import investigator_demo  # noqa: E402


def test_every_demo_scenario_ends_as_expected(capsys: pytest.CaptureFixture[str]) -> None:
    assert investigator_demo.main() == 0
    output = capsys.readouterr().out

    assert output.count('"provider_secret_sent": false') == len(investigator_demo.SCENARIOS)
    assert '"incident_state_unchanged": true' in output
    assert "RESULT: all scenarios as expected" in output
