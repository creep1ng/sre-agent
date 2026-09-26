//! OpenRouter usage projection, independent of Python parsing and DTOs.

#[derive(Clone, Copy)]
pub struct Evidence<'a> {
    pub value: Option<&'a str>,
    pub invalid: bool,
    pub present: bool,
}

#[derive(Clone, Copy)]
pub enum UsageState {
    Missing,
    Invalid,
    Mapping,
}

pub struct UsageFacts<'a> {
    pub state: UsageState,
    pub nonempty: bool,
    pub input: Evidence<'a>,
    pub output: Evidence<'a>,
    pub total: Evidence<'a>,
    pub cost: Evidence<'a>,
    pub timestamp_valid: bool,
    pub failure_context: bool,
}

pub struct ConsumptionProjection<'a> {
    pub availability: &'static str,
    pub input: Option<&'a str>,
    pub output: Option<&'a str>,
    pub total: Option<&'a str>,
    pub cost: Option<&'a str>,
    pub billing_context: bool,
}

fn token<'a>(fact: Evidence<'a>) -> (Option<&'a str>, bool) {
    let valid = fact
        .value
        .is_none_or(|value| !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()));
    (fact.value.filter(|_| valid), fact.invalid || !valid)
}

fn canonical(value: &str) -> &str {
    let stripped = value.trim_start_matches('0');
    if stripped.is_empty() {
        "0"
    } else {
        stripped
    }
}

fn total_matches(input: &str, output: &str, total: &str) -> bool {
    let mut input = canonical(input).bytes().rev();
    let mut output = canonical(output).bytes().rev();
    let mut total = canonical(total).bytes().rev();
    let mut carry = 0;
    loop {
        let left = input.next();
        let right = output.next();
        if left.is_none() && right.is_none() && carry == 0 {
            return total.next().is_none();
        }
        let sum = left.unwrap_or(b'0') - b'0' + right.unwrap_or(b'0') - b'0' + carry;
        if total.next() != Some(b'0' + sum % 10) {
            return false;
        }
        carry = sum / 10;
    }
}

/// The sole availability, contradiction, and billing-context decision authority.
pub fn project<'a>(facts: &UsageFacts<'a>) -> ConsumptionProjection<'a> {
    let empty = |availability| ConsumptionProjection {
        availability,
        input: None,
        output: None,
        total: None,
        cost: None,
        billing_context: false,
    };
    match facts.state {
        UsageState::Missing => {
            return empty(if facts.failure_context {
                "unavailable"
            } else {
                "absent"
            })
        }
        UsageState::Invalid => return empty("unavailable"),
        UsageState::Mapping => {}
    }

    let (input, input_invalid) = token(facts.input);
    let (output, output_invalid) = token(facts.output);
    let (mut total, total_invalid) = token(facts.total);
    let mut invalid = input_invalid || output_invalid || total_invalid || facts.cost.invalid;
    if let (Some(input), Some(output), Some(value)) = (input, output, total) {
        if !total_matches(input, output, value) {
            total = None;
            invalid = true;
        }
    }
    let cost = facts.cost.value.filter(|_| facts.timestamp_valid);
    if facts.cost.value.is_some() && !facts.timestamp_valid {
        invalid = true;
    }
    let has_values = input.is_some() || output.is_some() || total.is_some() || cost.is_some();
    if !has_values {
        let known = facts.input.present
            || facts.output.present
            || facts.total.present
            || facts.cost.present;
        return empty(
            if invalid || known || facts.nonempty || facts.failure_context {
                "unavailable"
            } else {
                "absent"
            },
        );
    }
    let complete = input.is_some() && output.is_some() && total.is_some() && cost.is_some();
    ConsumptionProjection {
        availability: if complete && !invalid {
            "complete"
        } else {
            "partial"
        },
        input,
        output,
        total,
        cost,
        billing_context: cost.is_some(),
    }
}
