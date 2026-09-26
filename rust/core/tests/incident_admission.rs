use sre_agent_core::incident_admission::{
    admit, approval_fact_required, check_actor, check_reference_version, select_outcome,
    AdmissionFacts, OutcomeFact, Verdict,
};

fn facts<'a>() -> AdmissionFacts<'a> {
    AdmissionFacts {
        current_state: Some("mitigating"),
        source: "mitigating",
        actor: "human",
        actors: &["human"],
        reference: Some(("1.0.0", "operator_one")),
        requires_approval: true,
        approval: true,
        outcome: None,
        outcomes: &["approve"],
    }
}

#[test]
fn admission_precedence_and_selected_outcome() {
    let accepted = admit(&facts());
    assert_eq!(accepted.verdict, Verdict::Accepted);
    assert_eq!(accepted.selected_outcome, Some("approve"));

    let mut request = facts();
    request.current_state = Some("investigating");
    request.actor = "agent";
    request.reference = None;
    request.approval = false;
    request.outcome = Some("reject");
    assert_eq!(admit(&request).verdict, Verdict::SourceMismatch);
    request.current_state = Some("mitigating");
    assert_eq!(admit(&request).verdict, Verdict::ActorForbidden);
    request.actor = "human";
    assert_eq!(admit(&request).verdict, Verdict::HumanReferenceMissing);
    request.reference = Some(("2.0.0", "operator_one"));
    assert_eq!(admit(&request).verdict, Verdict::ActorReferenceInvalid);
    request.reference = Some(("1.0.0", "operator_one"));
    assert_eq!(admit(&request).verdict, Verdict::ApprovalRequired);
    request.approval = true;
    assert_eq!(admit(&request).verdict, Verdict::OutcomeRequired);
}

#[test]
fn reference_and_outcome_match_python_contract() {
    let mut request = facts();
    let too_long = "a".repeat(65);
    for principal in ["ab", "Operator_one", "ñame", too_long.as_str()] {
        request.reference = Some(("1.0.0", principal));
        assert_eq!(admit(&request).verdict, Verdict::ActorReferenceInvalid);
    }
    request.reference = Some(("1.0.0", "a_0"));
    request.outcome = Some("approve");
    assert_eq!(admit(&request).selected_outcome, Some("approve"));
    request.outcomes = &[];
    request.outcome = Some("unconstrained");
    assert_eq!(admit(&request).selected_outcome, Some("unconstrained"));
    request.outcome = Some("");
    assert_eq!(admit(&request).selected_outcome, None);
}

#[test]
fn approval_fact_is_relevant_only_to_required_human_transition() {
    assert!(approval_fact_required("human", true));
    assert!(!approval_fact_required("human", false));
    assert!(!approval_fact_required("agent", true));
}

#[test]
fn malformed_facts_reject_without_transport_exception() {
    assert_eq!(check_actor(None, &["human"]), Verdict::ActorForbidden);
    assert_eq!(
        check_reference_version(None),
        Verdict::ActorReferenceInvalid
    );
    assert_eq!(
        select_outcome(OutcomeFact::Other { truthy: true }, &["approve"]).verdict,
        Verdict::OutcomeRequired
    );
    let unlisted = select_outcome(OutcomeFact::Other { truthy: true }, &[]);
    assert_eq!(unlisted.verdict, Verdict::Accepted);
    assert!(unlisted.preserve_raw_outcome);
    assert!(!select_outcome(OutcomeFact::Other { truthy: false }, &[]).preserve_raw_outcome);
}
