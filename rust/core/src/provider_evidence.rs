//! Closed OpenRouter routing evidence decisions, independent of HTTP and Python.

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Number(pub String);

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Scalar {
    Null,
    Bool(bool),
    Text(String),
    Number(Number),
    Other,
}

impl Scalar {
    fn text_equals(&self, expected: &str) -> bool {
        matches!(self, Self::Text(value) if value == expected)
    }

    fn integer_equals(&self, expected: u16) -> bool {
        match self {
            Self::Bool(value) => *value && expected == 1,
            Self::Number(value) => decimal_equals(&value.0, expected),
            _ => false,
        }
    }
}

#[derive(Clone, Debug)]
pub struct Endpoint {
    pub selected_is_true: bool,
    pub provider_folded: Option<String>,
    pub model: Scalar,
}

#[derive(Clone, Debug)]
pub struct Attempt {
    pub provider_folded: Option<String>,
    pub model: Scalar,
    pub status: Scalar,
}

#[derive(Clone, Debug)]
pub struct Metadata {
    pub requested: Scalar,
    pub strategy: Scalar,
    pub attempt: Scalar,
    pub available: Option<Vec<Endpoint>>,
    /// None means missing/null; malformed non-lists normalize to an empty list.
    pub attempts: Option<Vec<Attempt>>,
}

#[derive(Clone, Debug)]
pub struct ResponseFacts {
    pub generation_id: Option<String>,
    pub model: Scalar,
    pub error_is_none: bool,
    pub incomplete_is_none: bool,
    pub metadata: Option<Metadata>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum RoutingStage {
    Accept,
    Reject(&'static str),
    CatalogRequired(String),
}

#[derive(Debug, PartialEq, Eq)]
pub struct ResponseFoldPlan {
    pub selected_index: usize,
    pub attempt_index: Option<usize>,
}

pub fn response_body_valid(facts: &ResponseFacts, request_model: &str) -> bool {
    facts
        .generation_id
        .as_deref()
        .is_some_and(valid_generation_id)
        && facts.model.text_equals(request_model)
        && facts.error_is_none
        && facts.incomplete_is_none
}

/// Identify only provider names that can affect the final Rust decision.
pub fn response_fold_plan(facts: &ResponseFacts, request_model: &str) -> Option<ResponseFoldPlan> {
    if !response_body_valid(facts, request_model) {
        return None;
    }
    let metadata = facts.metadata.as_ref()?;
    let available = metadata.available.as_ref()?;
    let mut selected = available
        .iter()
        .enumerate()
        .filter(|(_, item)| item.selected_is_true);
    let (Some((selected_index, endpoint)), None) = (selected.next(), selected.next()) else {
        return None;
    };
    if !metadata.requested.text_equals(request_model)
        || !metadata.strategy.text_equals("direct")
        || !metadata.attempt.integer_equals(1)
        || !matches!(endpoint.model, Scalar::Text(_))
    {
        return None;
    }
    let attempt_index = match &metadata.attempts {
        None => None,
        Some(attempts)
            if attempts.len() == 1
                && attempts[0].model == endpoint.model
                && attempts[0].status.integer_equals(200) =>
        {
            Some(0)
        }
        Some(_) => return None,
    };
    Some(ResponseFoldPlan {
        selected_index,
        attempt_index,
    })
}

pub fn inspect_response(
    facts: &ResponseFacts,
    request_model: &str,
    request_provider_folded: &str,
) -> RoutingStage {
    if !response_body_valid(facts, request_model) {
        return RoutingStage::Reject("invalid_response");
    }
    let Some(plan) = response_fold_plan(facts, request_model) else {
        return RoutingStage::Reject("evidence_invalid");
    };
    let metadata = facts
        .metadata
        .as_ref()
        .expect("fold plan requires metadata");
    let endpoint = &metadata
        .available
        .as_ref()
        .expect("fold plan requires list")[plan.selected_index];
    if endpoint.provider_folded.as_deref() != Some(request_provider_folded) {
        return RoutingStage::Reject("evidence_invalid");
    }
    if plan.attempt_index.is_some_and(|index| {
        metadata
            .attempts
            .as_ref()
            .expect("fold plan requires attempts")[index]
            .provider_folded
            .as_deref()
            != Some(request_provider_folded)
    }) {
        return RoutingStage::Reject("evidence_invalid");
    }
    match &endpoint.model {
        Scalar::Text(model) if model == request_model => RoutingStage::Accept,
        Scalar::Text(model) => RoutingStage::CatalogRequired(model.clone()),
        _ => RoutingStage::Reject("evidence_invalid"),
    }
}

#[derive(Clone, Debug)]
pub struct CatalogEndpoint {
    pub model_id: Scalar,
    pub provider_name: Option<String>,
    pub provider_folded: Option<String>,
    pub tag: Option<String>,
    pub name: Scalar,
}

#[derive(Clone, Debug)]
pub struct CatalogFacts {
    pub id: Scalar,
    pub endpoints: Option<Vec<CatalogEndpoint>>,
}

pub fn catalog_id_valid(id: &Scalar, request_model: &str) -> bool {
    id.text_equals(request_model)
}

pub fn catalog_model_id_valid(id: &Scalar, request_model: &str) -> bool {
    id.text_equals(request_model)
}

pub fn catalog_fold_indices(facts: &CatalogFacts, request_model: &str) -> Vec<usize> {
    if !catalog_id_valid(&facts.id, request_model) {
        return Vec::new();
    }
    facts.endpoints.as_ref().map_or_else(Vec::new, |endpoints| {
        endpoints
            .iter()
            .enumerate()
            .filter(|(_, endpoint)| {
                endpoint.provider_name.is_some()
                    && endpoint.tag.is_some()
                    && catalog_model_id_valid(&endpoint.model_id, request_model)
            })
            .map(|(index, _)| index)
            .collect()
    })
}

pub fn confirm_catalog(
    facts: &CatalogFacts,
    selected_model: &str,
    request_model: &str,
    request_provider: &str,
    request_provider_folded: &str,
) -> bool {
    if !catalog_id_valid(&facts.id, request_model) {
        return false;
    }
    let Some(endpoints) = &facts.endpoints else {
        return false;
    };
    endpoints
        .iter()
        .filter(|endpoint| {
            let (Some(provider_name), Some(tag)) = (&endpoint.provider_name, &endpoint.tag) else {
                return false;
            };
            endpoint.model_id.text_equals(request_model)
                && endpoint.provider_folded.as_deref() == Some(request_provider_folded)
                && (tag == request_provider || tag.starts_with(&format!("{request_provider}/")))
                && endpoint
                    .name
                    .text_equals(&format!("{provider_name} | {selected_model}"))
        })
        .take(2)
        .count()
        == 1
}

fn valid_generation_id(value: &str) -> bool {
    value.strip_prefix("gen-").is_some_and(|suffix| {
        (8..=128).contains(&suffix.len())
            && suffix
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
    })
}

/// Compare JSON/Python decimal text exactly, without f64 rounding or magnitude overflow.
fn decimal_equals(value: &str, expected: u16) -> bool {
    let value = value.strip_prefix('+').unwrap_or(value);
    if value.starts_with('-') {
        return false;
    }
    let (mantissa, exponent) = value
        .split_once(['e', 'E'])
        .map_or((value, "0"), |(base, power)| (base, power));
    let Ok(exponent) = exponent.parse::<i64>() else {
        return false;
    };
    let (integer, fractional) = mantissa
        .split_once('.')
        .map_or((mantissa, ""), |(left, right)| (left, right));
    if integer.is_empty() && fractional.is_empty() {
        return false;
    }
    if !integer
        .bytes()
        .chain(fractional.bytes())
        .all(|byte| byte.is_ascii_digit())
    {
        return false;
    }
    let digits = format!("{integer}{fractional}");
    let significant = digits.trim_start_matches('0');
    if significant.is_empty() {
        return false;
    }
    let trailing = significant.len() - significant.trim_end_matches('0').len();
    let significant = significant.trim_end_matches('0');
    let Ok(fractional_len) = i64::try_from(fractional.len()) else {
        return false;
    };
    let Ok(trailing) = i64::try_from(trailing) else {
        return false;
    };
    let Some(power) = exponent
        .checked_sub(fractional_len)
        .and_then(|power| power.checked_add(trailing))
    else {
        return false;
    };
    let expected = expected.to_string();
    let expected_trailing = expected.len() - expected.trim_end_matches('0').len();
    significant == expected.trim_end_matches('0') && power == expected_trailing as i64
}
