"""E2E round trip for immutable historical request attribution."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from issue454_support import (
    ADMIN,
    AUDIT_KEY,
    CONSUMER,
    CONSUMPTION,
    DATABASE_URL,
    OUTPUT,
    PROMPT,
    ControlledProvider,
    auth,
    read_item,
)
from issue454_support import (
    clean_history as clean_history,
)
from issue454_support import migrated_database as migrated_database
from jsonschema import Draft202012Validator

from sre_agent.application import create_application
from sre_agent.settings import Settings


def test_historical_assignment_survives_real_alias_reassignment() -> None:
    """Read before/after reassignment proves the old snapshot never follows alias."""
    provider = ControlledProvider()
    application = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    artifact: dict[str, object] = {}
    with TestClient(application) as client:
        before = client.get("/v1/model-aliases/triage-agent", headers=auth(ADMIN))
        after = client.get("/v1/model-aliases/remediation-agent", headers=auth(ADMIN))
        assert before.status_code == after.status_code == 200
        first_assignment, replacement = before.json(), after.json()
        replacement["router"] = "issue454-router-" + "r" * 84
        assert first_assignment["concrete_model"] != replacement["concrete_model"]
        try:
            first = client.post(
                "/v1/responses",
                headers=auth(CONSUMER),
                json={"model": "triage-agent", "input": PROMPT},
            )
            assert first.status_code == 200, first.text
            first_id = first.json()["request_id"]
            assert str(UUID(first_id)) == first_id
            assert provider.requests[0].model == first_assignment["concrete_model"]

            # Capture and read while the old assignment is still current.
            first_item = read_item(client, first_id)
            assert first_item["requested_assignment"]["model"] == first_assignment["concrete_model"]

            # Consumers must get the same evidence-state rules from live OpenAPI.
            runtime = client.get("/openapi.json").json()
            response_schema = runtime["paths"]["/v1/usage/requests"]["get"]["responses"]["200"][
                "content"
            ]["application/json"]["schema"]
            validator = Draft202012Validator(
                {**response_schema, "components": runtime["components"]}
            )
            actual = {"filter": {"request_id": first_id}, "items": [first_item]}
            validator.validate(actual)
            contradictions = {}
            for status in ("available", "legacy", "unavailable"):
                invalid = deepcopy(actual)
                invalid["items"][0]["attribution_status"] = status
                contradictions[status] = invalid
            invalid = deepcopy(actual)
            invalid["items"][0]["credited_model"] = {
                "availability": "available",
                "value": first_assignment["concrete_model"],
            }
            invalid["items"][0]["credited_provider"] = {
                "availability": "available",
                "value": first_assignment["inference_provider"],
            }
            contradictions["partial-all-credit"] = invalid
            accepted = [name for name, value in contradictions.items() if validator.is_valid(value)]
            assert not accepted, f"Live OpenAPI accepted contradictory evidence: {accepted}"

            changed = client.put(
                "/v1/model-aliases/triage-agent/assignment",
                headers=auth(ADMIN),
                json={
                    "concrete_model": replacement["concrete_model"],
                    "router": replacement["router"],
                    "inference_provider": replacement["inference_provider"],
                    "expected_updated_at": first_assignment["updated_at"],
                },
            )
            assert changed.status_code == 200, changed.text
            # If reads re-resolve aliases, this reread changes or fails these checks.
            assert read_item(client, first_id) == first_item

            second = client.post(
                "/v1/responses",
                headers=auth(CONSUMER),
                json={"model": "triage-agent", "input": PROMPT},
            )
            assert second.status_code == 200, second.text
            second_id = second.json()["request_id"]
            assert provider.requests[1].model == replacement["concrete_model"]
            second_item = read_item(client, second_id)
            assert second_item["requested_assignment"]["model"] == replacement["concrete_model"]
            assert second_item["requested_assignment"]["router"] == replacement["router"]
            validator.validate({"filter": {"request_id": second_id}, "items": [second_item]})
            assert first_item["requested_assignment"] != second_item["requested_assignment"]
            assert first_item["attribution_status"] in {"available", "partial"}
            assert first_item["credited_model"] == {"availability": "unavailable", "value": None}
            assert first_item["credited_provider"] == {"availability": "unavailable", "value": None}
            assert first_item["consumption"] == CONSUMPTION.model_dump(mode="json")
            assert first_item["navigation"] == {"status": "unsupported"}
            assert PROMPT not in repr(first_item) and OUTPUT not in repr(first_item)
            assert ADMIN not in repr(first_item) and AUDIT_KEY not in repr(first_item)
            assert "hmac" not in repr(first_item).lower()
            artifact = {
                "scenario": "issue-454-historical-assignment-reassignment",
                "provider": "controlled-test-double",
                "first_request_id": first_id,
                "first_requested_model": first_item["requested_assignment"]["model"],
                "second_request_id": second_id,
                "second_requested_model": second_item["requested_assignment"]["model"],
                "reread_first_unchanged": True,
                "content_or_credentials_included": False,
            }
        finally:
            # Restore seeded shared state even if the expected RED assertion fails.
            current = client.get("/v1/model-aliases/triage-agent", headers=auth(ADMIN))
            if (
                current.status_code == 200
                and current.json()["concrete_model"] != first_assignment["concrete_model"]
            ):
                restored = client.put(
                    "/v1/model-aliases/triage-agent/assignment",
                    headers=auth(ADMIN),
                    json={
                        "concrete_model": first_assignment["concrete_model"],
                        "router": first_assignment["router"],
                        "inference_provider": first_assignment["inference_provider"],
                        "expected_updated_at": current.json()["updated_at"],
                    },
                )
                assert restored.status_code == 200, restored.text
    if artifact:
        Path("/tmp/issue454-attribution-artifact.json").write_text(
            json.dumps(artifact, sort_keys=True, indent=2) + "\n"
        )
