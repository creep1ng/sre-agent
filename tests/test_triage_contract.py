"""Issue #23 C1: triage contract gates (OpenAPI + schemas + examples)."""

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
OPENAPI = yaml.safe_load((ROOT / "agent/api/triage.openapi.yaml").read_text())
SCHEMAS = {
    name: yaml.safe_load((ROOT / f"agent/schemas/{name}.schema.yaml").read_text())
    for name in ("triage-state", "triage-command")
}
ENVELOPE = json.loads(
    (ROOT / "schemas/releases/2.0.0/json-schema/http/error-envelope.schema.json").read_text()
)
URN = r"urn:sre-agent:schema:[a-z][a-z0-9-]*:[0-9]+\.[0-9]+\.[0-9]+$"
OPERATIONS = {"open_triage", "triage_dismiss", "triage_link", "triage_declare"}
ELIGIBLE = {"active", "investigating", "mitigating", "verifying"}


def _walk(node, refs):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            _walk(value, refs)
    elif isinstance(node, list):
        for value in node:
            _walk(value, refs)


def _resolve(doc, pointer):
    current = doc
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False
    return True


def test_contract_schemas_and_paths() -> None:
    for name, schema in SCHEMAS.items():
        Draft202012Validator.check_schema(schema)
        assert re.fullmatch(URN, schema["$id"]), name
    assert OPENAPI["openapi"].split(".")[0] == "3"
    assert {
        "/v1/alerts/{alert_id}/triage",
        "/v1/alerts/{alert_id}/triage/eligible-incidents",
        "/v1/alerts/{alert_id}/triage/commands",
    } <= set(OPENAPI["paths"])
    post = OPENAPI["paths"]["/v1/alerts/{alert_id}/triage/commands"]["post"]
    headers = {p["name"] for p in post["parameters"] if "name" in p}
    assert "Idempotency-Key" in headers
    key = next(p for p in post["parameters"] if p.get("name") == "Idempotency-Key")
    assert key["required"] is True and key["in"] == "header"
    assert set(post["responses"]) == {
        "200",
        "201",
        "400",
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    }


def test_contract_refs_resolve() -> None:
    known = {s["$id"] for s in SCHEMAS.values()} | {ENVELOPE["$id"]}
    refs: list[str] = []
    _walk(OPENAPI, refs)
    for ref in refs:
        if ref.startswith("#"):
            assert _resolve(OPENAPI, ref[1:]), ref
        elif ref.startswith("urn:"):
            assert ref in known, ref
        elif ref.startswith("./examples/triage/"):
            assert (ROOT / "agent/api" / ref[2:]).exists(), ref
        else:
            raise AssertionError(f"unsupported reference '{ref}'")


def test_command_payloads_are_closed_per_operation() -> None:
    variants = SCHEMAS["triage-command"]["oneOf"]
    assert {v["properties"]["operation"]["const"] for v in variants} == OPERATIONS
    by_op = {v["properties"]["operation"]["const"]: v for v in variants}
    for operation in OPERATIONS:
        assert by_op[operation]["required"] == (
            ["operation", "expected_version"]
            if operation == "open_triage"
            else ["operation", "expected_version", "reason"]
            if operation != "triage_link"
            else ["operation", "expected_version", "reason", "target_incident_id"]
        )
    assert "actor" not in by_op["triage_declare"]["properties"]
    assert by_op["triage_dismiss"]["properties"]["reason"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 1000,
    }


def test_eligible_states_exclude_terminal() -> None:
    items = OPENAPI["components"]["schemas"]["EligibleIncidents"]["properties"]["items"]
    assert set(items["items"]["properties"]["state"]["enum"]) == ELIGIBLE
    assert not (ELIGIBLE & {"resolved", "postmortem", "closed"})


def test_contract_examples_validate() -> None:
    by_id = {s["$id"]: s for s in SCHEMAS.values()}
    by_id[ENVELOPE["$id"]] = ENVELOPE
    registry = Registry().with_resources(
        [(sid, Resource.from_contents(s)) for sid, s in by_id.items()]
    )
    cases = {
        "triage-open.json": "urn:sre-agent:schema:triage-state:1.0.0",
        "command-request.json": "urn:sre-agent:schema:triage-command:1.0.0",
        "command-declare.json": "urn:sre-agent:schema:triage-state:1.0.0",
        "error-409.json": "urn:sre-agent:schema:error-envelope:2.0.0",
    }
    errors: list[str] = []
    for filename, schema_id in cases.items():
        document = json.loads((ROOT / "agent/api/examples/triage" / filename).read_text())
        validator = Draft202012Validator(
            by_id[schema_id], registry=registry, format_checker=FormatChecker()
        )
        for problem in validator.iter_errors(document["value"]):
            errors.append(f"{filename}: {problem.message}")
    assert errors == []
