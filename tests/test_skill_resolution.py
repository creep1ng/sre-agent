"""Real HTTP/PostgreSQL evidence for exact-version Skill access."""

import json

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import ADMIN_KEY, DATABASE_URL, RESTRICTED_KEY, SEED_ENV, headers
from test_control_acceptance import client as _client_fixture  # noqa: F401
from test_control_acceptance import migrated_acceptance_database as _database_fixture  # noqa: F401

from sre_agent.gateway.skills import SkillResolutionResponse
from sre_agent.persistence import repositories

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


def grant_invoke(*skill_ids: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        for skill_id in skill_ids:
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
    assert set(schema["properties"]) == {"skill", "dependencies", "request_id", "retryable"}
    assert set(schema["required"]) == {"skill", "dependencies", "request_id", "retryable"}
    assert exact.json()["skill"]["skill_id"] == "authorized-root-skill"
    assert exact.json()["skill"]["version"] == "1.0.0"
    assert exact.json()["skill"]["manifest"]["instructions"] == private_instructions
    assert exact.json()["dependencies"] == []

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
    assert dependency_audit[7:] == (404, "denied", "no_matching_grant")
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
    ("path", "request_id"),
    (
        ("/v1/skills/INVALID/1.0.0/resolve", "195fa25c-cdd3-4c89-87a6-dd4cf1c79d80"),
        ("/v1/skills/valid-skill/1.0/resolve", "b1eb3959-9358-425b-92dc-c5a6fb239e99"),
        (
            f"/v1/skills/valid-skill/1.0.{'1' * 29}/resolve",
            "e411734b-2ddf-46d5-93cc-655fbca3fa2b",
        ),
    ),
)
def test_malformed_paths_return_correlated_terminal_validation_audit(
    client: TestClient, path: str, request_id: str
) -> None:
    response = client.get(path, headers={"X-Request-ID": request_id})
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT operation, action, stage, response_status, outcome, reason_code, "
            "identity, resource FROM audit_events WHERE correlation->>'request_id'=%s",
            (request_id,),
        ).fetchone()

    body = response.json()
    assert (
        response.status_code,
        body.get("request_id"),
        body.get("retryable"),
        body.get("error", {}).get("code"),
        row,
    ) == (
        422,
        request_id,
        False,
        "contract_validation_failed",
        (
            "skills.resolve",
            "invoke",
            "validation",
            422,
            "error",
            "contract_validation_failed",
            None,
            None,
        ),
    )


def test_resolution_openapi_keeps_bounded_path_patterns(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"][
        "/v1/skills/{skill_id}/{version}/resolve"
    ]["get"]
    patterns = {param["name"]: param["schema"]["pattern"] for param in operation["parameters"]}

    assert patterns == {
        "skill_id": r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$",
        "version": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
    }


def test_direct_dependencies_reuse_verified_context_and_fail_closed_atomically(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_ids = [f"direct-dependency-{index:02d}" for index in range(16)]
    for skill_id in dependency_ids:
        publish(client, skill_id, f"PRIVATE_{skill_id}_331")
        activate(client, skill_id, "active")
    root_id = "sixteen-dependency-root"
    publish(
        client,
        root_id,
        "PRIVATE_ROOT_331",
        dependencies=[{"skill_id": item, "version": "1.0.0"} for item in dependency_ids],
    )
    activate(client, root_id, "active")
    grant_invoke(root_id, *dependency_ids)

    original_verify = repositories.verify_api_key
    scrypt_verifications = 0

    def counted_real_verification(key: str, encoded_hash: str) -> bool:
        nonlocal scrypt_verifications
        scrypt_verifications += 1
        return original_verify(key, encoded_hash)

    monkeypatch.setattr(repositories, "verify_api_key", counted_real_verification)
    response = client.get(f"/v1/skills/{root_id}/1.0.0/resolve", headers=headers(INCIDENT_KEY))
    assert response.status_code == 200, response.text
    assert [item["skill_id"] for item in response.json()["dependencies"]] == dependency_ids
    assert [item["manifest"]["instructions"] for item in response.json()["dependencies"]] == [
        f"PRIVATE_{skill_id}_331" for skill_id in dependency_ids
    ]
    assert scrypt_verifications == 1

    activate(client, dependency_ids[0], "inactive")
    calls_before_inactive = scrypt_verifications
    inactive = client.get(f"/v1/skills/{root_id}/1.0.0/resolve", headers=headers(INCIDENT_KEY))
    assert inactive.status_code == 404
    assert scrypt_verifications - calls_before_inactive == 1
    assert "PRIVATE_ROOT_331" not in inactive.text
    activate(client, dependency_ids[0], "active")

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "DELETE FROM grants WHERE principal_id='incident-harness' AND action='invoke' "
            "AND resource_type='skill' AND resource_id=%s",
            (f"{dependency_ids[-1]}@1.0.0",),
        )
    calls_before_denial = scrypt_verifications
    denied = client.get(f"/v1/skills/{root_id}/1.0.0/resolve", headers=headers(INCIDENT_KEY))
    assert denied.status_code == 404
    assert scrypt_verifications - calls_before_denial == 1
    assert "PRIVATE_ROOT_331" not in denied.text
    assert all(f"PRIVATE_{skill_id}_331" not in denied.text for skill_id in dependency_ids)

    nested_id = "nested-direct-dependency"
    nested_root = "root-with-nested-dependency"
    publish(client, "hidden-transitive-dep", "PRIVATE_TRANSITIVE_331")
    publish(
        client,
        nested_id,
        "PRIVATE_NESTED_331",
        dependencies=[{"skill_id": "hidden-transitive-dep", "version": "1.0.0"}],
    )
    publish(
        client,
        nested_root,
        "PRIVATE_NESTED_ROOT_331",
        dependencies=[{"skill_id": nested_id, "version": "1.0.0"}],
    )
    for skill_id in (nested_id, nested_root, "hidden-transitive-dep"):
        activate(client, skill_id, "active")
    grant_invoke(nested_root, nested_id)
    nested = client.get(f"/v1/skills/{nested_root}/1.0.0/resolve", headers=headers(INCIDENT_KEY))
    assert nested.status_code == 404
    assert "PRIVATE_NESTED_ROOT_331" not in nested.text
    assert "PRIVATE_NESTED_331" not in nested.text
    assert "PRIVATE_TRANSITIVE_331" not in nested.text


def test_resolution_openapi_declares_custom_validation_envelope(client: TestClient) -> None:
    responses = client.get("/openapi.json").json()["paths"][
        "/v1/skills/{skill_id}/{version}/resolve"
    ]["get"]["responses"]
    assert "422" in responses and "503" in responses
    challenge = responses["401"]["headers"]["WWW-Authenticate"]
    assert challenge["schema"] == {"type": "string"}
    assert challenge["example"] == "Bearer"


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
