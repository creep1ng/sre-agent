//! Ordered, framework-independent admission for a named incident transition.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Verdict {
    Accepted,
    SourceMismatch,
    ActorForbidden,
    HumanReferenceMissing,
    ActorReferenceInvalid,
    ApprovalRequired,
    OutcomeRequired,
}

impl Verdict {
    pub const fn code(self) -> &'static str {
        match self {
            Self::Accepted => "accepted",
            Self::SourceMismatch => "source_mismatch",
            Self::ActorForbidden => "actor_forbidden",
            Self::HumanReferenceMissing => "human_reference_missing",
            Self::ActorReferenceInvalid => "actor_reference_invalid",
            Self::ApprovalRequired => "approval_required",
            Self::OutcomeRequired => "outcome_required",
        }
    }
}

#[derive(Debug, Eq, PartialEq)]
pub struct Admission<'a> {
    pub verdict: Verdict,
    pub selected_outcome: Option<&'a str>,
    pub preserve_raw_outcome: bool,
}

pub enum OutcomeFact<'a> {
    Missing,
    Text(&'a str),
    Other { truthy: bool },
}

pub struct AdmissionFacts<'a> {
    pub current_state: Option<&'a str>,
    pub source: &'a str,
    pub actor: &'a str,
    pub actors: &'a [&'a str],
    pub reference: Option<(&'a str, &'a str)>,
    pub requires_approval: bool,
    pub approval: bool,
    pub outcome: Option<&'a str>,
    pub outcomes: &'a [&'a str],
}

pub fn check_source(current_state: Option<&str>, source: &str) -> Verdict {
    if current_state == Some(source) {
        Verdict::Accepted
    } else {
        Verdict::SourceMismatch
    }
}

pub fn check_actor(actor: Option<&str>, actors: &[&str]) -> Verdict {
    if actor.is_some_and(|actor| actors.contains(&actor)) {
        Verdict::Accepted
    } else {
        Verdict::ActorForbidden
    }
}

pub fn check_reference_presence(actor: &str, present: bool) -> Verdict {
    if actor == "human" && !present {
        Verdict::HumanReferenceMissing
    } else {
        Verdict::Accepted
    }
}

pub fn check_reference_version(version: Option<&str>) -> Verdict {
    if version == Some("1.0.0") {
        Verdict::Accepted
    } else {
        Verdict::ActorReferenceInvalid
    }
}

pub fn check_reference_principal(principal: &str) -> Verdict {
    let bytes = principal.as_bytes();
    if (3..=64).contains(&bytes.len())
        && bytes[0].is_ascii_lowercase()
        && bytes[1..]
            .iter()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"_-".contains(byte))
    {
        Verdict::Accepted
    } else {
        Verdict::ActorReferenceInvalid
    }
}

pub fn check_approval(actor: &str, requires_approval: bool, approval: bool) -> Verdict {
    if requires_approval && (actor != "human" || !approval) {
        Verdict::ApprovalRequired
    } else {
        Verdict::Accepted
    }
}

pub fn approval_fact_required(actor: &str, requires_approval: bool) -> bool {
    requires_approval && actor == "human"
}

pub fn select_outcome<'a>(outcome: OutcomeFact<'a>, outcomes: &'a [&'a str]) -> Admission<'a> {
    let valid = match outcome {
        OutcomeFact::Missing => outcomes.is_empty() || outcomes.len() == 1,
        OutcomeFact::Text(value) => outcomes.is_empty() || outcomes.contains(&value),
        OutcomeFact::Other { .. } => outcomes.is_empty(),
    };
    if !valid {
        return Admission {
            verdict: Verdict::OutcomeRequired,
            selected_outcome: None,
            preserve_raw_outcome: false,
        };
    }
    let (selected_outcome, preserve_raw_outcome) = match outcome {
        OutcomeFact::Missing | OutcomeFact::Text("") => (outcomes.first().copied(), false),
        OutcomeFact::Text(value) => (Some(value), false),
        OutcomeFact::Other { truthy } => (None, truthy),
    };
    Admission {
        verdict: Verdict::Accepted,
        selected_outcome,
        preserve_raw_outcome,
    }
}

/// Compose the same staged decisions for core callers and Rust-only parity tests.
pub fn admit<'a>(facts: &AdmissionFacts<'a>) -> Admission<'a> {
    let reject = |verdict| Admission {
        verdict,
        selected_outcome: None,
        preserve_raw_outcome: false,
    };
    let verdict = check_source(facts.current_state, facts.source);
    if verdict != Verdict::Accepted {
        return reject(verdict);
    }
    let verdict = check_actor(Some(facts.actor), facts.actors);
    if verdict != Verdict::Accepted {
        return reject(verdict);
    }
    let verdict = check_reference_presence(facts.actor, facts.reference.is_some());
    if verdict != Verdict::Accepted {
        return reject(verdict);
    }
    if let Some((version, principal)) = facts.reference {
        let verdict = check_reference_version(Some(version));
        if verdict != Verdict::Accepted {
            return reject(verdict);
        }
        let verdict = check_reference_principal(principal);
        if verdict != Verdict::Accepted {
            return reject(verdict);
        }
    }
    let verdict = check_approval(facts.actor, facts.requires_approval, facts.approval);
    if verdict != Verdict::Accepted {
        return reject(verdict);
    }
    let outcome = facts
        .outcome
        .map_or(OutcomeFact::Missing, OutcomeFact::Text);
    select_outcome(outcome, facts.outcomes)
}
