import asyncio
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
            "principals, alembic_version CASCADE"
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
):
    settings = Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY)
    application = create_application(settings, llm_provider=provider, audit_store=audit_store)
    provider.application = application
    headers = {"Authorization": f"Bearer {KEYS[principal]}"} if principal else {}
    with TestClient(application) as client:
        return client.post("/v1/responses", headers=headers, json=body)


def latest_events() -> list[tuple]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT stage,response_status,latency_ms,identity,routing,"
            "policy_decision,correlation,to_jsonb(audit_events) "
            "FROM audit_events ORDER BY occurred_at DESC,event_id DESC LIMIT 1"
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
