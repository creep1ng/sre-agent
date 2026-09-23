"""Local JSON Pointer gate tests for the incident query contract (issue #189).

Every local `#/...` reference in the published OpenAPI document must resolve
against the original document (RFC 6901, with `~0`/`~1` escapes). A missing
target fails the gate; valid pointers keep passing.
"""

import sys
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import validate_incident_queries as gate  # noqa: E402

BOGUS_POINTER = "#/components/parameters/DOES_NOT_EXIST"


def _schemas():
    schemas, errors = gate.check_schemas()
    assert not errors
    return schemas


def test_missing_local_pointer_fails_contract_gate(tmp_path, monkeypatch) -> None:
    doc = gate.load_yaml(gate.OPENAPI_PATH)
    doc["paths"]["/v1/incidents/{incident_id}"]["get"]["parameters"] = [{"$ref": BOGUS_POINTER}]
    broken = tmp_path / "incident-queries.openapi.yaml"
    broken.write_text(yaml.dump(doc), encoding="utf-8")
    monkeypatch.setattr(gate, "OPENAPI_PATH", broken)
    errors = gate.check_openapi(_schemas())
    assert any("DOES_NOT_EXIST" in error for error in errors)


def test_valid_local_pointers_resolve() -> None:
    doc = gate.load_yaml(gate.OPENAPI_PATH)
    refs = [ref for ref in gate._iter_refs(doc) if ref.startswith("#")]
    assert refs, "published contract must contain local references to check"
    for ref in refs:
        assert gate._resolve_pointer(doc, ref[1:]), f"published ref broke: {ref}"
    assert gate._resolve_pointer(doc, "") is True
    assert gate._resolve_pointer(doc, "/components/parameters/IncidentId") is True
    assert gate._resolve_pointer(doc, "/components/parameters/NOPE") is False
