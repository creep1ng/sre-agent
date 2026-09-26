//! Provider-failure taxonomy independent of transport and provider adapters.

pub struct ProviderFailureMapping {
    pub status: u16,
    pub audit_reason: &'static str,
    pub public_code: &'static str,
}

/// Preserve the gateway's existing handling of known and unknown failure kinds.
pub fn map_provider_failure(kind: &str) -> ProviderFailureMapping {
    match kind {
        "timeout" => ProviderFailureMapping {
            status: 504,
            audit_reason: "upstream_failed",
            public_code: "upstream_timeout",
        },
        "unavailable" => ProviderFailureMapping {
            status: 503,
            audit_reason: "upstream_unavailable",
            public_code: "upstream_unavailable",
        },
        "evidence_invalid" => ProviderFailureMapping {
            status: 502,
            audit_reason: "upstream_invalid",
            public_code: "provider_evidence_invalid",
        },
        _ => ProviderFailureMapping {
            status: 502,
            audit_reason: "upstream_invalid",
            public_code: "upstream_invalid_response",
        },
    }
}
