import asyncio
import logging
import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderFailure, ProviderRequest, ProviderResult
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import GrantRepository, ResourceRepository
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
KEYS = {
    "incident-harness": "sre_inci_0123456789abcdefghijklmnop",
    "restricted-harness": "sre_rest_0123456789abcdefghijklmnop",
}
ENV = {
    "ADMIN_HUMAN_API_KEY": "sre_admn_0123456789abcdefghijklmnop",
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": KEYS["incident-harness"],
    "RESTRICTED_HARNESS_API_KEY": KEYS["restricted-harness"],
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
}
BODY = {"model": "triage-agent", "input": "sensitive incident prompt"}
AUDIT_KEY = "audit-key-must-not-persist"


@pytest.fixture(scope="module", autouse=True)
def responses_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def load() -> None:
        database = Database(DATABASE_URL)
        await seed(database, SeedSettings.from_environment(ENV))
        await database.dispose()

    asyncio.run(load())


class RecordingProvider:
    def __init__(self, failure: str | None = None) -> None:
        self.failure = failure
        self.requests, self.checked_out = [], []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        self.checked_out.append(self.application.state.database.engine.pool.checkedout())
        if self.failure:
            raise ProviderFailure(self.failure)  # type: ignore[arg-type]
        return ProviderResult(
            response_id="resp_12345678",
            model=request.model,
            text="sensitive provider output",
            provider=request.provider,
        )


class FailingAuditStore:
    async def append(self, _event: object) -> None:
        raise RuntimeError("audit unavailable")


def post(
    provider: RecordingProvider,
    principal: str | None,
    body: object = BODY,
    audit_store: object | None = None,
    authorization_key: str | None = None,
):
    settings = Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY)
    application = create_application(settings, llm_provider=provider, audit_store=audit_store)
    provider.application = application
    key = authorization_key or (KEYS[principal] if principal else None)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    with TestClient(application) as client:
        return client.post("/v1/responses", headers=headers, json=body)


def latest_events() -> list[tuple]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT stage,response_status,latency_ms,identity,routing,"
            "policy_decision,correlation,to_jsonb(audit_events) "
            "FROM audit_events ORDER BY occurred_at DESC,event_id DESC LIMIT 1"
        ).fetchall()


def events_for_request(request_id: str) -> list[tuple]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT stage,response_status,latency_ms,identity,routing,"
            "policy_decision,correlation,to_jsonb(audit_events) "
            "FROM audit_events WHERE correlation ->> 'request_id' = %s "
            "ORDER BY occurred_at,event_id",
            (request_id,),
        ).fetchall()


@pytest.mark.parametrize(
    ("body", "principal", "status", "stage"),
    [
        (BODY | {"provider": "evil"}, "incident-harness", 422, "validation"),
        (BODY, None, 401, "authentication"),
    ],
)
def test_validation_and_authentication_fail_before_upstream(
    body: object, principal: str | None, status: int, stage: str
) -> None:
    provider = RecordingProvider()
    response = post(provider, principal, body)
    event = latest_events()[0]
    assert response.status_code == status
    assert event[:2] == (stage, status) and provider.requests == []


@pytest.mark.parametrize(
    ("model", "principal", "cause"),
    [
        ("triage-agent", "restricted-harness", "grant_not_applicable"),
        ("missing-agent", "incident-harness", "resource_missing"),
    ],
)
def test_deny_and_missing_resources_are_indistinguishable_without_routing(
    model: str, principal: str, cause: str
) -> None:
    provider = RecordingProvider()
    response = post(provider, principal, BODY | {"model": model})
    event = latest_events()[0]
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "resource_unavailable"
    assert event[0:2] == ("authorization", 403) and event[4] is None and not provider.requests
    assert event[7]["authorization_denial_cause"] == cause
    assert "authorization_denial_cause" not in response.text


def test_denial_never_resolves_an_assignment(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unexpected_assignment(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("assignment resolution must follow authorization allow")

    monkeypatch.setattr(ResourceRepository, "resolve_assignment", unexpected_assignment)
    response = post(RecordingProvider(), "restricted-harness")

    assert response.status_code == 403


def test_inactive_principal_reaches_the_engine_before_all_authorization_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"resource": 0, "grant": 0, "routing": 0}

    async def resource_read(*_args: object, **_kwargs: object) -> None:
        calls["resource"] += 1

    async def grant_read(*_args: object, **_kwargs: object) -> None:
        calls["grant"] += 1

    async def routing_read(*_args: object, **_kwargs: object) -> None:
        calls["routing"] += 1

    monkeypatch.setattr(ResourceRepository, "authorization_view", resource_read)
    monkeypatch.setattr(GrantRepository, "find_active", grant_read)
    monkeypatch.setattr(ResourceRepository, "resolve_assignment", routing_read)
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE principals SET status = 'inactive' WHERE principal_id = 'incident-harness'"
        )
    try:
        provider = RecordingProvider()
        response = post(provider, "incident-harness")
        event = latest_events()[0]
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                "UPDATE principals SET status = 'active' WHERE principal_id = 'incident-harness'"
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "resource_unavailable"
    assert event[0:2] == ("authorization", 403)
    assert event[7]["authorization_denial_cause"] == "principal_inactive"
    assert calls == {"resource": 0, "grant": 0, "routing": 0}
    assert provider.requests == []


def test_inactive_resource_stops_before_grant_and_routing_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"grant": 0, "routing": 0}

    async def grant_read(*_args: object, **_kwargs: object) -> None:
        calls["grant"] += 1

    async def routing_read(*_args: object, **_kwargs: object) -> None:
        calls["routing"] += 1

    monkeypatch.setattr(GrantRepository, "find_active", grant_read)
    monkeypatch.setattr(ResourceRepository, "resolve_assignment", routing_read)
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE resources SET status = 'inactive' "
            "WHERE resource_type = 'llm_model' AND resource_id = 'triage-agent'"
        )
    try:
        provider = RecordingProvider()
        response = post(provider, "incident-harness")
        event = latest_events()[0]
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                "UPDATE resources SET status = 'active' "
                "WHERE resource_type = 'llm_model' AND resource_id = 'triage-agent'"
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "resource_unavailable"
    assert event[0:2] == ("authorization", 403)
    assert event[7]["authorization_denial_cause"] == "resource_inactive"
    assert calls == {"grant": 0, "routing": 0}
    assert provider.requests == []


INVALID_KEYS = {
    "incident-harness": "sre_inci_attempted_invalid_credential_0123456789",
    "restricted-harness": "sre_rest_attempted_invalid_credential_0123456789",
}

# The attempted identity labels document the caller's claimed credential family only. Invalid
# authentication never resolves a Principal and therefore cannot reach authorization.
CREDENTIAL_MATRIX = [
    pytest.param(
        credential_state,
        attempted_principal,
        alias_exists,
        id=(
            f"credential={credential_state},principal={attempted_principal},"
            f"alias={'existing' if alias_exists else 'missing'}"
        ),
    )
    for credential_state in ("valid", "invalid", "revoked")
    for attempted_principal in ("authorized", "unauthorized")
    for alias_exists in (True, False)
]


def matrix_key(credential_state: str, attempted_principal: str) -> str:
    principal = matrix_principal(attempted_principal)
    return KEYS[principal] if credential_state != "invalid" else INVALID_KEYS[principal]


def matrix_principal(attempted_principal: str) -> str:
    return "incident-harness" if attempted_principal == "authorized" else "restricted-harness"


def matrix_expectation(
    credential_state: str, attempted_principal: str, alias_exists: bool
) -> tuple[int, str, int, dict[str, int]]:
    if credential_state in {"invalid", "revoked"}:
        return 401, "authentication", 0, {"resource": 0, "grant": 0, "routing": 0}
    if attempted_principal == "authorized" and alias_exists:
        return 200, "response", 1, {"resource": 1, "grant": 1, "routing": 1}
    if attempted_principal == "authorized":
        return 403, "authorization", 0, {"resource": 1, "grant": 0, "routing": 0}
    return (
        403,
        "authorization",
        0,
        {
            "resource": 1,
            "grant": 1 if alias_exists else 0,
            "routing": 0,
        },
    )


@pytest.mark.parametrize(
    ("credential_state", "attempted_principal", "alias_exists"), CREDENTIAL_MATRIX
)
def test_public_responses_credential_matrix(
    credential_state: str,
    attempted_principal: str,
    alias_exists: bool,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    calls = {"resource": 0, "grant": 0, "routing": 0}
    original_resource = ResourceRepository.authorization_view
    original_grant = GrantRepository.find_active
    original_routing = ResourceRepository.resolve_assignment

    async def resource_read(repository: ResourceRepository, *args: object) -> object:
        calls["resource"] += 1
        return await original_resource(repository, *args)

    async def grant_read(repository: GrantRepository, *args: object) -> object:
        calls["grant"] += 1
        return await original_grant(repository, *args)

    async def routing_read(repository: ResourceRepository, *args: object) -> object:
        calls["routing"] += 1
        return await original_routing(repository, *args)

    monkeypatch.setattr(ResourceRepository, "authorization_view", resource_read)
    monkeypatch.setattr(GrantRepository, "find_active", grant_read)
    monkeypatch.setattr(ResourceRepository, "resolve_assignment", routing_read)

    principal = matrix_principal(attempted_principal)
    key = matrix_key(credential_state, attempted_principal)
    if credential_state == "revoked":
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                "UPDATE credentials SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP "
                "WHERE credential_id = %s",
                (f"credential-{principal}",),
            )
    try:
        provider = RecordingProvider()
        response = post(
            provider,
            None,
            BODY | {"model": "triage-agent" if alias_exists else "missing-agent"},
            authorization_key=key,
        )
    finally:
        if credential_state == "revoked":
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                connection.execute(
                    "UPDATE credentials SET status = 'active', revoked_at = NULL "
                    "WHERE credential_id = %s",
                    (f"credential-{principal}",),
                )

    expected_status, expected_stage, expected_upstream, expected_calls = matrix_expectation(
        credential_state, attempted_principal, alias_exists
    )
    assert response.status_code == expected_status
    assert len(provider.requests) == expected_upstream
    assert calls == expected_calls
    if expected_status == 200:
        assert response.json()["output"][0]["content"][0]["text"] == "sensitive provider output"
    elif expected_status == 403:
        assert response.json()["error"] == {
            "code": "resource_unavailable",
            "message": "Resource unavailable.",
        }
        assert response.json()["retryable"] is False
    else:
        assert response.json()["error"] == {
            "code": "authentication_failed",
            "message": "Authentication failed.",
        }
        assert response.json()["retryable"] is False

    events = events_for_request(response.json()["request_id"])
    assert len(events) == 1
    event = events[0]
    assert event[:3] == (expected_stage, expected_status, event[2]) and event[2] >= 0
    assert str(event[6]["request_id"]) == response.json()["request_id"]
    assert event[7]["content_state"] == "absent"
    if expected_status == 401:
        assert event[3:6] == (None, None, None)
    elif expected_status == 403:
        expected_cause = "resource_missing" if not alias_exists else "grant_not_applicable"
        assert event[3] and event[4] is None
        assert event[5]["decision"] == "deny"
        assert event[7]["authorization_denial_cause"] == expected_cause
    else:
        assert event[3] and event[4]
        assert event[5]["decision"] == "allow"
        assert event[7]["authorization_denial_cause"] is None

    internal_causes = (
        "authorization_denial_cause",
        "grant_not_applicable",
        "resource_missing",
        "resource_inactive",
        "principal_inactive",
    )
    public_forbidden = (key, BODY["input"], *internal_causes)
    assert all(value not in response.text for value in public_forbidden)
    audit_forbidden = (
        *KEYS.values(),
        *INVALID_KEYS.values(),
        BODY["input"],
        "sensitive provider output",
        AUDIT_KEY,
    )
    assert all(value not in repr(event) for value in audit_forbidden)
    assert all(value not in caplog.text for value in (*audit_forbidden, *internal_causes))


def test_allow_calls_once_outside_transactions_and_commits_protected_readback() -> None:
    provider = RecordingProvider()
    response = post(provider, "incident-harness")
    event = latest_events()[0]
    assert response.status_code == 200
    assert response.json()["output"][0]["content"][0]["text"] == "sensitive provider output"
    assert len(provider.requests) == 1 and provider.checked_out == [0]
    assert event[0:3] == ("response", 200, event[2]) and event[2] >= 0
    assert event[3] and event[4] and event[5]["decision"] == "allow"
    assert str(event[6]["request_id"]) == response.json()["request_id"]
    forbidden = (*KEYS.values(), *BODY.values(), "sensitive provider output", AUDIT_KEY)
    assert all(value not in repr(event) for value in forbidden)


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        ("evidence_invalid", 502, "provider_evidence_invalid"),
        ("invalid_response", 502, "upstream_invalid_response"),
        ("timeout", 504, "upstream_timeout"),
        ("unavailable", 503, "upstream_unavailable"),
    ],
)
def test_provider_failures_are_normalized_without_fallback(
    failure: str, status: int, code: str
) -> None:
    provider = RecordingProvider(failure)
    response = post(provider, "incident-harness")
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert len(provider.requests) == 1 and latest_events()[0][0] == "upstream"


@pytest.mark.parametrize("principal", ["incident-harness", "restricted-harness"])
def test_audit_commit_failure_suppresses_success_and_denial(principal: str) -> None:
    provider = RecordingProvider()
    response = post(provider, principal, audit_store=FailingAuditStore())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "audit_unavailable"
    assert len(provider.requests) == (1 if principal == "incident-harness" else 0)
