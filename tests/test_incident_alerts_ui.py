from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_inbox_uses_local_sans_typography_without_changing_shared_components() -> None:
    html = (ROOT / "public" / "incident-ui" / "alerts.html").read_text()
    javascript = (ROOT / "public" / "incident-ui" / "alerts.js").read_text()
    local_styles = (ROOT / "styles" / "incident-alerts.css").read_text()
    base_styles = (ROOT / "styles" / "base.css").read_text()
    shared_styles = (ROOT / "styles" / "components.css").read_text()

    assert 'class="ma-eyebrow alert-inbox__eyebrow">Operaciones</p>' in html
    assert 'statusText.className = "ma-badge alert-list__status";' in javascript
    assert ".alert-inbox__eyebrow," in local_styles
    assert ".alert-list__status {\n  font-family: var(--ma-font-body);\n}" in local_styles
    assert ".ma-eyebrow {" in base_styles
    assert "font-family: var(--ma-font-mono);" in base_styles
    assert ".ma-badge {" in shared_styles
    assert "font-family: var(--ma-font-mono);" in shared_styles
