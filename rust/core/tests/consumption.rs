use sre_agent_core::consumption::{project, Evidence, UsageFacts, UsageState};

fn value(value: &'static str) -> Evidence<'static> {
    Evidence {
        value: Some(value),
        invalid: false,
        present: true,
    }
}

fn missing() -> Evidence<'static> {
    Evidence {
        value: None,
        invalid: false,
        present: false,
    }
}

fn facts() -> UsageFacts<'static> {
    UsageFacts {
        state: UsageState::Mapping,
        nonempty: true,
        input: value("11"),
        output: value("7"),
        total: value("18"),
        cost: value("0.0012300"),
        timestamp_valid: true,
        failure_context: false,
    }
}

#[test]
fn complete_requires_consistent_tokens_and_timestamped_cost() {
    let result = project(&facts());
    assert_eq!(result.availability, "complete");
    assert_eq!(result.total, Some("18"));
    assert_eq!(result.cost, Some("0.0012300"));
    assert!(result.billing_context);

    let mut inconsistent = facts();
    inconsistent.total = value("17");
    let result = project(&inconsistent);
    assert_eq!(result.availability, "partial");
    assert_eq!(result.total, None);
    assert_eq!(result.cost, Some("0.0012300"));

    let mut missing_timestamp = facts();
    missing_timestamp.timestamp_valid = false;
    let result = project(&missing_timestamp);
    assert_eq!(result.availability, "partial");
    assert_eq!(result.cost, None);
    assert!(!result.billing_context);
}

#[test]
fn empty_and_invalid_usage_have_no_evidence_fields() {
    let mut facts = facts();
    facts.state = UsageState::Missing;
    assert_eq!(project(&facts).availability, "absent");
    facts.state = UsageState::Invalid;
    assert_eq!(project(&facts).availability, "unavailable");

    facts.state = UsageState::Mapping;
    facts.nonempty = false;
    facts.input = missing();
    facts.output = missing();
    facts.total = missing();
    facts.cost = missing();
    assert_eq!(project(&facts).availability, "absent");
    facts.nonempty = true;
    assert_eq!(project(&facts).availability, "unavailable");
    facts.nonempty = false;
    facts.input = Evidence {
        value: None,
        invalid: true,
        present: true,
    };
    assert_eq!(project(&facts).availability, "unavailable");

    facts.input = missing();
    facts.failure_context = true;
    assert_eq!(project(&facts).availability, "unavailable");
}

#[test]
fn large_token_totals_do_not_overflow_native_arithmetic() {
    let mut facts = facts();
    facts.input = value("9999999999999999999999999999999999999999");
    facts.output = value("1");
    facts.total = value("10000000000000000000000000000000000000000");
    assert_eq!(project(&facts).availability, "complete");
}
