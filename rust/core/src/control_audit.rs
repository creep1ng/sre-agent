//! Administrative terminal-audit policy, independent of clocks, keys, and storage.

pub type RefSpec<'a> = (&'static str, &'a str);

pub struct DecisionFact<'a> {
    pub decision: &'a str,
    pub policy_id: Option<&'a str>,
}

pub struct ControlAuditRequest<'a> {
    pub status: i64,
    pub stage: &'a str,
    pub reason: Option<&'a str>,
    /// Terminal service calls normalize stage/reason and derive retryability.
    pub terminal: bool,
    /// Direct projector calls retain their caller-supplied retryability.
    pub retryable: bool,
    pub context: Option<(&'a str, &'a str, &'a str, &'a str)>,
    pub resource: Option<(&'a str, &'a str)>,
    pub decision: Option<DecisionFact<'a>>,
    pub authorization_denial_cause: Option<&'a str>,
}

pub struct IdentityProjection<'a> {
    pub principal_ref: RefSpec<'a>,
    pub principal_kind: &'a str,
    pub principal_status: &'a str,
    pub credential_ref: RefSpec<'a>,
}

pub struct ResourceProjection<'a> {
    pub resource_type: &'a str,
    pub resource_ref: (&'static str, String),
}

pub struct DecisionProjection<'a> {
    pub decision: &'static str,
    pub reason_code: &'static str,
    pub grant_ref: Option<RefSpec<'a>>,
}

pub struct ControlAuditProjection<'a> {
    pub stage: &'a str,
    pub outcome: &'static str,
    pub reason: Option<&'a str>,
    pub retryable: bool,
    pub authorization_denial_cause: Option<&'a str>,
    pub identity: Option<IdentityProjection<'a>>,
    pub resource: Option<ResourceProjection<'a>>,
    pub policy_decision: Option<DecisionProjection<'a>>,
}

fn terminal_reason(reason: Option<&str>) -> Option<&str> {
    match reason {
        Some("validation_error" | "invalid_idempotency_key" | "credential_inactive") => {
            Some("contract_validation_failed")
        }
        Some("idempotency_conflict") => Some("status_conflict"),
        Some("rotation_failed" | "credential_issuance_failed") => Some("upstream_failed"),
        Some("resource_unavailable") => Some("no_matching_grant"),
        other => other,
    }
}

/// Determines whether subject facts are relevant before an adapter reads them.
pub fn retain_control_subject(terminal: bool, stage: &str) -> bool {
    !terminal || stage == "authorization"
}

/// Produces reference specifications, never a digest or an append attestation.
pub fn project_control_audit<'a>(
    request: &ControlAuditRequest<'a>,
) -> Result<ControlAuditProjection<'a>, &'static str> {
    let stage = if request.terminal && request.stage != "authorization" {
        "audit"
    } else {
        request.stage
    };
    let retain_subject = retain_control_subject(request.terminal, request.stage);
    let identity = request.context.filter(|_| retain_subject).map(
        |(principal_id, kind, status, credential_id)| IdentityProjection {
            principal_ref: ("principal", principal_id),
            principal_kind: kind,
            principal_status: status,
            credential_ref: ("credential", credential_id),
        },
    );
    let resource =
        request
            .resource
            .filter(|_| retain_subject)
            .map(|(resource_type, resource_id)| ResourceProjection {
                resource_type,
                resource_ref: ("resource", format!("{resource_type}/{resource_id}")),
            });
    let policy_decision = request
        .decision
        .as_ref()
        .filter(|_| retain_subject)
        .map(|decision| {
            if decision.decision == "allow" {
                let policy_id = decision
                    .policy_id
                    .ok_or("control allow requires a grant policy_id")?;
                Ok(DecisionProjection {
                    decision: "allow",
                    reason_code: "grant_matched",
                    grant_ref: Some(("grant", policy_id)),
                })
            } else {
                Ok(DecisionProjection {
                    decision: "deny",
                    reason_code: "no_matching_grant",
                    grant_ref: None,
                })
            }
        })
        .transpose()?;
    let denied = policy_decision
        .as_ref()
        .is_some_and(|decision| decision.decision == "deny");
    let outcome = if denied {
        "denied"
    } else if request.status < 400 {
        "success"
    } else {
        "error"
    };
    let reason = if denied {
        Some("no_matching_grant")
    } else if request.terminal {
        terminal_reason(request.reason)
    } else {
        request.reason
    };
    let authorization_denial_cause =
        if stage == "authorization" && matches!(request.status, 403 | 404) && denied {
            request.authorization_denial_cause
        } else {
            None
        };
    let retryable = if request.terminal {
        matches!(request.status, 500 | 503 | 504)
    } else {
        request.retryable
    };
    Ok(ControlAuditProjection {
        stage,
        outcome,
        reason,
        retryable,
        authorization_denial_cause,
        identity,
        resource,
        policy_decision,
    })
}
