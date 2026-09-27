"""Static guards for the mitigation review surface (HU-OPS-06, #41a-1).

Slice 41a-1 only derives and displays review actions; #330 publishes no POST
routes yet, so nothing is submitted. Command names, transitions and auth
actions are cross-checked against incident-response.yaml and
run-command.schema.yaml instead of being hardcoded twice.
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


def test_review_actions_match_the_published_workflow() -> None:
    approval = WORKFLOW["decision_points"]["mitigation_approval"]
    assert approval["state"] == "mitigating"
    assert approval["actor"] == ["human"]
    assert set(approval["outcomes"]) == {"approve", "reject", "request_changes"}
    by_id = {transition["id"]: transition for transition in WORKFLOW["transitions"]}
    assert by_id["apply_mitigation"]["decision_point"] == "mitigation_approval"
    assert by_id["apply_mitigation"]["on_outcome"] == "approve"
    assert set(by_id["reject_mitigation"]["on_outcome"]) == {"reject", "request_changes"}
    for command in ("approve_mitigation", "reject_mitigation", "request_changes"):
        assert command in COMMAND_SCHEMA["properties"]["command"]["enum"]
        assert command in JAVASCRIPT
    for transition in ("apply_mitigation", "reject_mitigation"):
        assert transition in JAVASCRIPT


def test_review_surface_stays_within_slice_scope() -> None:
    for block in ("actions-list", "actions-empty", "fact-run", "context-section"):
        assert block in HTML or block in JAVASCRIPT
    for forbidden in (
        "close_incident",
        "start_postmortem",
        "postmortem",
        "expected_version",
        "localStorage",
        "principal_id",
        "cancel_run",
        "propose_disposition",
    ):
        assert forbidden not in JAVASCRIPT, forbidden
        assert forbidden not in HTML, forbidden


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
