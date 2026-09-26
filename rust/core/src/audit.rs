//! Metadata-only responses audit projection; no keys, clocks, or storage live here.

pub type RefSpec<'a> = (&'static str, &'a str);

pub struct ContextFact<'a> {
    pub principal_id: &'a str,
    pub principal_kind: &'a str,
    pub principal_status: &'a str,
    pub credential_id: &'a str,
}

pub struct DecisionFact<'a> {
    pub decision: &'a str,
    pub reason_code: &'a str,
    pub policy_id: Option<&'a str>,
}

pub struct AssignmentFact<'a> {
    pub concrete_model: &'a str,
    pub inference_provider: &'a str,
}

pub struct AuditRequest<'a> {
    pub status: i64,
    pub reason: Option<&'a str>,
    pub context: Option<ContextFact<'a>>,
    pub alias: Option<&'a str>,
    pub decision: Option<DecisionFact<'a>>,
    pub assignment: Option<AssignmentFact<'a>>,
    pub identifiers: &'a [(&'a str, &'a str)],
}

pub struct IdentityProjection<'a> {
    pub principal_ref: RefSpec<'a>,
    pub principal_kind: &'a str,
    pub principal_status: &'a str,
    pub credential_ref: RefSpec<'a>,
}

pub struct ResourceProjection<'a> {
    pub resource_type: &'static str,
    pub resource_ref: RefSpec<'a>,
}

pub struct DecisionProjection<'a> {
    pub decision: &'a str,
    pub reason_code: &'a str,
    pub grant_ref: Option<RefSpec<'a>>,
}

pub struct RoutingProjection<'a> {
    pub model_ref: RefSpec<'a>,
    pub router: &'static str,
    pub provider_ref: RefSpec<'a>,
}

pub struct RedactionProjection {
    pub policy_version: &'static str,
    pub result: &'static str,
    pub source_class: &'static str,
    pub categories: &'static [&'static str],
    pub match_count: u16,
    pub sink_eligible: bool,
}

pub struct AuditProjection<'a> {
    pub operation: &'static str,
    pub action: &'static str,
    pub outcome: &'static str,
    pub correlation_refs: Vec<(String, &'a str, &'a str)>,
    pub identity: Option<IdentityProjection<'a>>,
    pub resource: Option<ResourceProjection<'a>>,
    pub model_alias_ref: Option<RefSpec<'a>>,
    pub policy_decision: Option<DecisionProjection<'a>>,
    pub routing: Option<RoutingProjection<'a>>,
    pub redaction: RedactionProjection,
    pub content_state: &'static str,
    pub authoritative_acceptance: &'static str,
    pub ordinary_result: &'static str,
    pub exporter_result: &'static str,
}

/// Decides which metadata may be projected. Adapters hash reference specs and
/// validate/persist the event; this does not redact runtime content or attest an append.
pub fn project_responses_audit<'a>(request: &AuditRequest<'a>) -> AuditProjection<'a> {
    let outcome = if request.status < 400 {
        "success"
    } else if request.status == 403 {
        "denied"
    } else {
        "error"
    };
    let correlation_refs = request
        .identifiers
        .iter()
        .map(|(name, value)| {
            (
                format!("{}_ref", name.strip_suffix("_id").unwrap_or(name)),
                *name,
                *value,
            )
        })
        .collect();
    let identity = request.context.as_ref().map(|context| IdentityProjection {
        principal_ref: ("principal", context.principal_id),
        principal_kind: context.principal_kind,
        principal_status: context.principal_status,
        credential_ref: ("credential", context.credential_id),
    });
    let (resource, model_alias_ref) = match (&request.context, request.alias) {
        (Some(_), Some(alias)) => (
            Some(ResourceProjection {
                resource_type: "llm_model",
                resource_ref: ("resource", alias),
            }),
            Some(("model_alias", alias)),
        ),
        _ => (None, None),
    };
    let policy_decision = request
        .decision
        .as_ref()
        .map(|decision| DecisionProjection {
            decision: decision.decision,
            reason_code: decision.reason_code,
            grant_ref: decision
                .policy_id
                .filter(|policy_id| !policy_id.is_empty())
                .map(|policy_id| ("grant", policy_id)),
        });
    let routing = request
        .assignment
        .as_ref()
        .map(|assignment| RoutingProjection {
            model_ref: ("model", assignment.concrete_model),
            router: "openrouter",
            provider_ref: ("provider", assignment.inference_provider),
        });
    let audit_unavailable = request.reason == Some("audit_unavailable");
    AuditProjection {
        operation: "responses.create",
        action: "invoke",
        outcome,
        correlation_refs,
        identity,
        resource,
        model_alias_ref,
        policy_decision,
        routing,
        redaction: RedactionProjection {
            policy_version: "redaction-1.0.0",
            result: "success",
            source_class: "none",
            categories: &[],
            match_count: 0,
            sink_eligible: false,
        },
        content_state: "absent",
        authoritative_acceptance: if audit_unavailable {
            "rejected"
        } else {
            "accepted"
        },
        ordinary_result: if audit_unavailable {
            "suppressed"
        } else {
            "released"
        },
        exporter_result: "not_attempted",
    }
}
