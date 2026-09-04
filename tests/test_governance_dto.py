import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    ModelAlias,
    PolicyDecision,
    Principal,
    Resource,
)

ROOT = Path(__file__).parents[1]
MODELS = {
    "principal": Principal,
    "credential-reference": CredentialReference,
    "resource": Resource,
    "model-alias": ModelAlias,
    "grant": Grant,
    "policy-decision": PolicyDecision,
    "audit-event": AuditEvent,
}


def fixture(version: str, status: str, name: str) -> dict[str, object]:
    path = ROOT / "schemas" / "releases" / version / "fixtures" / status
    return json.loads((path / f"{name}.{status}.v{version}.fixture.json").read_text())


def contract_cases(status: str) -> tuple[Path, ...]:
    paths = (ROOT / "schemas" / "releases").glob(f"1.*.0/fixtures/{status}/*.json")
    return tuple(
        path
        for path in paths
        if (
            (":" + str(json.loads(path.read_text()).get("target", ""))).rsplit(":", 2)[-2] in MODELS
        )
    )


@pytest.mark.parametrize("path", contract_cases("positive"), ids=lambda path: path.name)
def test_positive_ht01_fixtures_round_trip(path: Path) -> None:
    case = json.loads(path.read_text())
    model = MODELS[str(case["target"]).split(":")[-2]]

    dto = model.model_validate_json(json.dumps(case["data"]))

    assert dto.model_dump(mode="json", exclude_unset=True) == case["data"]


@pytest.mark.parametrize(
    "path",
    tuple(
        path
        for path in contract_cases("negative")
        if path.name
        not in {
            "audit.authorization-denial-cause-missing.negative.v1.3.0.fixture.json",
            "audit.authorization-denial-cause-null.negative.v1.3.0.fixture.json",
            "audit.authorization-denial-cause-missing.negative.v1.4.0.fixture.json",
            "audit.authorization-denial-cause-null.negative.v1.4.0.fixture.json",
        }
    ),
    ids=lambda path: path.name,
)
def test_negative_ht01_fixtures_are_rejected(path: Path) -> None:
    case = json.loads(path.read_text())
    model = MODELS[str(case["target"]).split(":")[-2]]

    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(case["data"]))


@pytest.mark.parametrize("model,field", ((Principal, "principal_id"), (ModelAlias, "alias")))
def test_invalid_identifiers_are_rejected(model: type, field: str) -> None:
    data = fixture(
        "1.1.0",
        "positive",
        {Principal: "shared.principal.human", ModelAlias: "shared.model-alias.assignment"}[model],
    )["data"]
    data[field] = "Legacy ID"

    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(data))


def test_audit_latency_is_additive_and_non_negative() -> None:
    data = fixture("1.1.0", "positive", "audit.responses.allowed")["data"]
    data["latency_ms"] = 17

    dto = AuditEvent.model_validate_json(json.dumps(data))

    assert dto.latency_ms == 17
    assert dto.model_dump(mode="json", exclude_unset=True)["latency_ms"] == 17


@pytest.mark.parametrize("latency_ms", (-1, True, 1.5))
def test_invalid_audit_latency_is_rejected(latency_ms: object) -> None:
    data = fixture("1.1.0", "positive", "audit.responses.allowed")["data"]
    data["latency_ms"] = latency_ms

    with pytest.raises(ValidationError):
        AuditEvent.model_validate_json(json.dumps(data))


def test_previous_release_audit_event_without_latency_remains_valid() -> None:
    data = fixture("1.1.0", "positive", "audit.responses.allowed")["data"]

    dto = AuditEvent.model_validate_json(json.dumps(data))

    assert dto.model_dump(mode="json", exclude_unset=True) == data


@pytest.mark.parametrize(
    "cause",
    ("principal_inactive", "resource_missing", "resource_inactive", "grant_not_applicable"),
)
def test_authorization_denial_cause_is_a_closed_audit_only_field(cause: str) -> None:
    data = fixture("1.2.0", "positive", "audit.responses.denied")["data"]
    data["authorization_denial_cause"] = cause

    dto = AuditEvent.model_validate_json(json.dumps(data))

    assert dto.authorization_denial_cause == cause
    assert dto.policy_decision.model_dump() == {
        "decision": "deny",
        "reason_code": "no_matching_grant",
    }


@pytest.mark.parametrize(
    "field,value",
    (
        ("authorization_denial_cause", "grant_exists"),
        ("outcome", "success"),
        ("stage", "routing"),
    ),
)
def test_authorization_denial_cause_requires_an_authorization_deny(field: str, value: str) -> None:
    data = fixture("1.2.0", "positive", "audit.responses.denied")["data"]
    data["authorization_denial_cause"] = "resource_missing"
    data[field] = value

    with pytest.raises(ValidationError):
        AuditEvent.model_validate_json(json.dumps(data))


def test_release_130_denial_fixture_carries_the_internal_audit_cause() -> None:
    data = fixture("1.3.0", "positive", "audit.responses.denied")["data"]

    dto = AuditEvent.model_validate_json(json.dumps(data))

    assert dto.authorization_denial_cause == "grant_not_applicable"


def test_historical_release_120_denial_without_a_cause_remains_readable() -> None:
    data = fixture("1.2.0", "positive", "audit.responses.denied")["data"]

    dto = AuditEvent.model_validate_json(json.dumps(data))

    assert dto.authorization_denial_cause is None
