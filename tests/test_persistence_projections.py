import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from sre_agent.governance.dto import (
    AuditEvent,
    Consumption,
    CredentialReference,
    Grant,
    ModelAlias,
    PolicyDecision,
    PricingContext,
    Principal,
    Resource,
)
from sre_agent.persistence import projections
from sre_agent.persistence.models import AuditEventRow

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
PROJECTORS = {
    Principal: projections.project_principal,
    CredentialReference: projections.project_credential,
    Resource: projections.project_resource,
    ModelAlias: projections.project_model_alias,
    Grant: projections.project_grant,
    PolicyDecision: projections.project_policy_decision,
    AuditEvent: projections.project_audit_event,
}


def contract_cases() -> tuple[Path, ...]:
    paths = (ROOT / "schemas" / "releases").glob("1.*.0/fixtures/positive/*.json")
    return tuple(
        path
        for path in paths
        if (
            (":" + str(json.loads(path.read_text()).get("target", ""))).rsplit(":", 2)[-2] in MODELS
        )
    )


@pytest.mark.parametrize("path", contract_cases(), ids=lambda path: path.name)
def test_row_projections_copy_only_contract_fields(path: Path) -> None:
    case = json.loads(path.read_text())
    model = MODELS[str(case["target"]).split(":")[-2]]
    dto = model.model_validate_json(json.dumps(case["data"]))
    row = SimpleNamespace(**dto.model_dump(), raw_key="secret", key_hash="hash", provider="leak")

    projected = PROJECTORS[model](row)

    assert projected == dto
    assert not {"raw_key", "key_hash", "provider"} & projected.model_fields_set


def test_audit_projection_preserves_zero_latency() -> None:
    data = json.loads(
        (
            ROOT / "schemas/releases/1.2.0/fixtures/positive/"
            "audit.responses.allowed.positive.v1.2.0.fixture.json"
        ).read_text()
    )["data"]
    data["latency_ms"] = 0

    projected = projections.project_audit_event(data)

    assert projected.latency_ms == 0


def test_audit_projection_preserves_the_authorization_denial_cause() -> None:
    data = json.loads(
        (
            ROOT / "schemas/releases/1.2.0/fixtures/positive/"
            "audit.responses.denied.positive.v1.2.0.fixture.json"
        ).read_text()
    )["data"]
    data["authorization_denial_cause"] = "resource_inactive"

    projected = projections.project_audit_event(data)

    assert projected.authorization_denial_cause == "resource_inactive"
    assert projected.policy_decision.reason_code == "no_matching_grant"


def complete_consumption() -> Consumption:
    return Consumption(
        availability="complete",
        source="openrouter",
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
        billed_usd="0.0012300",
        currency="USD",
        precision="exact",
        pricing_context=PricingContext(
            observed_at=datetime(2026, 9, 10, 14, tzinfo=UTC),
            price_version="openrouter:2026-09-10T14:00:00Z",
        ),
    )


def test_audit_projection_round_trips_consumption_without_provider_content() -> None:
    data = json.loads(
        (
            ROOT / "schemas/releases/1.2.0/fixtures/positive/"
            "audit.responses.allowed.positive.v1.2.0.fixture.json"
        ).read_text()
    )["data"]
    consumption = complete_consumption()
    data["consumption"] = consumption.model_dump(mode="json")
    data["provider_body"] = {"secret": "provider-body-must-not-project"}

    projected = projections.project_audit_event(data)

    assert projected.consumption == consumption
    assert projected.model_dump(mode="json")["consumption"] == consumption.model_dump(mode="json")
    assert "provider_body" not in projected.model_fields_set


def test_audit_row_accepts_nullable_consumption_jsonb() -> None:
    consumption = complete_consumption().model_dump(mode="json")
    row = AuditEventRow(consumption=consumption)

    assert row.consumption == consumption
