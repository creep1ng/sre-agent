"""Acceptance tests for the incident run API contract (HT-INC-04, issue #145).

Each test maps to an acceptance criterion of the issue so a failure names what regressed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_run_api import (  # noqa: E402
    CORRELATION_PATH,
    OPENAPI_PATH,
    REQUIRED_PATHS,
    SCHEMAS,
    build_validator,
    load_yaml,
    validate,
)


@pytest.fixture(scope="module")
def openapi() -> dict:
    return load_yaml(OPENAPI_PATH)


@pytest.fixture(scope="module")
def schemas() -> dict:
    return {name: load_yaml(path) for name, path in SCHEMAS.items()}


def test_every_contract_check_passes() -> None:
    """The full validator, exactly as CI runs it, reports no problems."""
    assert validate() == []


def test_four_run_endpoints_exist(openapi: dict) -> None:
    """Criterion: start/resume, state, commands and events endpoints are defined."""
    assert REQUIRED_PATHS <= set(openapi["paths"])


def test_start_and_command_are_idempotent(openapi: dict) -> None:
    """Criterion: mutating calls require an Idempotency-Key."""
    runs = openapi["paths"]["/v1/incidents/{incident_id}/runs"]["post"]
    commands = openapi["paths"]["/v1/incidents/{incident_id}/runs/{run_id}/commands"]["post"]
    for op in (runs, commands):
        names = [p.get("$ref", "").split("/")[-1] for p in op["parameters"]]
        assert "IdempotencyKey" in names


def test_error_matrix_is_complete(openapi: dict) -> None:
    """Criterion: 401, 403, 404, 409, 422 and a recoverable failure are covered."""
    start = openapi["paths"]["/v1/incidents/{incident_id}/runs"]["post"]["responses"]
    for code in ("401", "403", "404", "409", "422", "503"):
        assert code in start, code


def test_events_endpoint_is_cursor_based(openapi: dict) -> None:
    """ADR-008: events are polled with a cursor, not streamed."""
    events = openapi["paths"]["/v1/incidents/{incident_id}/runs/{run_id}/events"]["get"]
    param_names = [p.get("name") for p in events["parameters"] if "name" in p]
    assert "after" in param_names
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    assert "text/event-stream" not in text


def test_commands_are_human_only(schemas: dict) -> None:
    """Criterion: the harness never commands itself; commands are human."""
    assert schemas["run-command"]["properties"]["actor"]["const"] == "human"
    validator = build_validator(schemas["run-command"])
    identity = {"reference_version": "1.0.0", "principal_id": "demo-human"}
    assert not validator.is_valid(
        {"command": "approve_mitigation", "actor": "agent", "actor_reference": identity}
    )
    assert validator.is_valid(
        {"command": "approve_mitigation", "actor": "human", "actor_reference": identity}
    )


def test_run_state_carries_a_cursor(schemas: dict) -> None:
    """The UI needs a cursor to poll events (ADR-008)."""
    assert "cursor" in schemas["run-state"]["required"]


def test_workflow_version_is_pinned(schemas: dict) -> None:
    """A run is tied to a known workflow version, matching incident-state:1.0.0."""
    assert schemas["run-start-request"]["properties"]["workflow_version"]["const"] == "1.0.0"
    assert schemas["run-state"]["properties"]["workflow_version"]["const"] == "1.0.0"


def test_events_never_stream_secrets(schemas: dict) -> None:
    """Criterion: events carry no prompts or secrets, only a safe summary."""
    event_props = schemas["run-event"]["$defs"]["event"]["properties"]
    assert "summary" in event_props
    assert "prompt" not in event_props
    assert "arguments" not in event_props


def test_human_authorization_matches_canonical_vocabulary(schemas: dict) -> None:
    """The command assertion is closed over the canonical parent authorization tuple."""
    auth = schemas["run-command"]["properties"]["authorization"]
    assert set(auth["required"]) == {"action", "resource"}
    assert auth["properties"]["action"]["const"] == "run.approve"
    resource = auth["properties"]["resource"]
    assert resource["properties"]["type"]["const"] == "incident_workflow"
    assert resource["properties"]["id"]["const"] == "incident-response"


def test_runtime_api_is_not_implemented_yet() -> None:
    """Out of scope for HT-INC-04: no FastAPI router exists."""
    assert not (REPOSITORY_ROOT / "src" / "sre_agent" / "incident" / "run_router.py").exists()


@pytest.fixture(scope="module")
def correlation() -> dict:
    return load_yaml(CORRELATION_PATH)


def test_turn_id_never_crosses_to_the_gateway(correlation: dict) -> None:
    """C05: turn_id is domain-internal; the gateway only ever sees task_id."""
    by_name = {item["name"]: item for item in correlation["identifiers"]}
    assert by_name["turn_id"]["crosses_to_gateway"] is False
    for name in ("incident_id", "run_id", "task_id"):
        assert by_name[name]["crosses_to_gateway"] is True


def test_task_id_is_derived_from_turn_id(correlation: dict) -> None:
    """C05: the derivation is deterministic and replayable from the document."""
    derivation = correlation["derivation"]
    assert (derivation["from"], derivation["to"]) == ("turn_id", "task_id")
    example = derivation["example"]
    assert f"task_{example['turn_id'].removeprefix('turn_')}" == example["task_id"]
    numeric = derivation["numeric_suffix_example"]
    assert numeric == {"turn_id": "turn_12345678", "task_id": "task_12345678"}
    assert derivation["properties"]["deterministic"] is True


def test_schema_rejects_a_leaked_raw_turn_id(schemas: dict) -> None:
    """C05: a task_id that still carries the turn_ prefix is a leak, not a value."""
    validator = build_validator(schemas["run-event"])
    page = {
        "events": [
            {
                "event_id": "evt_00000001",
                "kind": "evidence_collected",
                "sequence": 0,
                "occurred_at": "2026-08-24T14:11:00Z",
                "task_id": "turn_a1b2c3d4",
            }
        ],
        "next_cursor": "seq:1",
        "has_more": False,
    }
    assert not validator.is_valid(page)

    page["events"][0]["task_id"] = "task_a1b2c3d4"
    assert validator.is_valid(page)


def test_numeric_turn_suffix_derives_a_valid_task_in_both_schemas(schemas: dict) -> None:
    task_id = "task_12345678"
    event_task = schemas["run-event"]["$defs"]["event"]["properties"]["task_id"]
    incident = load_yaml(REPOSITORY_ROOT / "agent" / "schemas" / "incident-state.schema.yaml")
    assert build_validator(event_task).is_valid(task_id)
    assert build_validator(incident["properties"]["task_id"]).is_valid(task_id)


def test_commands_record_who_concretely_acted(schemas: dict) -> None:
    """C06: the actor type alone cannot say which human approved a mitigation."""
    validator = build_validator(schemas["run-command"])
    without = {"command": "approve_mitigation", "actor": "human"}
    assert not validator.is_valid(without)

    with_identity = without | {
        "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"}
    }
    assert validator.is_valid(with_identity)


def test_actor_identity_is_additive_and_versioned(schemas: dict) -> None:
    """C06: the reference is added beside the type, never replacing it."""
    assert schemas["run-command"]["properties"]["actor"]["const"] == "human"
    event_actor = schemas["run-event"]["$defs"]["event"]["properties"]["actor"]
    assert event_actor["required"] == ["type"]
    reference = schemas["run-command"]["properties"]["actor_reference"]
    assert reference["properties"]["reference_version"]["const"] == "1.0.0"


def test_identity_is_for_attribution_not_authorization(schemas: dict) -> None:
    """C06 and C08: authority comes from a grant, never from the recorded identity."""
    description = schemas["run-command"]["properties"]["actor_reference"]["properties"][
        "principal_id"
    ]["description"]
    assert "never inferred" in description
