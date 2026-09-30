"""Real HTTP/PostgreSQL evidence for exact-version Skill access."""

import json

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import ADMIN_KEY, DATABASE_URL, RESTRICTED_KEY, SEED_ENV, headers
from test_control_acceptance import client as _client_fixture  # noqa: F401
from test_control_acceptance import migrated_acceptance_database as _database_fixture  # noqa: F401

from sre_agent.gateway.skills import SkillResolutionResponse

INCIDENT_KEY = SEED_ENV["INCIDENT_HARNESS_API_KEY"]


@pytest.fixture
def client(request: pytest.FixtureRequest) -> TestClient:
    return request.getfixturevalue("_client_fixture")


def publish(
    client: TestClient,
    skill_id: str,
    instructions: str,
    dependencies: list[dict[str, str]] | None = None,
) -> None:
    response = client.post(
        "/v1/skills/versions",
        json={
            "skill_id": skill_id,
            "version": "1.0.0",
            "owner_id": "demo-human",
            "manifest": {
                "display_name": "Resolution test Skill",
                "description": "A controlled exact-version resolution fixture.",
                "instructions": instructions,
                "dependencies": dependencies or [],
            },
        },
        headers={**headers(ADMIN_KEY), "Idempotency-Key": f"publish-{skill_id}-331"},
    )
    assert response.status_code == 201


def grant_invoke(skill_id: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO grants "
            "(grant_id, principal_id, action, resource_type, resource_id, effect, status, "
            "created_at) VALUES (%s, 'incident-harness', 'invoke', 'skill', %s, 'allow', "
            "'active', now())",
            (f"grant-resolution-{skill_id}", f"{skill_id}@1.0.0"),
        )


def activate(client: TestClient, skill_id: str, status: str) -> None:
    del client
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE resources SET status=%s WHERE resource_type='skill' AND resource_id=%s",
            (status, f"{skill_id}@1.0.0"),
        )


def test_exact_version_read_authorizes_before_content_and_audits_metadata_only(
    client: TestClient,
) -> None:
    private_instructions = "PRIVATE_SKILL_INSTRUCTIONS_RESOLUTION_331"
    publish(client, "authorized-root-skill", private_instructions)
    publish(client, "inactive-root-skill", "PRIVATE_INACTIVE_SKILL_INSTRUCTIONS_331")
    publish(client, "ungranted-dependency", "PRIVATE_DEPENDENCY_INSTRUCTIONS_331")
    publish(
        client,
        "dependency-bearing-root",
        "PRIVATE_DEPENDENCY_ROOT_INSTRUCTIONS_331",
        dependencies=[{"skill_id": "ungranted-dependency", "version": "1.0.0"}],
    )
    activate(client, "authorized-root-skill", "active")
    grant_invoke("authorized-root-skill")
    activate(client, "inactive-root-skill", "inactive")
    activate(client, "ungranted-dependency", "active")
    activate(client, "dependency-bearing-root", "active")
    grant_invoke("dependency-bearing-root")
    grant_invoke("inactive-root-skill")

    exact = client.get(
        "/v1/skills/authorized-root-skill/1.0.0/resolve", headers=headers(INCIDENT_KEY)
    )
    unauthorized = client.get(
        "/v1/skills/authorized-root-skill/1.0.0/resolve", headers=headers(RESTRICTED_KEY)
    )
    absent = client.get("/v1/skills/absent-root-skill/1.0.0/resolve", headers=headers(INCIDENT_KEY))
    dependency_bearing = client.get(
        "/v1/skills/dependency-bearing-root/1.0.0/resolve", headers=headers(INCIDENT_KEY)
    )
    inactive = client.get(
        "/v1/skills/inactive-root-skill/1.0.0/resolve", headers=headers(INCIDENT_KEY)
    )

    assert exact.status_code == 200, exact.text
    resolved = SkillResolutionResponse.model_validate_json(exact.content)
    assert str(resolved.request_id) == exact.json()["request_id"]
    assert resolved.retryable is False
    schema = client.get("/openapi.json").json()["components"]["schemas"]["SkillResolutionResponse"]
    assert set(schema["properties"]) == {"skill", "request_id", "retryable"}
    assert set(schema["required"]) == {"skill", "request_id", "retryable"}
    assert exact.json()["skill"]["skill_id"] == "authorized-root-skill"
    assert exact.json()["skill"]["version"] == "1.0.0"
    assert exact.json()["skill"]["manifest"]["instructions"] == private_instructions

    expected_error = dict(
        code="resource_not_found", message="The requested resource was not found."
    )
    for denied in (unauthorized, absent, inactive, dependency_bearing):
        assert denied.status_code == 404 and denied.json()["error"] == expected_error
    dependency_body = json.dumps(dependency_bearing.json())
    assert "PRIVATE_DEPENDENCY_ROOT_INSTRUCTIONS_331" not in dependency_body
    assert "PRIVATE_DEPENDENCY_INSTRUCTIONS_331" not in dependency_body
    assert "ungranted-dependency" not in dependency_body

    responses = (exact, unauthorized, absent, inactive, dependency_bearing)
    request_ids = {response.json()["request_id"] for response in responses}
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT operation, action, correlation, identity, resource, content_state, "
            "redacted_content, response_status, outcome, reason_code "
            "FROM audit_events WHERE correlation->>'request_id' = ANY(%s)",
            (list(request_ids),),
        ).fetchall()
    audit_json = json.dumps(rows, default=str)
    assert len(rows) == len(request_ids) == len({row[2]["request_id"] for row in rows})
    assert all(
        row[0:2] == ("skills.resolve", "invoke") and row[5:7] == ("absent", None) for row in rows
    )
    assert all(row[3] is not None and row[4] is not None for row in rows)
    dependency_audit = next(
        row for row in rows if row[2]["request_id"] == dependency_bearing.json()["request_id"]
    )
    assert dependency_audit[7:] == (404, "error", "resource_not_found")
    assert all(
        instruction not in audit_json
        for instruction in (
            private_instructions,
            "PRIVATE_INACTIVE_SKILL_INSTRUCTIONS_331",
            "PRIVATE_DEPENDENCY_ROOT_INSTRUCTIONS_331",
            "PRIVATE_DEPENDENCY_INSTRUCTIONS_331",
        )
    )


def test_unauthenticated_resolution_returns_bearer_challenge(client: TestClient) -> None:
    response = client.get("/v1/skills/authorized-root-skill/1.0.0/resolve")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "skill_id,version,request_id",
    (
        ("Invalid!", "1.0.0", "30000000-0000-4000-8000-000000000001"),
        ("valid-skill-id", "latest", "30000000-0000-4000-8000-000000000002"),
    ),
)
def test_invalid_resolution_paths_return_correlated_audited_422(
    client: TestClient, skill_id: str, version: str, request_id: str
) -> None:
    response = client.get(
        f"/v1/skills/{skill_id}/{version}/resolve",
        headers={**headers(INCIDENT_KEY), "X-Request-ID": request_id},
    )
    assert response.status_code == 422, response.text
    assert response.json()["request_id"] == request_id
    assert response.json()["error"]["code"] == "contract_validation_failed"
    with psycopg.connect(DATABASE_URL) as connection:
        audit = connection.execute(
            "SELECT operation, response_status, outcome, reason_code FROM audit_events "
            "WHERE correlation->>'request_id' = %s",
            (request_id,),
        ).fetchone()
    assert audit == ("skills.resolve", 422, "error", "contract_validation_failed")


def test_resolution_openapi_declares_envelope_and_error_models(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    success_ref = openapi["paths"]["/v1/skills/{skill_id}/{version}/resolve"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    assert set(openapi["components"]["schemas"][success_ref]["properties"]) == {
        "skill",
        "request_id",
        "retryable",
    }
    responses = openapi["paths"]["/v1/skills/{skill_id}/{version}/resolve"]["get"]["responses"]
    assert "422" in responses and "503" in responses
    challenge = responses["401"]["headers"]["WWW-Authenticate"]
    assert challenge["schema"] == {"type": "string"}
    assert challenge["example"] == "Bearer"


def test_persistence_failure_returns_retryable_503_with_audit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sre_agent.persistence import repositories as _repositories

    publish(client, "retryable-root-skill", "PRIVATE_RETRYABLE_331")
    activate(client, "retryable-root-skill", "active")
    grant_invoke("retryable-root-skill")

    async def _raise_get(self, skill_id: str, version: str):  # noqa: ANN001, ANN202
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(_repositories.SkillVersionRepository, "get", _raise_get)
    request_id = "30000000-0000-4000-8000-000000000009"
    response = client.get(
        "/v1/skills/retryable-root-skill/1.0.0/resolve",
        headers={**headers(INCIDENT_KEY), "X-Request-ID": request_id},
    )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "audit_unavailable"
    assert response.json()["request_id"] == request_id
    assert response.json()["retryable"] is True
    with psycopg.connect(DATABASE_URL) as connection:
        audit = connection.execute(
            "SELECT response_status, outcome, reason_code FROM audit_events "
            "WHERE correlation->>'request_id' = %s",
            (request_id,),
        ).fetchone()
    assert audit == (503, "error", "audit_unavailable")
