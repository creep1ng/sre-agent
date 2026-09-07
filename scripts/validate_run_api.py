"""Validate the incident run API contract (HT-INC-04, issue #145).

Automated acceptance gate for the run API. Runs in CI and locally with:

    python scripts/validate_run_api.py

Checks:
1. Every request/response schema is a well-formed JSON Schema draft 2020-12 document.
2. The OpenAPI document is parseable, declares the four required paths, and every
   local $ref resolves.
3. Positive examples validate against their schema; negative examples are rejected.
4. `format` is actually enforced (date-time, uuid), not merely annotated.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT = REPOSITORY_ROOT / "agent"
OPENAPI_PATH = AGENT / "api" / "incident-runs.openapi.yaml"
EXAMPLES = AGENT / "api" / "examples"
CORRELATION_PATH = AGENT / "api" / "correlation-mapping.v1.yaml"
TRANSPORT_ADR_PATH = REPOSITORY_ROOT / "docs" / "adrs" / "ADR-008-run-events-transport.md"
PROJECTION_PATH = AGENT / "api" / "projection-policy.v1.yaml"
AUTHORIZATION_PATH = AGENT / "api" / "authorization.v1.yaml"
ERROR_ENVELOPE_PATH = (
    REPOSITORY_ROOT / "schemas/releases/1.2.0/json-schema/http/error-envelope.schema.json"
)
HTTP_FIXTURES = EXAMPLES / "http"
CORRELATION_FIXTURES = EXAMPLES / "correlation"
URN_REFERENCE = re.compile(r"^urn:sre-agent:schema:[a-z][a-z0-9-]*:[0-9]+\.[0-9]+\.[0-9]+$")
EXPECTED_HTTP_FIXTURES = {
    "start-created.json": ("POST", "201"),
    "start-replay.json": ("POST", "200"),
    "start-resume.json": ("POST", "200"),
    "get-state.json": ("GET", "200"),
    "command-accepted.json": ("POST", "202"),
    "events-page.json": ("GET", "200"),
    "get-context.json": ("GET", "200"),
    "error-401.json": ("POST", "401"),
    "error-403.json": ("POST", "403"),
    "error-404.json": ("GET", "404"),
    "error-409.json": ("POST", "409"),
    "error-422.json": ("POST", "422"),
    "error-503.json": ("POST", "503"),
}

SCHEMAS = {
    "run-context": AGENT / "schemas" / "run-context.schema.yaml",
    "run-start-request": AGENT / "schemas" / "run-start-request.schema.yaml",
    "run-state": AGENT / "schemas" / "run-state.schema.yaml",
    "run-command": AGENT / "schemas" / "run-command.schema.yaml",
    "run-event": AGENT / "schemas" / "run-event.schema.yaml",
}

REQUIRED_PATHS = {
    "/v1/incidents/{incident_id}/runs",
    "/v1/incidents/{incident_id}/runs/{run_id}",
    "/v1/incidents/{incident_id}/runs/{run_id}/commands",
    "/v1/incidents/{incident_id}/runs/{run_id}/events",
}

# Which schema each example validates against.
POSITIVE = {
    "start-request.json": "run-start-request",
    "run-state-running.json": "run-state",
    "run-state-awaiting.json": "run-state",
    "command-approve.json": "run-command",
    "events-page.json": "run-event",
    "run-context.json": "run-context",
}
NEGATIVE = {
    "start-foreign-version.json": "run-start-request",
    "command-by-agent.json": "run-command",
    "state-unknown-status.json": "run-state",
    "command-without-actor-identity.json": "run-command",
    "event-leaks-raw-turn-as-task.json": "run-event",
    "context-leaks-raw-turn.json": "run-context",
    "event-sensitive-prompt.json": "run-event",
    "state-sensitive-token.json": "run-state",
}


def load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"required contract file is missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def build_validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def external_schema_registry(schemas: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """Load every schema available to this contract, including frozen shared bodies."""
    errors: list[str] = []
    registry = dict(schemas)
    try:
        error_envelope = json.loads(ERROR_ENVELOPE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return registry, [f"shared error envelope is missing: {ERROR_ENVELOPE_PATH}"]
    registry["error-envelope"] = error_envelope

    by_id: dict[str, dict] = {}
    for name, schema in registry.items():
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not URN_REFERENCE.fullmatch(schema_id):
            errors.append(
                f"schema registry entry '{name}' has malformed immutable $id {schema_id!r}"
            )
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:  # noqa: BLE001
            errors.append(f"schema registry entry '{name}' is invalid: {error}")
            continue
        if schema_id in by_id:
            errors.append(f"schema registry has duplicate $id '{schema_id}'")
        by_id[schema_id] = schema
    return by_id, errors


def check_schemas() -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    schemas: dict[str, dict] = {}
    for name, path in SCHEMAS.items():
        schema = load_yaml(path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:  # noqa: BLE001
            errors.append(f"schema '{name}' is not valid draft 2020-12: {error}")
            continue
        schemas[name] = schema
    return schemas, errors


def check_format_enforcement() -> list[str]:
    checker = FormatChecker()
    errors: list[str] = []
    for name, subschema, bad in (
        ("date-time", {"type": "string", "format": "date-time"}, "not-a-timestamp"),
        ("uuid", {"type": "string", "format": "uuid"}, "not-a-uuid"),
    ):
        if Draft202012Validator({**subschema}, format_checker=checker).is_valid(bad):
            errors.append(f"format '{name}' is not enforced; install the jsonschema[format] extra")
    return errors


def _declared_property_names(node: Any, found: set[str]) -> None:
    """Collect every property name a schema declares, at any depth.

    The walk descends into the property subschemas as well as their names. Without that
    it stops one level short, and a sensitive field nested inside an object property
    would never be seen: exactly the blind spot the safe projection cannot afford.
    """
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            found.update(properties)
            for subschema in properties.values():
                _declared_property_names(subschema, found)
        for key, value in node.items():
            if key != "properties":
                _declared_property_names(value, found)
    elif isinstance(node, list):
        for item in node:
            _declared_property_names(item, found)


def _unclosed_object_paths(node: Any, path: str = "$", conditional: bool = False) -> list[str]:
    """Return public object-schema locations that do not reject unknown fields.

    Conditional `if`/`then` fragments intentionally inherit their parent object. They
    are constraints, not new payload objects. A normal properties-bearing schema still
    counts as an object even when it omits `type`, so public schemas cannot bypass this
    gate by deleting one keyword.
    """
    unclosed: list[str] = []
    if isinstance(node, dict):
        has_properties = isinstance(node.get("properties"), dict)
        is_object = node.get("type") == "object" or (has_properties and not conditional)
        if is_object and node.get("additionalProperties") is not False:
            unclosed.append(path)
        for key, value in node.items():
            unclosed.extend(
                _unclosed_object_paths(
                    value,
                    f"{path}/{key}",
                    conditional=conditional or key in {"if", "then", "else"},
                )
            )
    elif isinstance(node, list):
        for index, item in enumerate(node):
            unclosed.extend(_unclosed_object_paths(item, f"{path}/{index}", conditional))
    return unclosed


def check_safe_projection() -> list[str]:
    """Audit finding C07: prove the public snapshot cannot carry sensitive content.

    The policy is an allow-list because a deny-list fails open: a field added later leaks
    until somebody remembers to ban it. Walking the schemas here makes the policy fail
    closed instead, the same way the compose allow-list keeps a provider credential out of
    a client image (docs/architecture.md).
    """
    errors: list[str] = []
    policy = load_yaml(PROJECTION_PATH)
    safe = policy["safe_projection"]
    allowed = set(safe["allowed_fields"])
    forbidden = set(policy["forbidden_in_safe_projection"])

    overlap = allowed & forbidden
    if overlap:
        errors.append(f"fields are both allowed and forbidden: {sorted(overlap)}")

    for relative in safe["schemas"]:
        path = REPOSITORY_ROOT / relative
        if not path.exists():
            errors.append(f"safe projection schema '{relative}' does not exist")
            continue
        declared: set[str] = set()
        schema = load_yaml(path)
        _declared_property_names(schema, declared)

        for object_path in _unclosed_object_paths(schema):
            errors.append(
                f"'{relative}' leaves public object '{object_path}' open to additional properties"
            )

        for name in sorted(declared & forbidden):
            errors.append(
                f"'{relative}' declares '{name}', which the projection policy forbids in "
                "a safe projection"
            )
        for name in sorted(declared - allowed - forbidden):
            errors.append(
                f"'{relative}' declares '{name}', which is not registered in the "
                "projection allow-list; register it or move it behind the context endpoint"
            )

    # The sensitive context must be a separate surface with its own action.
    context = policy["sensitive_context"]
    if context["authorized_by"] == safe["authorized_by"]:
        errors.append(
            "the sensitive context is authorized by the same action as the safe "
            "projection; C07 requires them to be separable"
        )
    if not (REPOSITORY_ROOT / context["schema"]).exists():
        errors.append(f"sensitive context schema '{context['schema']}' does not exist")

    api = load_yaml(OPENAPI_PATH)
    context_path = "/v1/incidents/{incident_id}/runs/{run_id}/context"
    if context_path not in api["paths"]:
        errors.append("the OpenAPI does not expose the sensitive context endpoint")

    return errors


def check_transport_decision() -> list[str]:
    """The polling/SSE decision is a deliverable of the issue, not an implicit choice.

    The contract encodes polling in `GET .../events`; without the ADR beside it a reader
    cannot tell whether streaming was rejected or simply forgotten.
    """
    errors: list[str] = []
    if not TRANSPORT_ADR_PATH.exists():
        return [f"the transport decision record is missing: {TRANSPORT_ADR_PATH}"]

    adr = TRANSPORT_ADR_PATH.read_text(encoding="utf-8")
    if "Status: Accepted" not in adr:
        errors.append("the transport ADR is not marked Accepted")
    if "SSE" not in adr:
        errors.append("the transport ADR does not record the alternative it rejected")

    api = OPENAPI_PATH.read_text(encoding="utf-8")
    if "text/event-stream" in api:
        errors.append("the API declares a streaming media type while the ADR decides polling")
    return errors


def check_correlation_mapping(schemas: dict[str, Any]) -> list[str]:
    """Audit finding C05: turn_id is domain-internal and must never reach the gateway.

    The mapping document is only a promise until something asserts it, so the derivation
    is replayed here and the identifiers that may cross the boundary are pinned.
    """
    errors: list[str] = []
    mapping = load_yaml(CORRELATION_PATH)

    crossing = {item["name"] for item in mapping["identifiers"] if item.get("crosses_to_gateway")}
    if "turn_id" in crossing:
        errors.append("turn_id is marked as crossing to the gateway; C05 forbids it")
    for required in ("incident_id", "run_id", "task_id"):
        if required not in crossing:
            errors.append(f"'{required}' must be declared as crossing to the gateway")

    derivation = mapping["derivation"]
    if derivation.get("from") != "turn_id" or derivation.get("to") != "task_id":
        errors.append("the derivation must map turn_id to task_id")

    event_task = schemas["run-event"]["$defs"]["event"]["properties"]["task_id"]
    incident_task = load_yaml(AGENT / "schemas" / "incident-state.schema.yaml")["properties"][
        "task_id"
    ]
    for name in ("example", "numeric_suffix_example"):
        example = derivation.get(name, {})
        turn_id, task_id = example.get("turn_id", ""), example.get("task_id", "")
        expected = f"task_{turn_id.removeprefix('turn_')}"
        if not turn_id.startswith("turn_") or task_id != expected:
            errors.append(
                f"the documented {name} does not follow the rule: {turn_id!r} -> {task_id!r}"
            )
        for schema_name, task_schema in (
            ("run-event", event_task),
            ("incident-state", incident_task),
        ):
            if not build_validator(task_schema).is_valid(task_id):
                errors.append(f"derived task_id {task_id!r} is invalid in {schema_name}")

    # Both identifiers must exist in the schemas that carry them.
    event_props = schemas["run-event"]["$defs"]["event"]["properties"]
    for field in ("turn_id", "task_id"):
        if field not in event_props:
            errors.append(f"run-event does not carry '{field}'")
    if "turn_id" not in schemas["run-command"]["properties"]:
        errors.append("run-command does not carry 'turn_id'")

    return errors


def check_authorization_contract(schemas: dict[str, Any]) -> list[str]:
    """Every command assertion must be closed over the catalog action map."""
    errors: list[str] = []
    vocabulary = load_yaml(AUTHORIZATION_PATH)
    command = schemas["run-command"]
    props = command["properties"]["authorization"]["properties"]
    resource_props = props["resource"]["properties"]
    command_action_map = vocabulary["command_action_map"]
    declared_actions = set(props["action"].get("enum", []))
    expected_actions = set(command_action_map.values())
    if declared_actions != expected_actions:
        errors.append("run-command authorization actions differ from authorization.v1.yaml")

    resource = next(item for item in vocabulary["resources"] if item["id"] == "incident-response")
    if resource_props["type"].get("const") != resource["type"]:
        errors.append("run-command resource type differs from authorization.v1.yaml")
    if resource_props["id"].get("const") != resource["id"]:
        errors.append("run-command resource id differs from authorization.v1.yaml")

    validator = build_validator(command)
    identity = {"reference_version": "1.0.0", "principal_id": "demo-human"}
    resource_assertion = {"type": resource["type"], "id": resource["id"]}
    for command_name, action in command_action_map.items():
        payload = {
            "command": command_name,
            "actor": "human",
            "actor_reference": identity,
            "authorization": {"action": action, "resource": resource_assertion},
        }
        if command_name == "propose_disposition":
            payload["disposition"] = "link"
        if not validator.is_valid(payload):
            errors.append(f"run-command rejects catalog mapping for '{command_name}' -> '{action}'")
    return errors


def check_actor_identity(schemas: dict[str, Any]) -> list[str]:
    """Audit finding C06: record the concrete actor, not only its type.

    The type is kept so existing consumers keep working; the reference is added beside
    it. A command is always attributable, so its reference is required.
    """
    errors: list[str] = []

    command = schemas["run-command"]
    if "actor" not in command["properties"]:
        errors.append("run-command dropped the actor type; C06 must be additive")
    if "actor_reference" not in command.get("required", []):
        errors.append("run-command must require actor_reference: a command is attributable")

    reference = command["properties"].get("actor_reference", {})
    for field in ("reference_version", "principal_id"):
        if field not in reference.get("required", []):
            errors.append(f"actor_reference must require '{field}'")
    if "const" not in reference.get("properties", {}).get("reference_version", {}):
        errors.append("actor_reference must pin its version with const")

    event_actor = schemas["run-event"]["$defs"]["event"]["properties"].get("actor", {})
    if "type" not in event_actor.get("required", []):
        errors.append("run-event actor must still require its type")
    if "reference" not in event_actor.get("properties", {}):
        errors.append("run-event actor must be able to carry a concrete reference")

    return errors


def _iter_refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        refs = [value for key, value in node.items() if key == "$ref" and isinstance(value, str)]
        return refs + [ref for value in node.values() for ref in _iter_refs(value)]
    if isinstance(node, list):
        return [ref for value in node for ref in _iter_refs(value)]
    return []


def _response_for(doc: dict, response: dict) -> dict:
    ref = response.get("$ref")
    if not ref:
        return response
    if not ref.startswith("#/components/responses/"):
        raise ValueError(f"unsupported response reference '{ref}'")
    return doc["components"]["responses"][ref.rsplit("/", 1)[1]]


def check_openapi(registry: dict[str, dict], document: dict | None = None) -> list[str]:
    errors: list[str] = []
    doc = document if document is not None else load_yaml(OPENAPI_PATH)

    if doc.get("openapi", "").split(".")[0] != "3":
        errors.append("openapi document is not version 3.x")

    declared = set(doc.get("paths", {}))
    for path in REQUIRED_PATHS - declared:
        errors.append(f"openapi is missing required path '{path}'")

    refs = _iter_refs(doc)
    for ref in refs:
        if ref.startswith("#/"):
            parts = ref.removeprefix("#/").split("/")
            target: Any = doc
            try:
                for part in parts:
                    target = target[part]
            except (KeyError, TypeError):
                errors.append(f"openapi $ref '{ref}' does not resolve")
        elif ref.startswith("urn:sre-agent:schema:"):
            if not URN_REFERENCE.fullmatch(ref):
                errors.append(f"openapi schema URN is malformed: '{ref}'")
            elif ref not in registry:
                errors.append(f"openapi schema URN is absent from the local registry: '{ref}'")
        elif ref.startswith("./"):
            path = OPENAPI_PATH.parent / ref
            if not path.exists():
                errors.append(f"openapi external example reference is missing: '{ref}'")
        else:
            errors.append(f"openapi uses unsupported external $ref '{ref}'")
    return errors


def _operation_for_fixture(doc: dict, method: str, request_path: str) -> tuple[str, dict] | None:
    parsed = urlsplit(request_path)
    for template, item in doc["paths"].items():
        pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", template) + "$"
        if re.fullmatch(pattern, parsed.path):
            operation = item.get(method.lower())
            if operation:
                return template, operation
    return None


def _schema_from_content(content: dict, registry: dict[str, dict]) -> dict | None:
    schema = content.get("application/json", {}).get("schema")
    if not schema:
        return None
    ref = schema.get("$ref")
    return registry.get(ref) if ref else schema


def _header(headers: dict, name: str) -> str | None:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), None)


def check_http_fixtures(registry: dict[str, dict]) -> list[str]:
    """Validate static mocks against the endpoint selected by their method and path."""
    errors: list[str] = []
    doc = load_yaml(OPENAPI_PATH)
    referenced = {
        (OPENAPI_PATH.parent / ref).resolve()
        for ref in _iter_refs(doc)
        if ref.startswith("./examples/http/")
    }
    fixtures = sorted(HTTP_FIXTURES.glob("*.json"))
    if not fixtures:
        return ["no HTTP mock fixtures are published"]
    if {path.name for path in fixtures} != set(EXPECTED_HTTP_FIXTURES):
        errors.append("HTTP mock fixture coverage is incomplete or contains an unexpected fixture")
    if {path.resolve() for path in fixtures} != referenced:
        errors.append("OpenAPI response examples and HTTP mock fixture files differ")

    for path in fixtures:
        fixture = load_json(path)
        mock = fixture.get("x-http-mock", {})
        request, response = mock.get("request", {}), mock.get("response", {})
        method, request_path = request.get("method"), request.get("path")
        operation_match = _operation_for_fixture(doc, method or "", request_path or "")
        if not operation_match:
            errors.append(f"HTTP fixture '{path.name}' does not select an OpenAPI operation")
            continue
        _, operation = operation_match
        status = str(response.get("status"))
        if (method, status) != EXPECTED_HTTP_FIXTURES.get(path.name):
            errors.append(f"HTTP fixture '{path.name}' changed its required method/status coverage")
        if status not in operation["responses"]:
            errors.append(f"HTTP fixture '{path.name}' uses undeclared response status {status}")
            continue
        request_headers = request.get("headers")
        response_headers = response.get("headers")
        if not isinstance(request_headers, dict) or not isinstance(response_headers, dict):
            errors.append(f"HTTP fixture '{path.name}' must publish request and response headers")
            continue
        if status != "401" and not _header(request_headers, "Authorization"):
            errors.append(f"HTTP fixture '{path.name}' lacks an authenticated request header")
        if _header(response_headers, "Content-Type") != "application/json":
            errors.append(
                f"HTTP fixture '{path.name}' response must publish Content-Type application/json"
            )

        for parameter in operation.get("parameters", []):
            if parameter.get("$ref"):
                parameter = doc["components"]["parameters"][parameter["$ref"].rsplit("/", 1)[1]]
            if parameter.get("required") and parameter.get("in") == "header":
                if not _header(request_headers, parameter["name"]):
                    errors.append(
                        f"HTTP fixture '{path.name}' lacks required header '{parameter['name']}'"
                    )
        resolved_response = _response_for(doc, operation["responses"][status])
        for header_name, header_schema in resolved_response.get("headers", {}).items():
            value = _header(response_headers, header_name)
            if value is None:
                errors.append(f"HTTP fixture '{path.name}' lacks response header '{header_name}'")
            elif not build_validator(header_schema.get("schema", {})).is_valid(value):
                errors.append(
                    f"HTTP fixture '{path.name}' has invalid response header '{header_name}'"
                )

        body_schema = _schema_from_content(resolved_response.get("content", {}), registry)
        if body_schema is None:
            errors.append(f"HTTP fixture '{path.name}' has no response body schema")
        elif not build_validator(body_schema).is_valid(response.get("body")):
            errors.append(f"HTTP fixture '{path.name}' response body fails its OpenAPI schema")
        if fixture.get("value") != response.get("body"):
            errors.append(f"HTTP fixture '{path.name}' OpenAPI value differs from response body")

        request_body = request.get("body")
        request_schema = _schema_from_content(
            operation.get("requestBody", {}).get("content", {}), registry
        )
        request_is_valid = request_schema and build_validator(request_schema).is_valid(request_body)
        if request_schema and status != "422" and not request_is_valid:
            errors.append(f"HTTP fixture '{path.name}' request body fails its OpenAPI schema")
    return errors


def check_decision_correlation(schemas: dict[str, dict]) -> list[str]:
    """Decision fixtures prove endpoint scope and audit metadata stay correlated."""
    errors: list[str] = []
    files = sorted(CORRELATION_FIXTURES.glob("authorization-*.json"))
    expected_decisions = {
        "authorization-allow.json": ("allow", "human_command"),
        "authorization-deny.json": ("deny", "denial"),
    }
    if {path.name for path in files} != set(expected_decisions):
        return ["authorization allow/deny correlation fixtures are incomplete"]

    command_validator = build_validator(schemas["run-command"])
    event_validator = build_validator(schemas["run-event"])
    uuid_validator = build_validator({"type": "string", "format": "uuid"})
    for path in files:
        fixture = load_json(path)
        request, event, metadata = (
            fixture.get("request", {}),
            fixture.get("event", {}),
            fixture.get("internal_audit_metadata", {}),
        )
        match = re.fullmatch(
            r"/v1/incidents/(?P<incident_id>[a-z][a-z0-9_-]{2,63})/runs/"
            r"(?P<run_id>run_[a-z0-9]{8,32})/commands",
            request.get("path", ""),
        )
        if request.get("method") != "POST" or not match:
            errors.append(f"correlation fixture '{path.name}' must use a scoped command endpoint")
            continue
        expected_outcome, expected_kind = expected_decisions[path.name]
        if fixture.get("outcome") != expected_outcome or event.get("kind") != expected_kind:
            errors.append(f"correlation fixture '{path.name}' changed its decision semantics")
        request_id = request.get("request_id")
        if not uuid_validator.is_valid(request_id):
            errors.append(f"correlation fixture '{path.name}' has an invalid request_id")
        if not command_validator.is_valid(request.get("body")):
            errors.append(f"correlation fixture '{path.name}' has an invalid command body")
        event_page = {"events": [event], "next_cursor": "fixture:1", "has_more": False}
        if not event_validator.is_valid(event_page):
            errors.append(f"correlation fixture '{path.name}' has an invalid decision event")
        if event.get("request_id") != request_id or metadata.get("request_id") != request_id:
            errors.append(f"correlation fixture '{path.name}' does not retain request_id")
        if set(metadata) != {"request_id", "incident_id", "run_id"}:
            errors.append(
                f"correlation fixture '{path.name}' metadata must contain only "
                "canonical correlation"
            )
        scoped_metadata = (
            metadata.get("incident_id") == match["incident_id"]
            and metadata.get("run_id") == match["run_id"]
        )
        if not scoped_metadata:
            errors.append(
                f"correlation fixture '{path.name}' does not retain endpoint incident_id/run_id"
            )
        if metadata.get("run_id") is None:
            errors.append(
                f"correlation fixture '{path.name}' cannot null run_id after endpoint scope exists"
            )
        if "audit_event_id" in fixture or "audit_event_id" in metadata:
            errors.append(f"correlation fixture '{path.name}' invents a public audit_event_id")

        authenticated = request.get("authenticated_principal_id")
        claimed = request.get("body", {}).get("actor_reference", {}).get("principal_id")
        event_principal = event.get("actor", {}).get("reference", {}).get("principal_id")
        if fixture.get("outcome") == "allow" and claimed != authenticated:
            errors.append(
                f"allow fixture '{path.name}' does not attribute the authenticated principal"
            )
        if fixture.get("outcome") == "deny" and claimed == authenticated:
            errors.append(f"deny fixture '{path.name}' does not exercise spoofed actor rejection")
        if event_principal != authenticated:
            errors.append(f"correlation fixture '{path.name}' audit actor is not authoritative")
    return errors


def check_examples(schemas: dict[str, dict]) -> list[str]:
    errors: list[str] = []

    for filename, schema_name in POSITIVE.items():
        path = EXAMPLES / filename
        if not path.exists():
            errors.append(f"positive example '{filename}' is missing")
            continue
        problems = list(build_validator(schemas[schema_name]).iter_errors(load_json(path)))
        for problem in problems:
            errors.append(f"positive example '{filename}' failed: {problem.message}")

    for filename, schema_name in NEGATIVE.items():
        path = EXAMPLES / "negative" / filename
        if not path.exists():
            errors.append(f"negative example '{filename}' is missing")
            continue
        if build_validator(schemas[schema_name]).is_valid(load_json(path)):
            errors.append(
                f"negative example '{filename}' was accepted; the schema does not "
                "enforce the rule it encodes"
            )

    return errors


def validate() -> list[str]:
    schemas, schema_errors = check_schemas()
    registry, registry_errors = external_schema_registry(schemas)
    errors = [
        *schema_errors,
        *registry_errors,
        *check_format_enforcement(),
        *check_openapi(registry),
    ]
    if schemas:
        errors.extend(check_safe_projection())
        errors.extend(check_transport_decision())
        errors.extend(check_correlation_mapping(schemas))
        errors.extend(check_actor_identity(schemas))
        errors.extend(check_authorization_contract(schemas))
        errors.extend(check_examples(schemas))
        errors.extend(check_http_fixtures(registry))
        errors.extend(check_decision_correlation(schemas))
    return errors


def main() -> int:
    try:
        errors = validate()
    except FileNotFoundError as error:
        print(f"run api: {error}", file=sys.stderr)
        return 1

    if errors:
        print(f"run api: {len(errors)} problem(s) found", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    doc = load_yaml(OPENAPI_PATH)
    print(
        f"run api: OK ({len(doc.get('paths', {}))} paths, {len(SCHEMAS)} schemas, "
        f"{len(POSITIVE)} positive and {len(NEGATIVE)} negative examples)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
