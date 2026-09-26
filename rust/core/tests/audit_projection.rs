use sre_agent_core::audit::{
    project_responses_audit, AssignmentFact, AuditRequest, ContextFact, DecisionFact,
};

#[test]
fn responses_denial_preserves_reference_domains_and_output_names() {
    let projection = project_responses_audit(&AuditRequest {
        status: 403,
        reason: Some("no_matching_grant"),
        context: Some(ContextFact {
            principal_id: "principal-harness",
            principal_kind: "agent",
            principal_status: "active",
            credential_id: "credential-harness",
        }),
        alias: Some("triage-agent"),
        decision: Some(DecisionFact {
            decision: "deny",
            reason_code: "no_matching_grant",
            policy_id: None,
        }),
        assignment: None,
        identifiers: &[("incident_id", "incident-harness")],
    });

    assert_eq!(projection.outcome, "denied");
    assert_eq!(
        projection.correlation_refs,
        vec![("incident_ref".to_owned(), "incident_id", "incident-harness")]
    );
    assert_eq!(
        projection.identity.unwrap().principal_ref,
        ("principal", "principal-harness")
    );
    assert_eq!(
        projection.resource.unwrap().resource_ref,
        ("resource", "triage-agent")
    );
    assert_eq!(projection.policy_decision.unwrap().decision, "deny");
    assert!(projection.routing.is_none());
}

#[test]
fn audit_unavailable_is_suppressed_not_persisted_evidence() {
    let projection = project_responses_audit(&AuditRequest {
        status: 503,
        reason: Some("audit_unavailable"),
        context: None,
        alias: None,
        decision: None,
        assignment: None,
        identifiers: &[],
    });
    assert_eq!(projection.outcome, "error");
    assert_eq!(projection.authoritative_acceptance, "rejected");
    assert_eq!(projection.ordinary_result, "suppressed");
    assert!(projection.identity.is_none());
}

#[test]
fn any_responses_403_is_denied_and_other_statuses_follow_threshold() {
    for (status, expected) in [
        (200, "success"),
        (399, "success"),
        (400, "error"),
        (403, "denied"),
        (404, "error"),
        (503, "error"),
    ] {
        let projection = project_responses_audit(&AuditRequest {
            status,
            reason: None,
            context: None,
            alias: None,
            decision: None,
            assignment: None,
            identifiers: &[],
        });
        assert_eq!(projection.outcome, expected, "status: {status}");
    }
}

#[test]
fn assignment_and_grant_evidence_preserve_existing_domains_and_router() {
    let projection = project_responses_audit(&AuditRequest {
        status: 200,
        reason: None,
        context: None,
        alias: Some("triage-agent"),
        decision: Some(DecisionFact {
            decision: "allow",
            reason_code: "grant_matched",
            policy_id: Some("grant-harness"),
        }),
        assignment: Some(AssignmentFact {
            concrete_model: "provider/model",
            inference_provider: "inference-partner",
        }),
        identifiers: &[("trace", "trace-harness")],
    });
    assert!(projection.identity.is_none());
    assert!(projection.resource.is_none());
    assert!(projection.model_alias_ref.is_none());
    assert_eq!(
        projection.correlation_refs,
        vec![("trace_ref".to_owned(), "trace", "trace-harness")]
    );
    assert_eq!(
        projection.policy_decision.unwrap().grant_ref,
        Some(("grant", "grant-harness"))
    );
    let routing = projection.routing.unwrap();
    assert_eq!(routing.model_ref, ("model", "provider/model"));
    assert_eq!(routing.router, "openrouter");
    assert_eq!(routing.provider_ref, ("provider", "inference-partner"));
}
