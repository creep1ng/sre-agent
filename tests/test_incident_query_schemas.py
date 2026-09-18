"""Schema reference resolution for incident query schemas (issue #189).

Loads the published schemas exactly as a consumer receives them and resolves
references through their published ``$id`` identities. A relative file
reference is not resolvable for consumers: dependencies must be registered
by URN.
"""

from pathlib import Path

import pytest
import yaml

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
