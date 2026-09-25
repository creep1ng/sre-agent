"""Issue #23 C3a: triage UI stays on the C2b contract (no invented fields)."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "public" / "admin" / "triage.html").read_text()
JAVASCRIPT = (ROOT / "public" / "admin" / "triage.js").read_text()
CLIENT = (ROOT / "public" / "api" / "client.js").read_text()


def test_page_exposes_the_four_contract_operations() -> None:
    for operation in ("open_triage", "triage_dismiss", "triage_link", "triage_declare"):
        assert f'value="{operation}"' in HTML
    for severity in ("sev1", "sev2", "sev3", "sev4"):
        assert f'value="{severity}"' in HTML
    assert 'name="expected_version"' in HTML


def test_client_posts_commands_with_idempotency_key() -> None:
    assert "postTriageCommand" in CLIENT
    assert "/triage/commands" in CLIENT
    assert "Idempotency-Key" in CLIENT


def test_ui_has_no_impact_actor_or_timestamp_inputs() -> None:
    for field in ('name="impact"', 'name="actor"', 'name="timestamp"'):
        assert field not in HTML
    for fragment in ('"impact"', "'impact", "body.actor", "body.timestamp"):
        assert fragment not in JAVASCRIPT


def test_ui_builds_a_fresh_command_key_per_submit() -> None:
    assert "crypto.getRandomValues" in JAVASCRIPT
    assert "triage-" in JAVASCRIPT
