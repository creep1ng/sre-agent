import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    ModelAlias,
    PolicyDecision,
    Principal,
    Resource,
)
from sre_agent.persistence import projections

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
