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


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("status", "mismatched"),
        ("turns", 99),
        ("gateway_calls", 99),
        ("tool_calls", 99),
        ("evidence_sources", ["invented"]),
        ("provider_secret_sent", True),
        ("turn_id_sent", True),
    ],
)
def test_scenario_expectations_reject_tampered_observations(field: str, tampered: object) -> None:
    scenario = investigator_demo.SCENARIOS[0]
    observed = {
        "scenario": scenario.name,
        "status": scenario.expected,
        "turns": scenario.expected_turns,
        "gateway_calls": scenario.expected_gateway_calls,
        "tool_calls": scenario.expected_tool_calls,
        "evidence_sources": scenario.expected_evidence_sources,
        "provider_secret_sent": False,
        "turn_id_sent": False,
    }

    assert investigator_demo.matches_expectations(observed, scenario)
    observed[field] = tampered
    assert not investigator_demo.matches_expectations(observed, scenario)
