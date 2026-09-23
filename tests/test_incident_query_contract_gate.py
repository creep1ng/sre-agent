"""Negative gate tests for the incident query contract (issue #189).

The validator inspects published artifacts as-is: a broken reference must
fail the gate instead of crashing it or being repaired in memory.
"""

import copy
import sys
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import validate_incident_queries as gate  # noqa: E402

BOGUS_URN = "urn:sre-agent:schema:does-not-exist:9.9.9"


def _schemas():
    schemas, errors = gate.check_schemas()
    assert not errors
    return schemas


def test_broken_urn_reference_fails_examples_gate() -> None:
    schemas = _schemas()
    broken = copy.deepcopy(schemas["incident-snapshot"])
    broken["properties"]["incident"]["$ref"] = BOGUS_URN
    schemas["incident-snapshot"] = broken
    errors = gate.check_examples(schemas)
    assert errors, "gate must report the unresolvable reference"
    assert any("snapshot.json" in error for error in errors)


def test_unknown_openapi_urn_reference_fails_contract_gate(tmp_path, monkeypatch) -> None:
    schemas = _schemas()
    doc = gate.load_yaml(gate.OPENAPI_PATH)
    content = doc["paths"]["/v1/incidents/{incident_id}"]["get"]["responses"]["200"]["content"]
    content["application/json"]["schema"] = {"$ref": BOGUS_URN}
    broken = tmp_path / "incident-queries.openapi.yaml"
    broken.write_text(yaml.dump(doc), encoding="utf-8")
    monkeypatch.setattr(gate, "OPENAPI_PATH", broken)
    errors = gate.check_openapi(schemas)
    assert any("does-not-exist" in error for error in errors)
