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


@pytest.mark.parametrize("path", contract_cases("negative"), ids=lambda path: path.name)
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
