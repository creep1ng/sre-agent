//! Python boundary for the Rust-owned core.

mod audit_reference;

use pyo3::buffer::PyBuffer;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::ffi;
use pyo3::prelude::*;
use pyo3::types::{
    PyAny, PyBool, PyByteArray, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple,
};
use sre_agent_core::audit::{
    project_responses_audit as project_audit, AssignmentFact, AuditRequest, ContextFact,
    DecisionFact,
};
use sre_agent_core::consumption::{project as project_usage, Evidence, UsageFacts, UsageState};
use sre_agent_core::control_audit::{
    project_control_audit as project_control, retain_control_subject, ControlAuditRequest,
    DecisionFact as ControlDecisionFact,
};
use sre_agent_core::incident_admission::{
    approval_fact_required, check_actor, check_approval, check_reference_presence,
    check_reference_principal, check_reference_version, check_source, select_outcome, OutcomeFact,
    Verdict,
};
use sre_agent_core::openrouter_output::{
    content_kind_relevant, message_kind_relevant, message_role_relevant, root_accepts, select_text,
    status_completed, ContentFact, MessageFact,
};
use sre_agent_core::provider_evidence::{
    catalog_fold_indices, catalog_id_valid, catalog_model_id_valid, confirm_catalog,
    inspect_response, response_body_valid, response_fold_plan, Attempt, CatalogEndpoint,
    CatalogFacts, Endpoint, Metadata, Number, ResponseFacts, RoutingStage, Scalar,
};
use sre_agent_core::provider_failure::map_provider_failure as classify_provider_failure;
use sre_agent_core::{
    evaluate_authorization as decide, AuthorizationRequest, GrantFact, ResourceFact,
};

type ResourceTuple = (String, String, String);
type GrantTuple = (String, String, String, String, String, String, String);

/// Apply the same C-level formatting operation used by Python f-strings.
fn f_string_format<'py>(
    value: &Bound<'py, PyAny>,
    spec: &Bound<'py, PyString>,
) -> PyResult<Bound<'py, PyAny>> {
    // SAFETY: PyObject_Format returns an owned reference or null with a Python error.
    unsafe {
        Bound::from_owned_ptr_or_err(
            value.py(),
            ffi::PyObject_Format(value.as_ptr(), spec.as_ptr()),
        )
    }
}

/// Hash one canonical ADR-005 audit reference without a Python crypto fallback.
#[pyfunction]
fn audit_reference_digest(
    key: &Bound<'_, PyAny>,
    domain: &Bound<'_, PyAny>,
    value: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let py = key.py();
    let spec = PyString::new(py, "");
    // Format both fields before encoding, as the original f-string does.
    let domain = f_string_format(domain, &spec)?;
    let value = f_string_format(value, &spec)?;
    let prefix = PyString::new(py, "sre-audit-v1\0");
    let separator = PyString::new(py, "\0");
    let segments = PyTuple::new(
        py,
        [
            prefix.as_any(),
            domain.as_any(),
            separator.as_any(),
            value.as_any(),
        ],
    )?;
    // Encoding the complete Python string preserves UnicodeEncodeError.object
    // and offsets from the former f-string + .encode() path.
    let canonical = PyString::new(py, "").call_method1("join", (segments,))?;
    let encoded = canonical.call_method0("encode")?;
    let encoded = encoded.cast::<PyBytes>()?;
    if !key.is_instance_of::<PyBytes>() && !key.is_instance_of::<PyByteArray>() {
        let name = key.get_type().name()?;
        return Err(PyTypeError::new_err(format!(
            "key: expected bytes or bytearray, but got '{name}'"
        )));
    }
    let key = PyBuffer::<u8>::get(key)?;
    let key = key.to_vec(py)?;
    Ok(audit_reference::digest(&key, encoded.as_bytes()))
}

/// Read each Python fact only after the preceding Rust verdict accepted it.
#[pyfunction]
fn admit_incident_transition(
    state: &Bound<'_, PyAny>,
    command: &Bound<'_, PyAny>,
    transition: &Bound<'_, PyAny>,
) -> PyResult<(&'static str, Py<PyAny>)> {
    let py = command.py();
    let current_state: Option<String> = state.call_method1("get", ("state",))?.extract()?;
    let source: String = transition.getattr("source")?.extract()?;
    let verdict = check_source(current_state.as_deref(), &source);
    if verdict != Verdict::Accepted {
        return Ok((verdict.code(), py.None()));
    }

    let actor_value = command.getattr("actor")?;
    let actor: Option<String> = actor_value
        .is_instance_of::<PyString>()
        .then(|| actor_value.extract())
        .transpose()?;
    let actors = transition
        .getattr("actors")?
        .try_iter()?
        .map(|item| item?.extract::<String>())
        .collect::<PyResult<Vec<_>>>()?;
    let actor_refs: Vec<&str> = actors.iter().map(String::as_str).collect();
    let verdict = check_actor(actor.as_deref(), &actor_refs);
    if verdict != Verdict::Accepted {
        return Ok((verdict.code(), py.None()));
    }
    let actor = actor.as_deref().unwrap_or("");

    let reference = command.getattr("actor_reference")?;
    let present = !reference.is_none();
    let verdict = check_reference_presence(actor, present);
    if verdict != Verdict::Accepted {
        return Ok((verdict.code(), py.None()));
    }
    if present {
        let version_value = reference.getattr("reference_version")?;
        let version: Option<String> = version_value
            .is_instance_of::<PyString>()
            .then(|| version_value.extract())
            .transpose()?;
        let verdict = check_reference_version(version.as_deref());
        if verdict != Verdict::Accepted {
            return Ok((verdict.code(), py.None()));
        }
        let principal: String = reference.getattr("principal_id")?.extract()?;
        let verdict = check_reference_principal(&principal);
        if verdict != Verdict::Accepted {
            return Ok((verdict.code(), py.None()));
        }
    }

    let requires_approval = transition.getattr("requires_approval")?.is_truthy()?;
    let approval = if approval_fact_required(actor, requires_approval) {
        command.getattr("approval")?.is_truthy()?
    } else {
        false
    };
    let verdict = check_approval(actor, requires_approval, approval);
    if verdict != Verdict::Accepted {
        return Ok((verdict.code(), py.None()));
    }

    let outcomes = transition
        .getattr("outcomes")?
        .try_iter()?
        .map(|item| item?.extract::<String>())
        .collect::<PyResult<Vec<_>>>()?;
    let outcome_value = command.getattr("outcome")?;
    let outcome_text: Option<String> = outcome_value
        .is_instance_of::<PyString>()
        .then(|| outcome_value.extract())
        .transpose()?;
    let outcome_refs: Vec<&str> = outcomes.iter().map(String::as_str).collect();
    let fact = if outcome_value.is_none() {
        OutcomeFact::Missing
    } else if let Some(value) = outcome_text.as_deref() {
        OutcomeFact::Text(value)
    } else {
        OutcomeFact::Other {
            truthy: outcomes.is_empty() && outcome_value.is_truthy()?,
        }
    };
    let result = select_outcome(fact, &outcome_refs);
    let selected = if result.preserve_raw_outcome {
        outcome_value.unbind()
    } else if let Some(value) = result.selected_outcome {
        PyString::new(py, value).into_any().unbind()
    } else {
        py.None()
    };
    Ok((result.verdict.code(), selected))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn evaluate_authorization(
    principal_status: &str,
    principal_id: &str,
    action: &str,
    resource_type: &str,
    resource_id: &str,
    resource: Option<ResourceTuple>,
    grant: Option<GrantTuple>,
) -> (bool, &'static str, Option<String>, Option<&'static str>) {
    let resource = resource
        .as_ref()
        .map(|(resource_type, resource_id, status)| ResourceFact {
            resource_type,
            resource_id,
            status,
        });
    let grant = grant.as_ref().map(
        |(grant_id, principal_id, action, resource_type, resource_id, effect, status)| GrantFact {
            grant_id,
            principal_id,
            action,
            resource_type,
            resource_id,
            effect,
            status,
        },
    );
    let decision = decide(&AuthorizationRequest {
        principal_status,
        principal_id,
        action,
        resource_type,
        resource_id,
        resource,
        grant,
    });
    (
        decision.allowed,
        decision.reason_code,
        decision.policy_id.map(str::to_owned),
        decision.denial_cause,
    )
}

#[pyfunction]
fn map_provider_failure(kind: &Bound<'_, PyAny>) -> (u16, &'static str, &'static str) {
    let kind = kind
        .is_instance_of::<PyString>()
        .then(|| kind.extract::<String>().ok())
        .flatten();
    let mapping = classify_provider_failure(kind.as_deref().unwrap_or(""));
    (mapping.status, mapping.audit_reason, mapping.public_code)
}

fn mapping_field<'py>(value: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    value.call_method1("get", (key,))
}

fn string_fact(value: &Bound<'_, PyAny>) -> Option<String> {
    value
        .is_instance_of::<PyString>()
        .then(|| value.extract::<String>().ok())
        .flatten()
}

/// Select Python Unicode objects by a Rust-owned index plan. Never round-trip text
/// through Rust UTF-8: Python strings may contain lone surrogates.
#[pyfunction]
fn completed_openrouter_output_text(body: &Bound<'_, PyAny>) -> PyResult<Option<Py<PyAny>>> {
    let py = body.py();
    let mapping = py.import("collections.abc")?.getattr("Mapping")?;
    let status = mapping_field(body, "status")?;
    let status = string_fact(&status);
    if !status_completed(status.as_deref()) {
        return Ok(None);
    }
    let output = mapping_field(body, "output")?;
    let output_list = output.cast::<PyList>().ok();
    if !root_accepts(status.as_deref(), output_list.is_some()) {
        return Ok(None);
    }
    let output = output_list.expect("Rust accepted only list output");

    let mut facts = Vec::with_capacity(output.len());
    let mut text_slots: Vec<Vec<Option<Py<PyAny>>>> = Vec::with_capacity(output.len());
    for item in output.iter() {
        let mut fact = MessageFact {
            kind: None,
            role: None,
            status: None,
            contents: None,
        };
        let mut slots = Vec::new();
        if item.is_instance(&mapping)? {
            fact.kind = string_fact(&mapping_field(&item, "type")?);
            if message_kind_relevant(fact.kind.as_deref()) {
                fact.role = string_fact(&mapping_field(&item, "role")?);
                if message_role_relevant(fact.role.as_deref()) {
                    fact.status = string_fact(&mapping_field(&item, "status")?);
                    if status_completed(fact.status.as_deref()) {
                        let content = mapping_field(&item, "content")?;
                        if let Ok(content) = content.cast::<PyList>() {
                            let mut parts = Vec::with_capacity(content.len());
                            for part in content.iter() {
                                let mut part_fact = ContentFact {
                                    kind: None,
                                    is_text: false,
                                };
                                let mut text_slot = None;
                                if part.is_instance(&mapping)? {
                                    part_fact.kind = string_fact(&mapping_field(&part, "type")?);
                                    if content_kind_relevant(part_fact.kind.as_deref()) {
                                        let value = mapping_field(&part, "text")?;
                                        part_fact.is_text = value.is_instance_of::<PyString>();
                                        if part_fact.is_text {
                                            text_slot = Some(value.unbind());
                                        }
                                    }
                                }
                                parts.push(part_fact);
                                slots.push(text_slot);
                            }
                            fact.contents = Some(parts);
                        }
                    }
                }
            }
        }
        facts.push(fact);
        text_slots.push(slots);
    }

    let Some(plan) = select_text(status.as_deref(), Some(&facts)) else {
        return Ok(None);
    };
    let selected: Vec<Bound<'_, PyAny>> = plan
        .indices
        .into_iter()
        .map(|(message, content)| {
            text_slots[message][content]
                .as_ref()
                .expect("Rust selected only Python text")
                .bind(py)
                .clone()
        })
        .collect();
    let parts = PyTuple::new(py, selected)?;
    let joined = PyString::new(py, plan.separator).call_method1("join", (parts,))?;
    Ok(Some(joined.unbind()))
}

type UsageValue = (Option<String>, bool, bool);
type UsageProjection = (
    &'static str,
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
    bool,
);

fn usage_evidence(value: &UsageValue) -> Evidence<'_> {
    Evidence {
        value: value.0.as_deref(),
        invalid: value.1,
        present: value.2,
    }
}

#[pyfunction]
#[pyo3(signature = (state, nonempty, input, output, total, cost, timestamp_valid, failure_context=false))]
#[allow(clippy::too_many_arguments)]
fn project_openrouter_consumption(
    state: &str,
    nonempty: bool,
    input: UsageValue,
    output: UsageValue,
    total: UsageValue,
    cost: UsageValue,
    timestamp_valid: bool,
    failure_context: bool,
) -> PyResult<UsageProjection> {
    let state = match state {
        "missing" => UsageState::Missing,
        "invalid" => UsageState::Invalid,
        "mapping" => UsageState::Mapping,
        _ => return Err(PyValueError::new_err("unknown usage state")),
    };
    let projection = project_usage(&UsageFacts {
        state,
        nonempty,
        input: usage_evidence(&input),
        output: usage_evidence(&output),
        total: usage_evidence(&total),
        cost: usage_evidence(&cost),
        timestamp_valid,
        failure_context,
    });
    Ok((
        projection.availability,
        projection.input.map(str::to_owned),
        projection.output.map(str::to_owned),
        projection.total.map(str::to_owned),
        projection.cost.map(str::to_owned),
        projection.billing_context,
    ))
}

fn item<'py>(mapping: &Bound<'py, PyDict>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    mapping.get_item(key)
}

fn scalar(value: Option<&Bound<'_, PyAny>>) -> PyResult<Scalar> {
    let Some(value) = value else {
        return Ok(Scalar::Null);
    };
    if value.is_none() {
        return Ok(Scalar::Null);
    }
    if value.is_instance_of::<PyBool>() {
        return Ok(Scalar::Bool(value.is_truthy()?));
    }
    if value.is_instance_of::<PyString>() {
        return Ok(Scalar::Text(value.extract()?));
    }
    let decimal_type = value.get_type().name()? == "Decimal"
        && value
            .get_type()
            .getattr("__module__")?
            .extract::<String>()?
            == "decimal";
    if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() || decimal_type {
        return Ok(Scalar::Number(Number(value.str()?.to_str()?.to_owned())));
    }
    Ok(Scalar::Other)
}

fn scalar_item(mapping: &Bound<'_, PyDict>, key: &str) -> PyResult<Scalar> {
    scalar(item(mapping, key)?.as_ref())
}

fn text(value: Option<&Bound<'_, PyAny>>) -> PyResult<Option<String>> {
    value
        .filter(|value| value.is_instance_of::<PyString>())
        .map(|value| value.extract())
        .transpose()
}

fn folded(value: Option<&Bound<'_, PyAny>>) -> PyResult<Option<String>> {
    value
        .filter(|value| value.is_instance_of::<PyString>())
        .map(|value| value.call_method0("casefold")?.extract())
        .transpose()
}

fn folded_request(py: Python<'_>, value: &str) -> PyResult<String> {
    PyString::new(py, value).call_method0("casefold")?.extract()
}

fn endpoint(value: &Bound<'_, PyAny>) -> PyResult<Endpoint> {
    let Ok(mapping) = value.cast::<PyDict>() else {
        return Ok(Endpoint {
            selected_is_true: false,
            provider_folded: None,
            model: Scalar::Null,
        });
    };
    let selected = item(mapping, "selected")?;
    Ok(Endpoint {
        selected_is_true: selected.as_ref().is_some_and(|value| {
            value.is_instance_of::<PyBool>() && value.is_truthy().unwrap_or(false)
        }),
        provider_folded: None,
        model: scalar_item(mapping, "model")?,
    })
}

fn attempt(value: &Bound<'_, PyAny>) -> PyResult<Attempt> {
    let Ok(mapping) = value.cast::<PyDict>() else {
        return Ok(Attempt {
            provider_folded: None,
            model: Scalar::Null,
            status: Scalar::Null,
        });
    };
    Ok(Attempt {
        provider_folded: None,
        model: scalar_item(mapping, "model")?,
        status: scalar_item(mapping, "status")?,
    })
}

fn metadata(value: Option<&Bound<'_, PyAny>>) -> PyResult<Option<Metadata>> {
    let Some(mapping) = value.and_then(|value| value.cast::<PyDict>().ok()) else {
        return Ok(None);
    };
    let endpoints = item(mapping, "endpoints")?;
    let available = endpoints
        .as_ref()
        .and_then(|value| value.cast::<PyDict>().ok())
        .map(|mapping| item(mapping, "available"))
        .transpose()?
        .flatten();
    let available = available
        .as_ref()
        .and_then(|value| value.cast::<PyList>().ok())
        .map(|items| {
            items
                .iter()
                .map(|value| endpoint(&value))
                .collect::<PyResult<Vec<_>>>()
        })
        .transpose()?;
    let attempts = item(mapping, "attempts")?;
    let attempts = if attempts.as_ref().is_none_or(Bound::is_none) {
        None
    } else if let Some(items) = attempts
        .as_ref()
        .and_then(|value| value.cast::<PyList>().ok())
    {
        Some(
            items
                .iter()
                .map(|value| attempt(&value))
                .collect::<PyResult<Vec<_>>>()?,
        )
    } else {
        Some(Vec::new())
    };
    Ok(Some(Metadata {
        requested: scalar_item(mapping, "requested")?,
        strategy: scalar_item(mapping, "strategy")?,
        attempt: scalar_item(mapping, "attempt")?,
        available,
        attempts,
    }))
}

fn response_facts(body: &Bound<'_, PyAny>) -> PyResult<ResponseFacts> {
    let Ok(mapping) = body.cast::<PyDict>() else {
        return Ok(ResponseFacts {
            generation_id: None,
            model: Scalar::Null,
            error_is_none: true,
            incomplete_is_none: true,
            metadata: None,
        });
    };
    Ok(ResponseFacts {
        generation_id: text(item(mapping, "id")?.as_ref())?,
        model: scalar_item(mapping, "model")?,
        error_is_none: item(mapping, "error")?.as_ref().is_none_or(Bound::is_none),
        incomplete_is_none: item(mapping, "incomplete_details")?
            .as_ref()
            .is_none_or(Bound::is_none),
        metadata: None,
    })
}

#[pyfunction]
fn inspect_provider_response(
    py: Python<'_>,
    body: &Bound<'_, PyAny>,
    request_model: &str,
    request_provider: &str,
) -> PyResult<(&'static str, Option<String>)> {
    let mut facts = response_facts(body)?;
    let mut provider = String::new();
    if response_body_valid(&facts, request_model) {
        let mapping = body.cast::<PyDict>()?;
        let metadata_value = item(mapping, "openrouter_metadata")?;
        facts.metadata = metadata(metadata_value.as_ref())?;
        if let Some(plan) = response_fold_plan(&facts, request_model) {
            let metadata_mapping = metadata_value
                .as_ref()
                .expect("fold plan requires metadata")
                .cast::<PyDict>()?;
            let endpoints_value =
                item(metadata_mapping, "endpoints")?.expect("fold plan requires endpoints");
            let endpoints = endpoints_value.cast::<PyDict>()?;
            let available_value =
                item(endpoints, "available")?.expect("fold plan requires available");
            let available = available_value.cast::<PyList>()?;
            let selected_value = available.get_item(plan.selected_index)?;
            let selected = selected_value.cast::<PyDict>()?;
            let selected_provider = folded(item(selected, "provider")?.as_ref())?;
            let metadata_facts = facts
                .metadata
                .as_mut()
                .expect("fold plan requires metadata");
            metadata_facts
                .available
                .as_mut()
                .expect("fold plan requires list")[plan.selected_index]
                .provider_folded = selected_provider;
            if let Some(index) = plan.attempt_index {
                let attempts_value =
                    item(metadata_mapping, "attempts")?.expect("fold plan requires attempts");
                let attempts = attempts_value.cast::<PyList>()?;
                let attempt = attempts.get_item(index)?;
                let attempt_provider = attempt
                    .cast::<PyDict>()
                    .ok()
                    .map(|mapping| item(mapping, "provider"))
                    .transpose()?
                    .flatten();
                metadata_facts
                    .attempts
                    .as_mut()
                    .expect("fold plan requires attempts")[index]
                    .provider_folded = folded(attempt_provider.as_ref())?;
            }
            provider = folded_request(py, request_provider)?;
        }
    }
    Ok(match inspect_response(&facts, request_model, &provider) {
        RoutingStage::Accept => ("accept", None),
        RoutingStage::Reject(kind) => ("reject", Some(kind.into())),
        RoutingStage::CatalogRequired(model) => ("catalog_required", Some(model)),
    })
}

fn catalog_endpoint(value: &Bound<'_, PyAny>, request_model: &str) -> PyResult<CatalogEndpoint> {
    let Ok(mapping) = value.cast::<PyDict>() else {
        return Ok(CatalogEndpoint {
            model_id: Scalar::Null,
            provider_name: None,
            provider_folded: None,
            tag: None,
            name: Scalar::Null,
        });
    };
    let model_id = scalar_item(mapping, "model_id")?;
    if !catalog_model_id_valid(&model_id, request_model) {
        return Ok(CatalogEndpoint {
            model_id,
            provider_name: None,
            provider_folded: None,
            tag: None,
            name: Scalar::Null,
        });
    }
    let provider = item(mapping, "provider_name")?;
    Ok(CatalogEndpoint {
        model_id,
        provider_name: text(provider.as_ref())?,
        provider_folded: None,
        tag: text(item(mapping, "tag")?.as_ref())?,
        name: scalar_item(mapping, "name")?,
    })
}

fn catalog_facts(body: &Bound<'_, PyAny>, request_model: &str) -> PyResult<CatalogFacts> {
    let data = body
        .cast::<PyDict>()
        .ok()
        .map(|mapping| item(mapping, "data"))
        .transpose()?
        .flatten();
    let Some(data) = data.as_ref().and_then(|value| value.cast::<PyDict>().ok()) else {
        return Ok(CatalogFacts {
            id: Scalar::Null,
            endpoints: None,
        });
    };
    let id = scalar_item(data, "id")?;
    if !catalog_id_valid(&id, request_model) {
        return Ok(CatalogFacts {
            id,
            endpoints: None,
        });
    }
    let endpoints = item(data, "endpoints")?;
    let endpoints = endpoints
        .as_ref()
        .and_then(|value| value.cast::<PyList>().ok())
        .map(|items| {
            items
                .iter()
                .map(|value| catalog_endpoint(&value, request_model))
                .collect::<PyResult<Vec<_>>>()
        })
        .transpose()?;
    Ok(CatalogFacts { id, endpoints })
}

#[pyfunction]
fn confirm_provider_catalog(
    py: Python<'_>,
    body: &Bound<'_, PyAny>,
    selected_model: &str,
    request_model: &str,
    request_provider: &str,
) -> PyResult<bool> {
    let mut facts = catalog_facts(body, request_model)?;
    let indices = catalog_fold_indices(&facts, request_model);
    let mut provider = String::new();
    if !indices.is_empty() {
        let data_value =
            item(body.cast::<PyDict>()?, "data")?.expect("catalog candidates require data");
        let data = data_value.cast::<PyDict>()?;
        let endpoints_value =
            item(data, "endpoints")?.expect("catalog candidates require endpoints");
        let endpoints = endpoints_value.cast::<PyList>()?;
        for index in indices {
            let endpoint_value = endpoints.get_item(index)?;
            let endpoint = endpoint_value.cast::<PyDict>()?;
            facts
                .endpoints
                .as_mut()
                .expect("catalog candidates require list")[index]
                .provider_folded = folded(item(endpoint, "provider_name")?.as_ref())?;
        }
        provider = folded_request(py, request_provider)?;
    }
    Ok(confirm_catalog(
        &facts,
        selected_model,
        request_model,
        request_provider,
        &provider,
    ))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn project_responses_audit<'py>(
    py: Python<'py>,
    status: i64,
    reason: Option<&str>,
    context: Option<(String, String, String, String)>,
    alias: Option<&str>,
    decision: Option<(String, String, Option<String>)>,
    assignment: Option<(String, String)>,
    identifiers: Vec<(String, String)>,
) -> PyResult<Bound<'py, PyDict>> {
    let identifiers: Vec<_> = identifiers
        .iter()
        .map(|(name, value)| (name.as_str(), value.as_str()))
        .collect();
    let projection = project_audit(&AuditRequest {
        status,
        reason,
        context: context
            .as_ref()
            .map(|(id, kind, state, credential)| ContextFact {
                principal_id: id,
                principal_kind: kind,
                principal_status: state,
                credential_id: credential,
            }),
        alias,
        decision: decision
            .as_ref()
            .map(|(decision, reason_code, policy_id)| DecisionFact {
                decision,
                reason_code,
                policy_id: policy_id.as_deref(),
            }),
        assignment: assignment.as_ref().map(|(model, provider)| AssignmentFact {
            concrete_model: model,
            inference_provider: provider,
        }),
        identifiers: &identifiers,
    });
    let result = PyDict::new(py);
    result.set_item("operation", projection.operation)?;
    result.set_item("action", projection.action)?;
    result.set_item("outcome", projection.outcome)?;
    result.set_item("correlation_refs", &projection.correlation_refs)?;

    if let Some(identity) = projection.identity {
        let item = PyDict::new(py);
        item.set_item("principal_ref", identity.principal_ref)?;
        item.set_item("principal_kind", identity.principal_kind)?;
        item.set_item("principal_status", identity.principal_status)?;
        item.set_item("credential_ref", identity.credential_ref)?;
        result.set_item("identity", item)?;
    } else {
        result.set_item("identity", py.None())?;
    }
    if let Some(resource) = projection.resource {
        let item = PyDict::new(py);
        item.set_item("resource_type", resource.resource_type)?;
        item.set_item("resource_ref", resource.resource_ref)?;
        result.set_item("resource", item)?;
    } else {
        result.set_item("resource", py.None())?;
    }
    result.set_item("model_alias_ref", projection.model_alias_ref)?;
    if let Some(decision) = projection.policy_decision {
        let item = PyDict::new(py);
        item.set_item("decision", decision.decision)?;
        item.set_item("reason_code", decision.reason_code)?;
        if let Some(grant_ref) = decision.grant_ref {
            item.set_item("grant_ref", grant_ref)?;
        }
        result.set_item("policy_decision", item)?;
    } else {
        result.set_item("policy_decision", py.None())?;
    }
    if let Some(routing) = projection.routing {
        let item = PyDict::new(py);
        item.set_item("model_ref", routing.model_ref)?;
        item.set_item("router", routing.router)?;
        item.set_item("provider_ref", routing.provider_ref)?;
        result.set_item("routing", item)?;
    } else {
        result.set_item("routing", py.None())?;
    }
    let redaction = PyDict::new(py);
    redaction.set_item("policy_version", projection.redaction.policy_version)?;
    redaction.set_item("result", projection.redaction.result)?;
    redaction.set_item("source_class", projection.redaction.source_class)?;
    redaction.set_item("categories", projection.redaction.categories.to_vec())?;
    redaction.set_item("match_count", projection.redaction.match_count)?;
    redaction.set_item("sink_eligible", projection.redaction.sink_eligible)?;
    result.set_item("redaction", redaction)?;
    result.set_item("content_state", projection.content_state)?;
    result.set_item(
        "authoritative_acceptance",
        projection.authoritative_acceptance,
    )?;
    result.set_item("ordinary_result", projection.ordinary_result)?;
    result.set_item("exporter_result", projection.exporter_result)?;
    Ok(result)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn project_control_audit<'py>(
    py: Python<'py>,
    status: i64,
    stage: &str,
    reason: Option<&str>,
    terminal: bool,
    retryable: bool,
    context: Option<&Bound<'py, PyAny>>,
    resource: Option<&Bound<'py, PyAny>>,
    decision: Option<&Bound<'py, PyAny>>,
    authorization_denial_cause: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let retain_subject = retain_control_subject(terminal, stage);
    let context: Option<(String, String, String, String)> = if retain_subject {
        context
            .map(|value| {
                if value.is_instance_of::<PyTuple>() {
                    value.extract()
                } else {
                    let principal = value.getattr("principal")?;
                    Ok((
                        principal.getattr("principal_id")?.extract()?,
                        principal.getattr("kind")?.extract()?,
                        principal.getattr("status")?.extract()?,
                        value.getattr("credential_id")?.extract()?,
                    ))
                }
            })
            .transpose()?
    } else {
        None
    };
    let resource: Option<(String, String)> = if retain_subject {
        resource.map(|value| value.extract()).transpose()?
    } else {
        None
    };
    let decision: Option<(String, Option<String>)> = if retain_subject {
        decision
            .map(|value| {
                if value.is_instance_of::<PyTuple>() {
                    value.extract()
                } else {
                    let decision = value.getattr("decision")?.extract()?;
                    let _ = value.getattr("reason_code")?;
                    Ok((decision, value.getattr("policy_id")?.extract()?))
                }
            })
            .transpose()?
    } else {
        None
    };
    let authorization_denial_cause: Option<String> = if retain_subject {
        authorization_denial_cause
            .map(|value| value.extract())
            .transpose()?
    } else {
        None
    };
    let projection = project_control(&ControlAuditRequest {
        status,
        stage,
        reason,
        terminal,
        retryable,
        context: context.as_ref().map(|(id, kind, state, credential)| {
            (
                id.as_str(),
                kind.as_str(),
                state.as_str(),
                credential.as_str(),
            )
        }),
        resource: resource
            .as_ref()
            .map(|(resource_type, id)| (resource_type.as_str(), id.as_str())),
        decision: decision
            .as_ref()
            .map(|(decision, policy_id)| ControlDecisionFact {
                decision,
                policy_id: policy_id.as_deref(),
            }),
        authorization_denial_cause: authorization_denial_cause.as_deref(),
    })
    .map_err(PyValueError::new_err)?;
    let result = PyDict::new(py);
    result.set_item("stage", projection.stage)?;
    result.set_item("outcome", projection.outcome)?;
    result.set_item("reason", projection.reason)?;
    result.set_item("retryable", projection.retryable)?;
    result.set_item(
        "authorization_denial_cause",
        projection.authorization_denial_cause,
    )?;
    if let Some(identity) = projection.identity {
        let item = PyDict::new(py);
        item.set_item("principal_ref", identity.principal_ref)?;
        item.set_item("principal_kind", identity.principal_kind)?;
        item.set_item("principal_status", identity.principal_status)?;
        item.set_item("credential_ref", identity.credential_ref)?;
        result.set_item("identity", item)?;
    } else {
        result.set_item("identity", py.None())?;
    }
    if let Some(resource) = projection.resource {
        let item = PyDict::new(py);
        item.set_item("resource_type", resource.resource_type)?;
        item.set_item("resource_ref", resource.resource_ref)?;
        result.set_item("resource", item)?;
    } else {
        result.set_item("resource", py.None())?;
    }
    if let Some(decision) = projection.policy_decision {
        let item = PyDict::new(py);
        item.set_item("decision", decision.decision)?;
        item.set_item("reason_code", decision.reason_code)?;
        if let Some(grant_ref) = decision.grant_ref {
            item.set_item("grant_ref", grant_ref)?;
        }
        result.set_item("policy_decision", item)?;
    } else {
        result.set_item("policy_decision", py.None())?;
    }
    result.set_item("routing", py.None())?;
    Ok(result)
}

#[pymodule]
fn _core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("API_VERSION", 1)?;
    module.add_function(wrap_pyfunction!(audit_reference_digest, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_authorization, module)?)?;
    module.add_function(wrap_pyfunction!(admit_incident_transition, module)?)?;
    module.add_function(wrap_pyfunction!(map_provider_failure, module)?)?;
    module.add_function(wrap_pyfunction!(completed_openrouter_output_text, module)?)?;
    module.add_function(wrap_pyfunction!(project_openrouter_consumption, module)?)?;
    module.add_function(wrap_pyfunction!(inspect_provider_response, module)?)?;
    module.add_function(wrap_pyfunction!(confirm_provider_catalog, module)?)?;
    module.add_function(wrap_pyfunction!(project_responses_audit, module)?)?;
    module.add_function(wrap_pyfunction!(project_control_audit, module)?)?;
    Ok(())
}

#[cfg(test)]
mod audit_reference_tests {
    #[test]
    fn digest_uses_adr_005_prefix_utf8_and_domain_separation() {
        let key = b"test-audit-key-not-for-production";
        assert_eq!(
            super::audit_reference::digest(key, b"sre-audit-v1\0principal\0incident-harness"),
            "65b79231fefa9914077a157cdd26de9029de8b40bd235c53658c0732935e9f65"
        );
        assert_eq!(
            super::audit_reference::digest(key, "sre-audit-v1\0principal\0é🦉\0value".as_bytes()),
            "fd4afba9ce8fff0209abd6c1d2c873bf02673d742366f90f6961a5203fe2affa"
        );
        assert_ne!(
            super::audit_reference::digest(key, "sre-audit-v1\0principal\0é🦉\0value".as_bytes()),
            super::audit_reference::digest(key, "sre-audit-v1\0resource\0é🦉\0value".as_bytes())
        );
    }
}
