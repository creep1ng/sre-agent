"""Static guards for the mitigation review surface and command integration.

The UI derives review actions from the published workflow and submits commands
through the shared API client. Command names, transitions and auth actions are
cross-checked against incident-response.yaml and run-command.schema.yaml.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "public" / "incident-ui" / "review.html").read_text()
JAVASCRIPT = (ROOT / "public" / "incident-ui" / "review.js").read_text()
CLIENT = (ROOT / "public" / "api" / "client.js").read_text()
WORKFLOW = yaml.safe_load((ROOT / "agent" / "workflows" / "incident-response.yaml").read_text())
COMMAND_SCHEMA = yaml.safe_load(
    (ROOT / "agent" / "schemas" / "run-command.schema.yaml").read_text()
)
COMMAND_SCHEMA_210 = yaml.safe_load(
    (ROOT / "agent" / "schemas" / "run-command-2.1.0.schema.yaml").read_text()
)


def test_review_actions_match_the_published_workflow() -> None:
    approval = WORKFLOW["decision_points"]["mitigation_approval"]
    assert approval["state"] == "mitigating"
    assert approval["actor"] == ["human"]
    assert set(approval["outcomes"]) == {"approve", "reject", "request_changes"}
    stability = WORKFLOW["decision_points"]["stability_check"]
    assert stability["state"] == "verifying"
    assert stability["actor"] == ["human", "agent"]
    assert set(stability["outcomes"]) == {"stable", "not_stable"}
    by_id = {transition["id"]: transition for transition in WORKFLOW["transitions"]}
    assert by_id["apply_mitigation"]["decision_point"] == "mitigation_approval"
    assert by_id["apply_mitigation"]["on_outcome"] == "approve"
    assert set(by_id["reject_mitigation"]["on_outcome"]) == {"reject", "request_changes"}
    assert by_id["verification_passed"]["decision_point"] == "stability_check"
    assert by_id["verification_passed"]["on_outcome"] == "stable"
    assert by_id["verification_passed"]["to"] == "resolved"
    assert by_id["verification_failed"]["decision_point"] == "stability_check"
    assert by_id["verification_failed"]["on_outcome"] == "not_stable"
    assert by_id["verification_failed"]["to"] == "investigating"
    close = by_id["close_incident"]
    assert close["from"] == "postmortem"
    assert close["actor"] == ["human"]
    assert close["requires_approval"] is True
    for command in ("approve_mitigation", "reject_mitigation", "request_changes"):
        assert command in COMMAND_SCHEMA["properties"]["command"]["enum"]
    for command in ("verification_passed", "verification_failed", "close_incident"):
        assert command in JAVASCRIPT
        assert command not in COMMAND_SCHEMA["properties"]["command"]["enum"]
        assert command in COMMAND_SCHEMA_210["properties"]["command"]["enum"]
    for transition in (
        "apply_mitigation",
        "reject_mitigation",
        "verification_passed",
        "verification_failed",
        "close_incident",
    ):
        assert transition in JAVASCRIPT


def test_review_surface_stays_within_slice_scope() -> None:
    for block in ("actions-list", "actions-empty", "fact-run", "context-section"):
        assert block in HTML or block in JAVASCRIPT
    for forbidden in (
        "start_postmortem",
        "expected_version",
        "localStorage",
        "cancel_run",
        "propose_disposition",
    ):
        assert forbidden not in JAVASCRIPT, forbidden
        assert forbidden not in HTML, forbidden
    assert "principal_id" not in HTML


def test_review_reads_through_the_shared_seam() -> None:
    assert "getIncident(" in JAVASCRIPT
    assert "Idempotency-Key" in CLIENT


def test_review_submit_uses_the_contractual_command_seam() -> None:
    assert "sendRunCommand" in CLIENT
    assert "sendRunCommand" in JAVASCRIPT
    assert "randomUUID" in JAVASCRIPT
    assert '"409"' in JAVASCRIPT
    for key in ("command: action.command", 'actor: "human"', '"run.approve"', '"run.command"'):
        assert key in JAVASCRIPT, key
    assert "applied" not in JAVASCRIPT


def test_close_requires_the_explicit_visible_approval() -> None:
    assert 'id="decision-approval"' in HTML
    assert 'id="decision-approval-row"' in HTML
    assert "decision-approval-row" in JAVASCRIPT
    assert "decision-hint" in JAVASCRIPT
    assert "explicit_close_approval" in HTML
