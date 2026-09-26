//! Framework-independent gateway and core decisions.

pub mod audit;
pub mod consumption;
pub mod control_audit;
pub mod incident_admission;
pub mod openrouter_output;
pub mod provider_evidence;
pub mod provider_failure;

/// Facts supplied by adapters; no infrastructure is called from the core.
pub struct AuthorizationRequest<'a> {
    pub principal_status: &'a str,
    pub principal_id: &'a str,
    pub action: &'a str,
    pub resource_type: &'a str,
    pub resource_id: &'a str,
    pub resource: Option<ResourceFact<'a>>,
    pub grant: Option<GrantFact<'a>>,
}

pub struct ResourceFact<'a> {
    pub resource_type: &'a str,
    pub resource_id: &'a str,
    pub status: &'a str,
}

pub struct GrantFact<'a> {
    pub grant_id: &'a str,
    pub principal_id: &'a str,
    pub action: &'a str,
    pub resource_type: &'a str,
    pub resource_id: &'a str,
    pub effect: &'a str,
    pub status: &'a str,
}

pub struct AuthorizationDecision<'a> {
    pub allowed: bool,
    pub reason_code: &'static str,
    pub policy_id: Option<&'a str>,
    pub denial_cause: Option<&'static str>,
}

fn deny(cause: &'static str) -> AuthorizationDecision<'static> {
    AuthorizationDecision {
        allowed: false,
        reason_code: "no_matching_grant",
        policy_id: None,
        denial_cause: Some(cause),
    }
}

/// The sole authorization policy authority. Optional facts cannot bypass precedence.
pub fn evaluate_authorization<'a>(request: &AuthorizationRequest<'a>) -> AuthorizationDecision<'a> {
    if request.principal_status != "active" {
        return deny("principal_inactive");
    }

    let Some(resource) = &request.resource else {
        return deny("resource_missing");
    };
    if resource.resource_type != request.resource_type
        || resource.resource_id != request.resource_id
    {
        return deny("resource_missing");
    }
    if resource.status != "active" {
        return deny("resource_inactive");
    }

    let Some(grant) = &request.grant else {
        return deny("grant_not_applicable");
    };
    if grant.principal_id != request.principal_id
        || grant.action != request.action
        || grant.resource_type != request.resource_type
        || grant.resource_id != request.resource_id
        || grant.effect != "allow"
        || grant.status != "active"
    {
        return deny("grant_not_applicable");
    }
    AuthorizationDecision {
        allowed: true,
        reason_code: "grant_matched",
        policy_id: Some(grant.grant_id),
        denial_cause: None,
    }
}

#[cfg(test)]
mod tests {
    use super::{evaluate_authorization, AuthorizationRequest, GrantFact, ResourceFact};

    fn request<'a>() -> AuthorizationRequest<'a> {
        AuthorizationRequest {
            principal_status: "active",
            principal_id: "human-subject",
            action: "invoke",
            resource_type: "skill",
            resource_id: "resource-id",
            resource: Some(ResourceFact {
                resource_type: "skill",
                resource_id: "resource-id",
                status: "active",
            }),
            grant: Some(GrantFact {
                grant_id: "grant-skill",
                principal_id: "human-subject",
                action: "invoke",
                resource_type: "skill",
                resource_id: "resource-id",
                effect: "allow",
                status: "active",
            }),
        }
    }

    #[test]
    fn exact_grant_allows_for_every_resource_kind() {
        for kind in [
            "llm_model",
            "mcp_server",
            "mcp_tool",
            "skill",
            "bok_collection",
            "administrative_control",
            "incident_workflow",
        ] {
            let mut facts = request();
            facts.resource_type = kind;
            facts.resource.as_mut().unwrap().resource_type = kind;
            facts.grant.as_mut().unwrap().resource_type = kind;
            let decision = evaluate_authorization(&facts);
            assert!(decision.allowed, "resource kind: {kind}");
            assert_eq!(decision.reason_code, "grant_matched");
            assert_eq!(decision.policy_id, Some("grant-skill"));
            assert_eq!(decision.denial_cause, None);
        }
    }

    #[test]
    fn precedence_and_public_denial_are_stable() {
        let cases = [
            ("inactive", false, false, "principal_inactive"),
            ("active", false, false, "resource_missing"),
            ("active", true, false, "resource_inactive"),
            ("active", true, true, "grant_not_applicable"),
        ];
        for (principal_status, resource_exists, resource_active, cause) in cases {
            let mut facts = request();
            facts.principal_status = principal_status;
            if !resource_exists {
                facts.resource = None;
            } else if !resource_active {
                facts.resource.as_mut().unwrap().status = "inactive";
            } else {
                facts.grant = None;
            }
            let decision = evaluate_authorization(&facts);
            assert!(!decision.allowed);
            assert_eq!(decision.reason_code, "no_matching_grant");
            assert_eq!(decision.policy_id, None);
            assert_eq!(decision.denial_cause, Some(cause));
        }
    }

    #[test]
    fn mismatched_resource_facts_are_missing() {
        for mismatch in 0..2 {
            let mut facts = request();
            let resource = facts.resource.as_mut().unwrap();
            if mismatch == 0 {
                resource.resource_type = "mcp_tool";
            } else {
                resource.resource_id = "other";
            }
            assert_eq!(
                evaluate_authorization(&facts).denial_cause,
                Some("resource_missing")
            );
        }
    }

    #[test]
    fn every_grant_field_must_match_exactly() {
        for mismatch in 0..6 {
            let mut facts = request();
            let grant = facts.grant.as_mut().unwrap();
            match mismatch {
                0 => grant.principal_id = "agent-subject",
                1 => grant.action = "run.read",
                2 => grant.resource_type = "mcp_tool",
                3 => grant.resource_id = "other",
                4 => grant.effect = "deny",
                _ => grant.status = "revoked",
            }
            assert_eq!(
                evaluate_authorization(&facts).denial_cause,
                Some("grant_not_applicable"),
                "mismatch field: {mismatch}"
            );
        }
    }
}
