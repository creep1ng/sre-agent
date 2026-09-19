"""Static regression tests for the incident war room surface (HU-OPS-03, #36).

The war room is read-only: it navigates by incident_id, renders the
authoritative detail/timeline/snapshot through the browser API seam and never
applies transitions, starts the harness or synthesizes incidents. Behavioral
coverage lives in tests/browser/war-room.spec.js.
"""

from pathlib import Path

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "public" / "incident-ui" / "war-room.html").read_text()
JAVASCRIPT = (ROOT / "public" / "incident-ui" / "war-room.js").read_text()
CLIENT = (ROOT / "public" / "api" / "client.js").read_text()
STYLES = (ROOT / "styles" / "incident-war-room.css").read_text()


def test_war_room_navigates_by_incident_id() -> None:
    assert 'get("incident_id")' in JAVASCRIPT
    assert "getIncident(" in JAVASCRIPT
    assert "getIncidentTimeline(" in JAVASCRIPT
    assert "getIncidentSnapshot(" in JAVASCRIPT
    assert 'id="war-room"' in HTML
    assert 'id="timeline-list"' in HTML
    assert 'id="load-more"' in HTML
    assert 'id="refresh-button"' in HTML


def test_war_room_reuses_the_browser_api_seam() -> None:
    assert "getIncident(incidentId)" in CLIENT
    assert "getIncidentTimeline(incidentId" in CLIENT
    assert "getIncidentSnapshot(incidentId" in CLIENT
    assert "next_cursor" in JAVASCRIPT
    assert "has_more" in JAVASCRIPT and "hasMore" in JAVASCRIPT


def test_war_room_distinguishes_error_states_without_fixtures() -> None:
    for block in ("error-401", "error-403", "error-404", "error-503"):
        assert f'id="{block}"' in HTML
    assert "midnight-agent-theme" in JAVASCRIPT
    assert "localStorage.setItem" in JAVASCRIPT
    assert "incident_id" in JAVASCRIPT
    lowered = JAVASCRIPT.lower()
    assert "fixture" not in lowered


def test_war_room_applies_no_transitions_or_lifecycle_controls() -> None:
    for forbidden in (
        "start-triage",
        "approve",
        "resume",
        "start-harness",
        "lifecycle",
        "midnight:triage-requested",
        'localStorage.setItem("incident',
    ):
        assert forbidden not in JAVASCRIPT
        assert forbidden not in HTML


def test_war_room_uses_design_system_tokens() -> None:
    assert "var(--ma-" in STYLES
    assert "ma-badge" in HTML
    assert "ma-alert" in HTML
    assert "ma-button" in HTML
    assert "Sans" in STYLES or "ma-font-body" in STYLES
