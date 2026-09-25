"""Issue #25 B3a: audit-events page stays on the 2.3.0 contract."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "public" / "admin" / "audit-events.html").read_text()
JAVASCRIPT = (ROOT / "public" / "admin" / "audit-events.js").read_text()
CLIENT = (ROOT / "public" / "api" / "client.js").read_text()

CONTRACT_FILTERS = [
    "principal_id",
    "decision",
    "model_alias_id",
    "request_id",
    "incident_id",
    "run_id",
    "task_id",
    "trace_id",
    "from",
    "to",
    "limit",
]


def test_page_exposes_every_contract_filter_with_limit_default() -> None:
    for name in CONTRACT_FILTERS:
        assert f'name="{name}"' in HTML
    assert 'value="100"' in HTML


def test_client_calls_the_published_audit_endpoints() -> None:
    assert "listAuditEvents" in CLIENT
    assert "getAuditEvent" in CLIENT
    assert "/v1/audit-events" in CLIENT


def test_ui_never_builds_paging_tokens() -> None:
    for token in ("cursor", "continuation_token", "offset", "include_content", "raw_content"):
        assert token not in JAVASCRIPT
        assert token not in HTML


def test_ui_never_references_excluded_content_fields() -> None:
    for field in ("redacted_content", "tool_schema_version"):
        assert field not in JAVASCRIPT
        assert field not in HTML
