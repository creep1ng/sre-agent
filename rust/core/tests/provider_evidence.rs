use sre_agent_core::provider_evidence::{
    catalog_fold_indices, catalog_id_valid, catalog_model_id_valid, confirm_catalog,
    inspect_response, response_body_valid, response_fold_plan, Attempt, CatalogEndpoint,
    CatalogFacts, Endpoint, Metadata, Number, ResponseFacts, RoutingStage, Scalar,
};

fn response() -> ResponseFacts {
    ResponseFacts {
        generation_id: Some("gen-12345678".into()),
        model: Scalar::Text("openai/gpt-4o-mini".into()),
        error_is_none: true,
        incomplete_is_none: true,
        metadata: Some(Metadata {
            requested: Scalar::Text("openai/gpt-4o-mini".into()),
            strategy: Scalar::Text("direct".into()),
            attempt: Scalar::Number(Number("1".into())),
            available: Some(vec![Endpoint {
                selected_is_true: true,
                provider_folded: Some("openai".into()),
                model: Scalar::Text("openai/gpt-4o-mini".into()),
            }]),
            attempts: None,
        }),
    }
}

#[test]
fn staged_acceptance_preserves_body_precedence_and_inline_evidence() {
    let mut facts = response();
    assert_eq!(
        inspect_response(&facts, "openai/gpt-4o-mini", "openai"),
        RoutingStage::Accept
    );
    facts.generation_id = Some("resp_12345678".into());
    assert_eq!(
        inspect_response(&facts, "openai/gpt-4o-mini", "openai"),
        RoutingStage::Reject("invalid_response")
    );
    facts = response();
    facts.metadata.as_mut().unwrap().available.as_mut().unwrap()[0].selected_is_true = false;
    assert_eq!(
        inspect_response(&facts, "openai/gpt-4o-mini", "openai"),
        RoutingStage::Reject("evidence_invalid")
    );
}

#[test]
fn python_numeric_equality_accepts_bool_and_decimal_one_but_not_bool_200() {
    for attempt in [Scalar::Bool(true), Scalar::Number(Number("1.0".into()))] {
        let mut facts = response();
        facts.metadata.as_mut().unwrap().attempt = attempt;
        assert_eq!(
            inspect_response(&facts, "openai/gpt-4o-mini", "openai"),
            RoutingStage::Accept
        );
    }
    let mut facts = response();
    facts.metadata.as_mut().unwrap().attempts = Some(vec![Attempt {
        provider_folded: Some("openai".into()),
        model: Scalar::Text("openai/gpt-4o-mini".into()),
        status: Scalar::Bool(true),
    }]);
    assert_eq!(
        inspect_response(&facts, "openai/gpt-4o-mini", "openai"),
        RoutingStage::Reject("evidence_invalid")
    );
}

#[test]
fn catalog_requires_one_exact_case_sensitive_identity() {
    let candidate = CatalogEndpoint {
        model_id: Scalar::Text("alias".into()),
        provider_name: Some("Straße".into()),
        provider_folded: Some("strasse".into()),
        tag: Some("strasse/fp4".into()),
        name: Scalar::Text("Straße | canonical".into()),
    };
    let mut facts = CatalogFacts {
        id: Scalar::Text("alias".into()),
        endpoints: Some(vec![candidate.clone()]),
    };
    assert!(confirm_catalog(
        &facts,
        "canonical",
        "alias",
        "strasse",
        "strasse"
    ));
    facts.endpoints.as_mut().unwrap()[0].tag = Some("Strasse/fp4".into());
    assert!(!confirm_catalog(
        &facts,
        "canonical",
        "alias",
        "strasse",
        "strasse"
    ));
    facts.endpoints = Some(vec![candidate.clone(), candidate]);
    assert!(!confirm_catalog(
        &facts,
        "canonical",
        "alias",
        "strasse",
        "strasse"
    ));
}

#[test]
fn body_and_inline_relevance_are_decided_before_provider_normalization() {
    let mut facts = response();
    assert!(response_body_valid(&facts, "openai/gpt-4o-mini"));
    assert_eq!(
        response_fold_plan(&facts, "openai/gpt-4o-mini")
            .unwrap()
            .selected_index,
        0
    );
    facts.generation_id = Some("invalid".into());
    assert!(!response_body_valid(&facts, "openai/gpt-4o-mini"));
    assert!(response_fold_plan(&facts, "openai/gpt-4o-mini").is_none());
    facts = response();
    facts
        .metadata
        .as_mut()
        .unwrap()
        .available
        .as_mut()
        .unwrap()
        .insert(
            0,
            Endpoint {
                selected_is_true: false,
                provider_folded: None,
                model: Scalar::Text("other".into()),
            },
        );
    assert_eq!(
        response_fold_plan(&facts, "openai/gpt-4o-mini")
            .unwrap()
            .selected_index,
        1
    );
}

#[test]
fn catalog_relevance_excludes_invalid_ids_and_nonmatching_models() {
    let facts = CatalogFacts {
        id: Scalar::Text("wrong".into()),
        endpoints: Some(vec![CatalogEndpoint {
            model_id: Scalar::Text("alias".into()),
            provider_name: Some("Provider".into()),
            provider_folded: None,
            tag: Some("provider".into()),
            name: Scalar::Text("Provider | canonical".into()),
        }]),
    };
    assert!(!catalog_id_valid(&facts.id, "alias"));
    assert!(catalog_fold_indices(&facts, "alias").is_empty());
    assert!(!catalog_model_id_valid(
        &Scalar::Text("other".into()),
        "alias"
    ));
    let mut facts = facts;
    facts.id = Scalar::Text("alias".into());
    assert_eq!(catalog_fold_indices(&facts, "alias"), vec![0]);
}
