"""Issue #25 B2b unit gates: filter parsing and metadata projection (no DB)."""

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.audit_reads import AuditReadsService, project_metadata

KEY = b"test-audit-hmac-key-32-bytes!!"
PROJECTOR = AuditProjector(KEY)
WINDOW = {"from": "2026-09-20T00:00:00Z", "to": "2026-09-21T00:00:00Z"}


def _service() -> AuditReadsService:
    return AuditReadsService(None, KEY)


def test_full_filter_set_resolves_to_storage_arguments() -> None:
    filters = _service()._filters(
        {
            **WINDOW,
            "principal_id": "admin-human",
            "decision": "allow",
            "model_alias_id": "triage-agent",
            "request_id": "c0000000-0000-4000-8000-000000000005",
            "incident_id": "inc-1",
            "run_id": "run_12345678",
            "task_id": "task-1",
            "trace_id": "trace-1",
            "limit": "10",
        }
    )
    assert filters is not None
    assert filters["limit"] == 10
    assert filters["decision"] == "allow"
    assert filters["request_id"] == "c0000000-0000-4000-8000-000000000005"
    assert filters["principal_digest"] == PROJECTOR.reference("principal", "admin-human").digest
    assert (
        filters["model_alias_digest"] == PROJECTOR.reference("model_alias", "triage-agent").digest
    )
    assert filters["incident_digest"] == PROJECTOR.reference("incident_id", "inc-1").digest
    assert filters["start"].isoformat() == "2026-09-20T00:00:00+00:00"
    assert filters["end"].isoformat() == "2026-09-21T00:00:00+00:00"


def test_defaults_and_single_filter_windows() -> None:
    assert _service()._filters({"decision": "deny"})["limit"] == 100
    assert _service()._filters({"from": WINDOW["from"]})["end"] is None
    assert _service()._filters({"to": WINDOW["to"]})["start"] is None


def test_rejections() -> None:
    service = _service()
    cases = [
        {},
        {"limit": "10"},
        {"cursor": "abc"},
        {"page": "1"},
        {"offset": "5"},
        {"continuation_token": "x"},
        {"next": "x"},
        {"content": "x"},
        {"raw_content": "x"},
        {"redacted_content": "x"},
        {"include_content": "x"},
        {**WINDOW, "decision": "maybe"},
        {**WINDOW, "request_id": "nope"},
        {**WINDOW, "principal_id": "ABC"},
        {**WINDOW, "model_alias_id": ""},
        {**WINDOW, "from": WINDOW["to"], "to": WINDOW["from"]},
        {**WINDOW, "from": "2026-09-20T00:00:00"},
        {**WINDOW, "to": "not-a-date"},
        {**WINDOW, "limit": "0"},
        {**WINDOW, "limit": "101"},
        {**WINDOW, "limit": "x"},
    ]
    for raw in cases:
        assert service._filters(raw) is None, raw


def test_projection_is_230_metadata_only() -> None:
    event = {
        "event_id": "b0000000-0000-4000-8000-000000000005",
        "redacted_content": {"text": "secret"},
        "correction_of_event_id": None,
        "untrusted_input": None,
        "identity": None,
        "resource": None,
        "reason_code": None,
        "authorization_denial_cause": None,
        "consumption": None,
        "policy_decision": {
            "decision": "allow",
            "reason_code": "grant_matched",
            "policy_ref": None,
        },
        "correlation": {"request_id": "c0000000-0000-4000-8000-000000000005", "run_ref": None},
        "redaction": {
            "policy_version": "redaction-1.0.0",
            "result": "success",
            "source_class": "none",
            "categories": [],
            "match_count": 0,
            "sink_eligible": False,
            "tool_schema_version": None,
        },
    }
    projected = project_metadata(event)
    assert "redacted_content" not in projected
    assert "correction_of_event_id" not in projected
    assert "untrusted_input" not in projected
    assert "identity" not in projected
    assert projected["reason_code"] is None
    assert projected["correlation"] == {"request_id": "c0000000-0000-4000-8000-000000000005"}
    assert projected["policy_decision"] == {"decision": "allow", "reason_code": "grant_matched"}
    assert "tool_schema_version" not in projected["redaction"]
