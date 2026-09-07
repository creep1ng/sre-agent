"""Acceptance tests for the incident run API contract (HT-INC-04, issue #145).

Each test maps to an acceptance criterion of the issue so a failure names what regressed.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_run_api import (  # noqa: E402
    CORRELATION_PATH,
    OPENAPI_PATH,
    PROJECTION_PATH,
    REQUIRED_PATHS,
    SCHEMAS,
    _unclosed_object_paths,
    build_validator,
    check_decision_correlation,
    check_http_fixtures,
    check_openapi,
    external_schema_registry,
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


def test_resume_returns_the_existing_run_with_200() -> None:
    """Resumption is not creation: the response keeps the requested run identity."""
    import json

    fixture = json.loads(
        (REPOSITORY_ROOT / "agent/api/examples/http/start-resume.json").read_text(encoding="utf-8")
    )["x-http-mock"]
    assert fixture["response"]["status"] == 200
    assert fixture["request"]["body"]["resume_from_run_id"] == fixture["response"]["body"]["run_id"]


@pytest.mark.parametrize(
    ("ref", "expected_error"),
    [
        ("urn:sre-agent:schema:run-state:not-semver", "schema URN is malformed"),
        ("urn:sre-agent:schema:missing:1.0.0", "absent from the local registry"),
        ("./examples/http/missing.json", "external example reference is missing"),
    ],
)
def test_openapi_rejects_bad_external_references(
    openapi: dict, schemas: dict, ref: str, expected_error: str
) -> None:
    registry, errors = external_schema_registry(schemas)
    assert errors == []
    mutated = deepcopy(openapi)
    content = mutated["paths"]["/v1/incidents/{incident_id}/runs"]["post"]["responses"]["201"][
        "content"
    ]["application/json"]
    content["examples"]["created"] = {"$ref": ref}
    assert any(expected_error in error for error in check_openapi(registry, mutated))


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


def test_human_authorization_matches_every_catalog_command(schemas: dict) -> None:
    """Each command accepts only the action resolved by the canonical catalog."""
    authorization = load_yaml(REPOSITORY_ROOT / "agent/api/authorization.v1.yaml")
    command_schema = schemas["run-command"]
    auth = command_schema["properties"]["authorization"]
    assert set(auth["required"]) == {"action", "resource"}
    assert set(auth["properties"]["action"]["enum"]) == set(
        authorization["command_action_map"].values()
    )

    validator = build_validator(command_schema)
    identity = {"reference_version": "1.0.0", "principal_id": "demo-human"}
    resource = {"type": "incident_workflow", "id": "incident-response"}
    for command, action in authorization["command_action_map"].items():
        payload = {
            "command": command,
            "actor": "human",
            "actor_reference": identity,
            "authorization": {"action": action, "resource": resource},
        }
        if command == "propose_disposition":
            payload["disposition"] = "link"
        assert validator.is_valid(payload), command
        payload["authorization"] = {
            "action": "run.command" if action == "run.approve" else "run.approve",
            "resource": resource,
        }
        assert not validator.is_valid(payload), command


def test_disposition_is_exclusive_to_propose_disposition(schemas: dict) -> None:
    validator = build_validator(schemas["run-command"])
    identity = {"reference_version": "1.0.0", "principal_id": "demo-human"}
    proposed = {"command": "propose_disposition", "actor": "human", "actor_reference": identity}
    assert not validator.is_valid(proposed)
    assert not validator.is_valid(proposed | {"disposition": None})
    assert validator.is_valid(proposed | {"disposition": "declare"})
    assert not validator.is_valid(
        {
            "command": "escalate",
            "actor": "human",
            "actor_reference": identity,
            "disposition": "link",
        }
    )


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


@pytest.fixture(scope="module")
def projection() -> dict:
    return load_yaml(PROJECTION_PATH)


def test_safe_projection_declares_no_sensitive_field(projection: dict) -> None:
    """C07: the public snapshot must not be able to carry prompts or tool arguments."""
    from validate_run_api import _declared_property_names

    forbidden = set(projection["forbidden_in_safe_projection"])
    for relative in projection["safe_projection"]["schemas"]:
        declared: set[str] = set()
        _declared_property_names(load_yaml(REPOSITORY_ROOT / relative), declared)
        assert not (declared & forbidden), f"{relative} leaks {declared & forbidden}"


def test_projection_policy_fails_closed(projection: dict) -> None:
    """An unregistered field must break the build, not ship silently."""
    from validate_run_api import _declared_property_names

    allowed = set(projection["safe_projection"]["allowed_fields"])
    for relative in projection["safe_projection"]["schemas"]:
        declared: set[str] = set()
        _declared_property_names(load_yaml(REPOSITORY_ROOT / relative), declared)
        assert declared <= allowed, f"{relative} declares unregistered {declared - allowed}"


def test_context_is_a_separate_surface(projection: dict) -> None:
    """C07: separation is enforced by authorization, not only by schema shape."""
    safe = projection["safe_projection"]
    context = projection["sensitive_context"]
    assert safe["authorized_by"] == "run.read"
    assert context["authorized_by"] == "run.read_context"
    assert context["authorized_by"] != safe["authorized_by"]


def test_context_endpoint_exists_and_can_deny(openapi: dict) -> None:
    """The sensitive context has its own path and can refuse an insufficient grant."""
    path = "/v1/incidents/{incident_id}/runs/{run_id}/context"
    assert path in openapi["paths"]
    assert "403" in openapi["paths"][path]["get"]["responses"]


def test_context_may_carry_what_the_projection_may_not(schemas: dict) -> None:
    """The point of the split: this is where the sensitive content is allowed to live."""
    turn = schemas["run-context"]["$defs"]["turn"]["properties"]
    assert "assembled_input" in turn
    assert "model_output" in turn
    assert "tool_invocation" in turn


def test_context_still_refuses_a_leaked_turn_id(schemas: dict) -> None:
    """C05 holds inside the context too: task_id never keeps the turn_ prefix."""
    validator = build_validator(schemas["run-context"])
    context = {
        "run_id": "run_a1b2c3d4e5",
        "incident_id": "inc-test",
        "turns": [
            {
                "turn_id": "turn_a1b2c3d4",
                "task_id": "turn_a1b2c3d4",
                "sequence": 0,
                "occurred_at": "2026-08-24T14:11:00Z",
            }
        ],
        "retrieved_at": "2026-08-24T14:30:00Z",
    }
    assert not validator.is_valid(context)
    context["turns"][0]["task_id"] = "task_a1b2c3d4"
    assert validator.is_valid(context)


def test_safe_projection_objects_are_structurally_closed(projection: dict) -> None:
    for relative in projection["safe_projection"]["schemas"]:
        schema = load_yaml(REPOSITORY_ROOT / relative)
        assert _unclosed_object_paths(schema) == []

    mutated = deepcopy(load_yaml(REPOSITORY_ROOT / "agent/schemas/run-event.schema.yaml"))
    mutated["$defs"]["event"].pop("additionalProperties")
    assert "$/$defs/event" in _unclosed_object_paths(mutated)
    assert "$" in _unclosed_object_paths({"properties": {"public": {"type": "string"}}})


def test_projection_walk_reaches_nested_properties() -> None:
    """The non-exposure walk must not stop one level short.

    An audit of this contract found the walk collecting property names without
    descending into their subschemas, so a sensitive field nested inside an object
    property passed the check. This pins the fixed behaviour.
    """
    from validate_run_api import _declared_property_names

    schema = {
        "properties": {
            "actor": {
                "type": "object",
                "properties": {"type": {}, "prompt": {}},
            }
        }
    }
    found: set[str] = set()
    _declared_property_names(schema, found)
    assert {"actor", "type", "prompt"} <= found


def test_every_allowed_field_is_actually_used(projection: dict) -> None:
    """An allow-list entry nobody uses is a permission granted for nothing."""
    from validate_run_api import _declared_property_names

    used: set[str] = set()
    for relative in projection["safe_projection"]["schemas"]:
        _declared_property_names(load_yaml(REPOSITORY_ROOT / relative), used)
    unused = set(projection["safe_projection"]["allowed_fields"]) - used
    assert not unused, f"allow-list grants unused fields: {sorted(unused)}"


def test_decision_events_require_correlation_and_identity(schemas: dict) -> None:
    """Human commands and denials are attributable; generic system events stay valid."""
    validator = build_validator(schemas["run-event"])
    page = {
        "events": [
            {
                "event_id": "evt_00000001",
                "kind": "human_command",
                "sequence": 0,
                "occurred_at": "2026-08-24T14:10:00Z",
            }
        ],
        "next_cursor": "seq:1",
        "has_more": False,
    }
    assert not validator.is_valid(page)
    page["events"][0] |= {
        "request_id": "3f2c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
        "actor": {
            "type": "human",
            "reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
        },
    }
    assert validator.is_valid(page)
    page["events"][0]["actor"]["reference"] = None
    assert not validator.is_valid(page)

    page["events"] = [
        {
            "event_id": "evt_00000002",
            "kind": "state_change",
            "sequence": 1,
            "occurred_at": "2026-08-24T14:11:00Z",
        }
    ]
    assert validator.is_valid(page)


def test_static_mocks_and_decision_correlation_are_executable(schemas: dict) -> None:
    registry, errors = external_schema_registry(schemas)
    assert errors == []
    assert "urn:sre-agent:schema:error-envelope:1.2.0" in registry
    assert check_http_fixtures(registry) == []
    assert check_decision_correlation(schemas) == []
