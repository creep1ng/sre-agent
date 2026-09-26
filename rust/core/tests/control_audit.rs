use sre_agent_core::control_audit::{project_control_audit, ControlAuditRequest, DecisionFact};

fn request<'a>() -> ControlAuditRequest<'a> {
    ControlAuditRequest {
        status: 403,
        stage: "authorization",
        reason: Some("resource_unavailable"),
        terminal: true,
        retryable: false,
        context: Some(("admin", "human", "active", "credential")),
        resource: Some(("administrative_control", "credentials")),
        decision: Some(DecisionFact {
            decision: "deny",
            policy_id: None,
        }),
        authorization_denial_cause: Some("grant_not_applicable"),
    }
}

#[test]
fn hidden_denial_and_authorized_target_miss_remain_distinct() {
    let denial = project_control_audit(&request()).unwrap();
    assert_eq!(denial.outcome, "denied");
    assert_eq!(denial.reason, Some("no_matching_grant"));
    assert_eq!(
        denial.authorization_denial_cause,
        Some("grant_not_applicable")
    );
    assert_eq!(
        denial.resource.unwrap().resource_ref,
        ("resource", "administrative_control/credentials".to_owned())
    );

    let mut hidden = request();
    hidden.status = 404;
    let hidden = project_control_audit(&hidden).unwrap();
    assert_eq!(hidden.outcome, "denied");

    let mut target_miss = request();
    target_miss.status = 404;
    target_miss.reason = Some("resource_not_found");
    target_miss.decision = Some(DecisionFact {
        decision: "allow",
        policy_id: Some("grant"),
    });
    let target_miss = project_control_audit(&target_miss).unwrap();
    assert_eq!(target_miss.outcome, "error");
    assert_eq!(target_miss.reason, Some("resource_not_found"));
    assert_eq!(target_miss.authorization_denial_cause, None);
    assert_eq!(
        target_miss.policy_decision.unwrap().grant_ref,
        Some(("grant", "grant"))
    );
}

#[test]
fn non_authorization_stage_suppresses_subject_and_maps_terminal_reason() {
    let mut input = request();
    input.stage = "validation";
    input.status = 422;
    input.reason = Some("validation_error");
    let projection = project_control_audit(&input).unwrap();
    assert_eq!(projection.stage, "audit");
    assert_eq!(projection.reason, Some("contract_validation_failed"));
    assert!(projection.identity.is_none());
    assert!(projection.resource.is_none());
    assert!(projection.policy_decision.is_none());
    assert_eq!(projection.authorization_denial_cause, None);
}

#[test]
fn missing_allow_policy_fails_closed_and_server_error_is_retryable() {
    let mut input = request();
    input.decision = Some(DecisionFact {
        decision: "allow",
        policy_id: None,
    });
    assert!(project_control_audit(&input).is_err());

    input.decision = Some(DecisionFact {
        decision: "allow",
        policy_id: Some("grant"),
    });
    input.status = 500;
    input.reason = Some("credential_issuance_failed");
    let projection = project_control_audit(&input).unwrap();
    assert_eq!(projection.outcome, "error");
    assert_eq!(projection.reason, Some("upstream_failed"));
    assert!(projection.retryable);
}
