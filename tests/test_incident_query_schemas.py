"""Schema reference resolution for incident query schemas (issue #189).

Loads the published schemas exactly as a consumer receives them and resolves
references through their published ``$id`` identities. A relative file
reference is not resolvable for consumers: dependencies must be registered
by URN.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_incident_queries as gate  # noqa: E402

SCHEMA_DIR = Path("agent/schemas")
SNAPSHOT_ID = "urn:sre-agent:schema:incident-snapshot:1.0.0"
DETAIL_ID = "urn:sre-agent:schema:incident-detail:1.0.0"


def _load(name: str) -> dict:
    with open(SCHEMA_DIR / name, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _registry() -> dict:
    return {
        document["$id"]: document
        for document in (
            _load("incident-detail.schema.yaml"),
            _load("incident-snapshot.schema.yaml"),
        )
    }


def test_snapshot_incident_reference_resolves_by_published_urn() -> None:
    snapshot = _load("incident-snapshot.schema.yaml")
    assert snapshot["$id"] == SNAPSHOT_ID
    reference = snapshot["properties"]["incident"]["$ref"]
    assert reference == DETAIL_ID
    resolved = _registry().get(reference)
    assert resolved is not None
    assert resolved["$id"] == DETAIL_ID
    assert resolved["title"] == "IncidentDetail"


def test_unknown_reference_is_not_silently_resolved() -> None:
    with pytest.raises(KeyError):
        _registry()["urn:sre-agent:schema:does-not-exist:9.9.9"]


def test_run_event_schema_is_validated_fail_closed(tmp_path, monkeypatch) -> None:
    schemas, errors = gate.check_schemas()
    assert not errors
    assert schemas["run-event"]["$id"] == "urn:sre-agent:schema:run-event:1.0.0"
    broken_id = tmp_path / "run-event.schema.yaml"
    broken_id.write_text('{"$id": "bogus", "type": "object"}', encoding="utf-8")
    monkeypatch.setattr(gate, "RUN_EVENT_SCHEMA_PATH", broken_id)
    _, id_errors = gate.check_schemas()
    assert any("run-event" in error for error in id_errors)
    broken_schema = tmp_path / "run-event-broken.schema.yaml"
    broken_schema.write_text('{"type": "not-a-type"}', encoding="utf-8")
    monkeypatch.setattr(gate, "RUN_EVENT_SCHEMA_PATH", broken_schema)
    _, schema_errors = gate.check_schemas()
    assert any("run-event" in error for error in schema_errors)
