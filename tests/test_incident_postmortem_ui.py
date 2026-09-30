"""Static guards for the postmortem view surface (HU-OPS-07, #43a-1).

Slice 43a-1 presents the contractual minimum from incident reads; #335 does
not exist as a backend, so generation, persistence, versioning, provenance
selection, review persistence and close are out. Shape names mirror
$defs/postmortem in incident-state.schema.yaml; the page invents no endpoint,
no version field and no review state.
"""

from pathlib import Path

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "public" / "incident-ui" / "postmortem.html").read_text()
JAVASCRIPT = (ROOT / "public" / "incident-ui" / "postmortem.js").read_text()


def test_postmortem_shape_uses_the_contractual_status() -> None:
    assert '"draft"' in JAVASCRIPT
    assert "pm_demo0001" in JAVASCRIPT
    for block in ("artifact-sections", "fixture-banner", "fact-artifact"):
        assert block in HTML or block in JAVASCRIPT


def test_postmortem_invents_no_backend_or_close() -> None:
    for forbidden in (
        "close_incident",
        "/postmortems",
        "localStorage",
        "expected_version",
        "fetch(",
    ):
        assert forbidden not in JAVASCRIPT, forbidden
        assert forbidden not in HTML, forbidden
