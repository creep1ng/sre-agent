"""Reject cost/coverage contradictions at runtime and the generated HTTP schema.

Failure modes and valid boundary cases live in the shared invariant matrix;
request-count arithmetic is semantic, not expressible by standard JSON Schema.
"""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from sre_agent.application import create_application
from sre_agent.gateway.usage import UsageReadResponse
from sre_agent.settings import Settings

CASES = yaml.safe_load(Path("schemas/tooling/test/fixtures/usage-read-invariants.yaml").read_text())


def payload(case, kind):
    data = deepcopy(CASES["base"])
    if kind == "cost_cases":
        data["totals"]["cost"].update(
            {key: case[key] for key in ("amount", "currency", "precision")}
        )
        if case["name"] == "incompatible-prices":
            data["totals"]["cost"]["price_versions"].append("controlled-v2")
    else:
        data["coverage"] = {key: case[key] for key in ("status", "known", "incomplete", "unknown")}
        data["request_count"] = case["request_count"]
        data["months"] = (
            [{"month": "2026-09", "request_count": case["request_count"]}]
            if case["request_count"]
            else []
        )
        if not case["request_count"] or case["status"] != "complete":
            data["totals"].update(input_tokens=None, output_tokens=None, total_tokens=None)
            data["totals"]["cost"].update(amount=None, currency=None, precision=None)
    return data


@pytest.fixture(scope="module")
def http_schema():
    app = create_application(Settings("postgresql://unused", audit_hmac_key="controlled-test"))
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    return Draft202012Validator(
        {
            "$ref": "#/components/schemas/UsageReadResponse",
            "components": response.json()["components"],
        }
    )


@pytest.mark.parametrize(
    ("kind", "case"),
    [(kind, case) for kind in ("cost_cases", "coverage_cases") for case in CASES[kind]],
    ids=[case["name"] for kind in ("cost_cases", "coverage_cases") for case in CASES[kind]],
)
def test_usage_invariants_at_model_and_http_schema(kind, case, http_schema):
    data = payload(case, kind)
    if case["valid"]:
        UsageReadResponse.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            UsageReadResponse.model_validate(data)
    assert http_schema.is_valid(data) == (case["valid"] or case.get("rule") == "semantic")
