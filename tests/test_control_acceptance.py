"""Real HTTP acceptance evidence for issue #147's eight control routes."""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.jsonschema import DRAFT202012
from sqlalchemy.exc import StatementError

from sre_agent.application import create_application
from sre_agent.control.service import RotationIssuanceFailure
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "CONTROL_ACCEPTANCE_DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"),
)
AUDIT_KEY = "issue147-acceptance-audit-key"
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
RELEASE = Path(__file__).parents[1] / "schemas/releases/2.0.0/json-schema"


@pytest.fixture(scope="module", autouse=True)
def migrated_acceptance_database() -> None:
    """Use only the dedicated database, never another test suite's database."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            assert await seed(database, SeedSettings.from_environment(SEED_ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


@pytest.fixture
def client() -> TestClient:
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def canonical() -> dict[str, Draft202012Validator]:
    documents = [json.loads(path.read_text()) for path in RELEASE.rglob("*.json")]
    registry = Registry().with_resources(
        (document["$id"], DRAFT202012.create_resource(document))
        for document in documents
        if "$id" in document
    )

    def validator(name: str) -> Draft202012Validator:
        document = next(item for item in documents if item.get("title") == name)
        return Draft202012Validator(document, registry=registry, format_checker=FormatChecker())

    return {
        "principal": validator("Principal"),
        "issuance": validator("CredentialIssuance"),
        "rotation": validator("CredentialRotation"),
        "list": validator("ListEnvelope"),
        "error": validator("ErrorEnvelope"),
    }


def headers(key: str = ADMIN_KEY, idempotency_key: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {key}"}
    if idempotency_key:
        result["Idempotency-Key"] = idempotency_key
    return result


def principal_body(principal_id: str) -> dict[str, str]:
    return {"principal_id": principal_id, "kind": "human", "display_name": principal_id}


def assert_valid(validator: Draft202012Validator, payload: object) -> None:
    assert not list(validator.iter_errors(payload)), payload


def audit_row(request_id: str) -> tuple[object, ...]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT authorization_denial_cause, response_status, identity, resource, "
            "policy_decision FROM audit_events WHERE correlation ->> 'request_id' = %s",
            (request_id,),
        ).fetchone()
    assert row is not None
    return row


def credential_count(principal_id: str) -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT count(*) FROM credentials WHERE principal_id = %s", (principal_id,)
        ).fetchone()[0]


def latest_rotation_audit() -> tuple[object, ...]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT authorization_denial_cause, response_status, identity, resource, "
            "policy_decision FROM audit_events WHERE operation = 'credentials.rotate' "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    return row


def test_rotation_operation_ref_matches_runtime_canonical_envelope() -> None:
    document = yaml.safe_load((RELEASE.parent / "openapi/control-plane.yaml").read_text())
    response_schema = document["paths"]["/v1/credentials/{id}/rotation"]["post"]["responses"][
        "201"
    ]["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "urn:sre-agent:schema:credential-rotation:2.0.0"}


def test_all_eight_routes_with_replays_expiry_and_revocation(
    client: TestClient, canonical: dict[str, Draft202012Validator]
) -> None:
    created = client.post(
        "/v1/principals",
        json=principal_body("route-human"),
        headers=headers(idempotency_key="create-route-human"),
    )
    assert created.status_code == 201
    route_principal = created.json()
    assert_valid(canonical["principal"], route_principal)
    assert client.get("/v1/principals", headers=headers()).status_code == 200
    listed = client.get("/v1/principals", headers=headers()).json()
    assert_valid(canonical["list"], listed)
    assert "route-human" in {item["principal_id"] for item in listed["items"]}
    fetched = client.get("/v1/principals/route-human", headers=headers())
    assert fetched.status_code == 200
    assert_valid(canonical["principal"], fetched.json())

    missing = client.put(
        "/v1/principals/route-human/status", json={"status": "inactive"}, headers=headers()
    )
    assert missing.status_code == 422
    assert_valid(canonical["error"], missing.json())
    changed = client.put(
        "/v1/principals/route-human/status",
        json={"status": "inactive", "expected_updated_at": route_principal["updated_at"]},
        headers=headers(),
    )
    assert changed.status_code == 200 and changed.json()["status"] == "inactive"
    assert_valid(canonical["principal"], changed.json())
    stale = client.put(
        "/v1/principals/route-human/status",
        json={"status": "active", "expected_updated_at": route_principal["updated_at"]},
        headers=headers(),
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "status_conflict"

    credential_principal = client.post(
        "/v1/principals",
        json=principal_body("credential-human"),
        headers=headers(idempotency_key="create-credential-human"),
    )
    assert credential_principal.status_code == 201
    old_expiry, new_expiry = "2031-01-02T03:04:05Z", "2032-01-02T03:04:05Z"
    issued = client.post(
        "/v1/principals/credential-human/credentials",
        json={"expires_at": old_expiry},
        headers=headers(idempotency_key="issue-credential-human"),
    )
    assert issued.status_code == 201
    first = issued.json()
    assert first["secret_revealed"] is True and first["replaced_credential_id"] is None
    assert first["credential"]["expires_at"] == old_expiry and first["key"].startswith("sre_")
    assert_valid(canonical["issuance"], first)
    replay = client.post(
        "/v1/principals/credential-human/credentials",
        json={"expires_at": old_expiry},
        headers=headers(idempotency_key="issue-credential-human"),
    )
    assert replay.status_code == 201 and replay.json()["secret_revealed"] is False
    assert "key" not in replay.json() and replay.json()["credential"] == first["credential"]
    assert_valid(canonical["issuance"], replay.json())
    credentials = client.get("/v1/principals/credential-human/credentials", headers=headers())
    assert credentials.status_code == 200 and first["key"] not in credentials.text
    assert_valid(canonical["list"], credentials.json())

    rotation = client.post(
        f"/v1/credentials/{first['credential']['credential_id']}/rotation",
        json={"expires_at": new_expiry},
        headers=headers(idempotency_key="rotate-credential-human"),
    )
    assert rotation.status_code == 201
    first_rotation = rotation.json()
    replacement = first_rotation["issuance"]
    assert first_rotation["old_credential"]["expires_at"] == old_expiry
    assert replacement["credential"]["expires_at"] == new_expiry
    assert replacement["replaced_credential_id"] == first["credential"]["credential_id"]
    assert replacement["secret_revealed"] is True and replacement["key"].startswith("sre_")
    assert_valid(canonical["rotation"], first_rotation)
    rotation_replay = client.post(
        f"/v1/credentials/{first['credential']['credential_id']}/rotation",
        json={"expires_at": new_expiry},
        headers=headers(idempotency_key="rotate-credential-human"),
    )
    assert rotation_replay.status_code == 201
    replay_rotation = rotation_replay.json()
    assert replay_rotation["replayed"] is True and "key" not in replay_rotation["issuance"]
    assert replay_rotation["issuance"]["secret_revealed"] is False
    assert_valid(canonical["rotation"], replay_rotation)
    assert client.get("/v1/principals", headers=headers(first["key"])).status_code == 401

    racing = client.post(
        "/v1/principals/credential-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-racing-credential"),
    ).json()["credential"]["credential_id"]
    before_race = credential_count("credential-human")

    def rotate_once(key: str) -> int:
        app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
        with TestClient(app, raise_server_exceptions=False) as race_client:
            return race_client.post(
                f"/v1/credentials/{racing}/rotation",
                json={},
                headers=headers(idempotency_key=key),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        racing_statuses = list(
            executor.map(rotate_once, ("race-rotation-key-1", "race-rotation-key-2"))
        )
    assert sorted(racing_statuses) == [201, 409]
    assert credential_count("credential-human") == before_race + 1

    replacement_id = replacement["credential"]["credential_id"]
    assert client.delete(f"/v1/credentials/{replacement_id}", headers=headers()).status_code == 204
    assert client.delete(f"/v1/credentials/{replacement_id}", headers=headers()).status_code == 204
    assert client.get("/v1/principals", headers=headers(replacement["key"])).status_code == 401
    inactive_rotation = client.post(
        f"/v1/credentials/{replacement_id}/rotation",
        json={},
        headers=headers(idempotency_key="revoked-rotation-key"),
    )
    assert inactive_rotation.status_code == 409
    assert inactive_rotation.json()["result"] == "failure"
    assert inactive_rotation.json()["error_code"] == "credential_inactive"
    assert_valid(canonical["rotation"], inactive_rotation.json())
    assert "key" not in inactive_rotation.text


def test_conflict_inactive_auth_and_hidden_denial_audit(
    client: TestClient, canonical: dict[str, Draft202012Validator]
) -> None:
    key = "conflict-principal-key"
    assert (
        client.post(
            "/v1/principals",
            json=principal_body("conflict-human"),
            headers=headers(idempotency_key=key),
        ).status_code
        == 201
    )
    conflict = client.post(
        "/v1/principals",
        json=principal_body("different-human"),
        headers=headers(idempotency_key=key),
    )
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
    )

    inactive = client.post(
        "/v1/principals",
        json=principal_body("inactive-human"),
        headers=headers(idempotency_key="create-inactive-human"),
    ).json()
    issued = client.post(
        "/v1/principals/inactive-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-inactive-human"),
    ).json()
    assert (
        client.put(
            "/v1/principals/inactive-human/status",
            json={"status": "inactive", "expected_updated_at": inactive["updated_at"]},
            headers=headers(),
        ).status_code
        == 200
    )
    inactive_denial = client.get("/v1/principals", headers=headers(issued["key"]))
    assert inactive_denial.status_code == 404
    inactive_cause, *_ = audit_row(inactive_denial.json()["request_id"])
    assert inactive_cause == "principal_inactive"

    denied_existing = client.get("/v1/principals/admin-human", headers=headers(RESTRICTED_KEY))
    denied_missing = client.get("/v1/principals/not-present-human", headers=headers(RESTRICTED_KEY))
    assert (denied_existing.status_code, denied_missing.status_code) == (404, 404)
    assert denied_existing.json()["error"] == denied_missing.json()["error"]
    assert_valid(canonical["error"], denied_existing.json())
    cause, status, identity, resource, decision = audit_row(denied_existing.json()["request_id"])
    assert cause == "grant_not_applicable" and status == 404
    assert identity is not None and resource["resource_type"] == "administrative_control"
    assert decision["decision"] == "deny"


def test_rotation_issuance_failure_rolls_back_and_audits(
    client: TestClient,
    canonical: dict[str, Draft202012Validator],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        client.post(
            "/v1/principals",
            json=principal_body("failure-human"),
            headers=headers(idempotency_key="create-failure-human"),
        ).status_code
        == 201
    )
    issued = client.post(
        "/v1/principals/failure-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-failure-human"),
    ).json()["credential"]
    before = credential_count("failure-human")

    async def fail_issuance(*_args: object, **_kwargs: object) -> object:
        raise RotationIssuanceFailure("injected acceptance failure")

    monkeypatch.setattr(CredentialRepository, "issue", fail_issuance)
    failed = client.post(
        f"/v1/credentials/{issued['credential_id']}/rotation",
        json={},
        headers=headers(idempotency_key="rotate-failure-human"),
    )
    assert failed.status_code == 409
    failure = failed.json()
    assert failure["result"] == "failure" and failure["error_code"] == "rotation_failed"
    assert failure["replacement_count"] == failure["transition_count"] == 0
    assert_valid(canonical["rotation"], failure)
    assert credential_count("failure-human") == before
    with psycopg.connect(DATABASE_URL) as connection:
        old = connection.execute(
            "SELECT status, revoked_at FROM credentials WHERE credential_id = %s",
            (issued["credential_id"],),
        ).fetchone()
    assert old == ("active", None)
    _, status, identity, resource, decision = latest_rotation_audit()
    assert status == 409 and identity is not None and resource is not None
    assert decision["decision"] == "allow"


def test_credential_issue_dependency_failure_is_sanitized_and_audited(
    client: TestClient,
    canonical: dict[str, Draft202012Validator],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert (
        client.post(
            "/v1/principals",
            json=principal_body("driver-failure-human"),
            headers=headers(idempotency_key="create-driver-failure-human"),
        ).status_code
        == 201
    )
    secret = "scrypt$never-log-driver-detail"

    async def fail_issuance(*_args: object, **_kwargs: object) -> object:
        raise StatementError(
            "credential insert failed",
            "INSERT INTO credentials (key_hash) VALUES (%(key_hash)s)",
            {"key_hash": secret},
            RuntimeError(f"driver detail: {secret}"),
            hide_parameters=True,
        )

    monkeypatch.setattr(CredentialRepository, "issue", fail_issuance)
    failed = client.post(
        "/v1/principals/driver-failure-human/credentials",
        json={},
        headers=headers(idempotency_key="issue-driver-failure-human"),
    )
    assert failed.status_code == 500
    payload = failed.json()
    assert payload["error"]["code"] == "credential_issuance_failed"
    assert payload["retryable"] is True
    assert secret not in failed.text
    assert secret not in caplog.text
    assert_valid(canonical["error"], payload)
    with psycopg.connect(DATABASE_URL) as connection:
        reason, status = connection.execute(
            "SELECT reason_code, response_status FROM audit_events "
            "WHERE correlation ->> 'request_id' = %s",
            (payload["request_id"],),
        ).fetchone()
    assert (reason, status) == ("upstream_failed", 500)


def test_audit_append_failure_suppresses_ordinary_secret(
    canonical: dict[str, Draft202012Validator],
) -> None:
    class RejectingAudit:
        async def append(self, _event: object) -> None:
            raise RuntimeError("intentional acceptance audit rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/v1/principals/demo-human/credentials",
            json={},
            headers=headers(idempotency_key="audit-failure-issuance"),
        )
    assert response.status_code == 503 and response.json()["error"]["code"] == "audit_unavailable"
    assert "key" not in response.json() and "sre_" not in response.text
    assert_valid(canonical["error"], response.json())
