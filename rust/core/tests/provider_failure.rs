use sre_agent_core::provider_failure::map_provider_failure;

#[test]
fn known_failures_preserve_status_audit_reason_and_public_code() {
    for (kind, expected) in [
        ("timeout", (504, "upstream_failed", "upstream_timeout")),
        (
            "unavailable",
            (503, "upstream_unavailable", "upstream_unavailable"),
        ),
        (
            "evidence_invalid",
            (502, "upstream_invalid", "provider_evidence_invalid"),
        ),
        (
            "invalid_response",
            (502, "upstream_invalid", "upstream_invalid_response"),
        ),
    ] {
        let actual = map_provider_failure(kind);
        assert_eq!(
            (actual.status, actual.audit_reason, actual.public_code),
            expected,
            "kind: {kind}"
        );
    }
}

#[test]
fn unknown_failures_use_the_existing_invalid_response_mapping() {
    for kind in ["", "future_failure", "TIMEOUT"] {
        let actual = map_provider_failure(kind);
        assert_eq!(actual.status, 502, "kind: {kind}");
        assert_eq!(actual.audit_reason, "upstream_invalid", "kind: {kind}");
        assert_eq!(
            actual.public_code, "upstream_invalid_response",
            "kind: {kind}"
        );
    }
}
