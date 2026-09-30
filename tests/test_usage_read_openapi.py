"""Publication and runtime activation checks for the usage-read contract.

Failure modes covered here: an old active version; an omitted canonical path;
missing or widened selectors; an undocumented response bound/status; and a
published schema reference that does not exist in the immutable inventory.
"""

import json
from pathlib import Path
from typing import Any

import yaml

from sre_agent.application import create_application
from sre_agent.release import CONTRACT_VERSION
from sre_agent.settings import Settings

RELEASES = Path("schemas/releases")


def test_active_runtime_publishes_the_versioned_usage_contract() -> None:
    release = RELEASES / CONTRACT_VERSION
    manifest = yaml.safe_load((release / "manifest.yaml").read_text())
    canonical = yaml.safe_load((release / "openapi/control-plane.yaml").read_text())
    runtime = create_application(
        Settings.from_environment(
            {
                "DATABASE_URL": "postgresql://unused",
                "AUDIT_HMAC_KEY": "contract-test-hmac-key",
            }
        )
    ).openapi()

    assert CONTRACT_VERSION == "2.5.0"
    assert manifest["contract_version"] == runtime["info"]["x-sre-agent-contract-version"]
    assert canonical["info"]["version"] == CONTRACT_VERSION
    assert runtime["info"]["x-sre-agent-contract-version"] == CONTRACT_VERSION
    assert (release / "manifest.yaml").is_file()

    path = "/v1/usage/consumption"
    assert path in runtime["paths"]
    assert path in canonical["paths"]
    runtime_operation = runtime["paths"][path]["get"]
    canonical_operation = canonical["paths"][path]["get"]
    assert runtime_operation["operationId"] == canonical_operation["operationId"]
    assert runtime_operation["summary"] == canonical_operation["summary"]

    def query_contract(operation: dict[str, Any]) -> dict[str, tuple[bool, dict[str, Any]]]:
        return {
            item["name"]: (
                item["required"],
                {
                    key: value
                    for key, value in item["schema"].items()
                    if key not in {"title", "description"}
                },
            )
            for item in operation["parameters"]
            if item["in"] == "query"
        }

    runtime_parameters = query_contract(runtime_operation)
    canonical_parameters = query_contract(canonical_operation)
    assert (
        set(runtime_parameters)
        == set(canonical_parameters)
        == {
            "request_id",
            "incident_id",
            "month",
        }
    )
    assert runtime_parameters == canonical_parameters
    canonical_security = canonical_operation.get("security", canonical.get("security", []))
    assert runtime_operation["security"] == canonical_security

    runtime_responses = runtime_operation["responses"]
    canonical_responses = canonical_operation["responses"]
    assert {"200", "401", "403", "413", "422", "503"} <= set(runtime_responses)
    assert set(runtime_responses) == set(canonical_responses)
    runtime_success = runtime_responses["200"]["content"]["application/json"]["schema"]
    canonical_success = canonical_responses["200"]["content"]["application/json"]["schema"]
    assert runtime_success["$ref"].startswith("#/components/schemas/")
    assert canonical_success["$ref"] == "urn:sre-agent:schema:usage-read:2.5.0"
    runtime_model = runtime["components"]["schemas"][
        runtime_success["$ref"].removeprefix("#/components/schemas/")
    ]
    assert runtime_model["additionalProperties"] is False
    assert set(runtime_model["properties"]) == set(
        json.loads((release / "json-schema/http/usage-read.schema.json").read_text())["properties"]
    )
    filter_schema = runtime_model["properties"]["filter"]
    assert "anyOf" in filter_schema or "oneOf" in filter_schema
    assert any(item["id"] == canonical_success["$ref"] for item in manifest["inventory"]["schemas"])


def test_every_published_usage_openapi_selector_preserves_optional_null_semantics() -> None:
    """Every shipped source must accept omission/null and retain selector constraints."""
    proposal = yaml.safe_load(
        Path("schemas/proposals/issue-333/usage-read.openapi.yaml").read_text()
    )
    release = RELEASES / CONTRACT_VERSION
    standalone = yaml.safe_load((release / "openapi/usage-read.yaml").read_text())
    canonical = yaml.safe_load((release / "openapi/control-plane.yaml").read_text())
    runtime = create_application(
        Settings.from_environment(
            {
                "DATABASE_URL": "postgresql://unused",
                "AUDIT_HMAC_KEY": "contract-test-hmac-key",
            }
        )
    ).openapi()

    expected_constraints = {
        "request_id": {"format": "uuid"},
        "incident_id": {"minLength": 1, "maxLength": 128},
        "month": {"pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
    }

    def variants(schema: dict[str, Any]) -> list[dict[str, Any]]:
        found = [schema]
        for key in ("anyOf", "oneOf", "allOf"):
            for child in schema.get(key, []):
                found.extend(variants(child))
        return found

    artifacts = {
        "standalone release": standalone,
        "canonical release": canonical,
        "proposal": proposal,
        "runtime": runtime,
    }
    for label, document in artifacts.items():
        operation = document["paths"]["/v1/usage/consumption"]["get"]
        parameters = {
            parameter["name"]: parameter
            for parameter in operation["parameters"]
            if parameter["in"] == "query"
        }
        assert set(parameters) == set(expected_constraints), label
        for name, constraints in expected_constraints.items():
            parameter = parameters[name]
            assert parameter["required"] is False, f"{label}: {name} must be optional"
            choices = variants(parameter["schema"])
            assert any(choice.get("type") == "null" for choice in choices), (
                f"{label}: {name} must preserve explicit null semantics"
            )
            assert any(
                choice.get("type") == "string"
                and all(choice.get(key) == value for key, value in constraints.items())
                for choice in choices
            ), f"{label}: {name} selector constraints are missing"
