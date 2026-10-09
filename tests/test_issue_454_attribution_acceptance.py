"""Issue #454 E2E acceptance for immutable historical request attribution.

Failure modes this test must detect before implementation:
- alias reassignment makes an earlier request appear to have used the new model;
- the read reconstructs history from the current alias instead of persisted evidence;
- requested routing is mislabeled as provider-credited canonical routing;
- consumption is recomputed, omitted, or duplicated while projecting attribution;
- authentication/authorization or malformed filters reveal partial request data;
- prompts, provider output, API keys, or HMAC references leak into the projection;
- read attempts create attribution evidence or return a success-shaped outage.

These scenarios run the real FastAPI app and isolated PostgreSQL with a deterministic
provider double. The provider double is explicitly controlled test evidence, not a
live/paid OpenRouter call. Successful historical reads write a sanitized repeatable
JSON artifact for inspection.
"""

import asyncio
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import event

from sre_agent.application import create_application
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.providers import ProviderFailure, ProviderRequest, ProviderResult
from sre_agent.gateway.responses import PostgresAuditStore
from sre_agent.governance.dto import (
    Consumption,
    ModelAlias,
    PolicyDecision,
    Principal,
    PrincipalContext,
    PricingContext,
)
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
AUDIT_KEY = "issue454-attribution-audit-key"
ADMIN = "sre_admn_0123456789abcdefghijklmnop"
CONSUMER = "sre_inci_0123456789abcdefghijklmnop"
RESTRICTED = "sre_rest_0123456789abcdefghijklmnop"
ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": CONSUMER,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
PROMPT = "private attribution acceptance prompt"
OUTPUT = "private attribution acceptance output"
CONSUMPTION = Consumption(
    availability="complete",
    source="openrouter",
    input_tokens=5,
    output_tokens=7,
    total_tokens=12,
    billed_usd="0.0012300",
    currency="USD",
    precision="exact",
    pricing_context=PricingContext(
        observed_at=datetime(2026, 9, 10, 14, tzinfo=UTC),
        price_version="openrouter:2026-09-10T14:00:00Z",
    ),
)


class ControlledProvider:
    def __init__(
        self, failure: str | None = None, gate: threading.Event | None = None,
        entered: threading.Event | None = None,
    ) -> None:
        self.requests: list[ProviderRequest] = []
        self.failure = failure
        self.gate, self.entered = gate, entered

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.entered is not None:
            self.entered.set()
        if self.gate is not None:
            await asyncio.to_thread(self.gate.wait, 10)
        if self.failure:
            raise ProviderFailure(self.failure)
        return ProviderResult(
            response_id=f"resp_issue454_{len(self.requests):08d}",
            model=request.model,
            text=OUTPUT,
            provider=request.provider,
            consumption=CONSUMPTION,
        )


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS request_attributions, consumption_limit_policies, bok_section_chunks, "
            "bok_documents, bok_collection_versions, audit_events, skill_versions, grants, "
            "credentials, resources, alert_triage, mcp_tools, mcp_servers, principals, "
            "idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            await seed(database, SeedSettings.from_environment(ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


@pytest.fixture(autouse=True)
def clean_history():
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        has_snapshot_table = connection.execute(
            "SELECT to_regclass('public.request_attributions') IS NOT NULL"
        ).fetchone()[0]
        if has_snapshot_table:
            connection.execute("TRUNCATE TABLE audit_events, request_attributions CASCADE")
        else:
            connection.execute("TRUNCATE TABLE audit_events")
    yield


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def read_item(client: TestClient, request_id: str) -> dict[str, object]:
    response = client.get(
        "/v1/usage/requests", params={"request_id": request_id}, headers=auth(ADMIN)
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"filter", "items"}
    assert response.json()["filter"] == {"request_id": request_id}
    assert len(response.json()["items"]) == 1
    return response.json()["items"][0]


def historical_response_event(request_id: UUID, occurred_at: datetime):
    """Build a closed valid response audit event as legacy persisted history."""
    principal = Principal(
        principal_id="issue454-harness",
        kind="agent",
        display_name="Issue 454 acceptance harness",
        status="active",
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    return AuditProjector(AUDIT_KEY.encode()).event(
        request_id=request_id,
        status=200,
        latency_ms=1,
        stage="response",
        context=PrincipalContext(
            principal=principal,
            credential_id="issue454-credential",
            authenticated_at=occurred_at,
        ),
        alias="triage-agent",
        decision=PolicyDecision(
            decision="allow", reason_code="grant_matched", policy_id="issue454-grant"
        ),
        assignment=ModelAlias(
            model_alias_id="issue454-triage-alias",
            alias="triage-agent",
            concrete_model="openai/gpt-4o-mini",
            router="openrouter",
            inference_provider="openai",
            status="active",
        ),
        consumption=CONSUMPTION,
    ).model_copy(update={"occurred_at": occurred_at})


def test_historical_assignment_survives_real_alias_reassignment(
    migrated_database: Database,
) -> None:
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
        assert first_assignment["concrete_model"] != replacement["concrete_model"]
        try:
            first = client.post(
                "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
            )
            assert first.status_code == 200, first.text
            first_id = first.json()["request_id"]
            assert str(UUID(first_id)) == first_id
            assert provider.requests[0].model == first_assignment["concrete_model"]

            # Capture and read while the old assignment is still current.
            first_item = read_item(client, first_id)
            assert first_item["requested_assignment"]["model"] == first_assignment["concrete_model"]

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
                "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
            )
            assert second.status_code == 200, second.text
            second_id = second.json()["request_id"]
            assert provider.requests[1].model == replacement["concrete_model"]
            second_item = read_item(client, second_id)
            assert second_item["requested_assignment"]["model"] == replacement["concrete_model"]
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
            if current.status_code == 200 and current.json()["concrete_model"] != first_assignment["concrete_model"]:
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


def test_alias_change_while_provider_is_in_flight_keeps_invocation_snapshot(
    migrated_database: Database,
) -> None:
    release, entered = threading.Event(), threading.Event()
    provider = ControlledProvider(gate=release, entered=entered)
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app) as client:
        first_assignment = client.get("/v1/model-aliases/triage-agent", headers=auth(ADMIN)).json()
        replacement = client.get("/v1/model-aliases/remediation-agent", headers=auth(ADMIN)).json()
        result: list[object] = []
        errors: list[BaseException] = []

        def invoke() -> None:
            try:
                result.append(client.post(
                    "/v1/responses", headers=auth(CONSUMER),
                    json={"model": "triage-agent", "input": PROMPT},
                ))
            except BaseException as error:  # propagate worker failures to the test thread
                errors.append(error)

        thread = threading.Thread(target=invoke)
        thread.start()
        assert entered.wait(timeout=5), "provider invocation was not reached"
        assert provider.requests[0].model == first_assignment["concrete_model"]
        try:
            changed = client.put(
                "/v1/model-aliases/triage-agent/assignment", headers=auth(ADMIN),
                json={
                    "concrete_model": replacement["concrete_model"],
                    "router": replacement["router"],
                    "inference_provider": replacement["inference_provider"],
                    "expected_updated_at": first_assignment["updated_at"],
                },
            )
            assert changed.status_code == 200, changed.text
            release.set()
            thread.join(timeout=10)
            assert not thread.is_alive() and not errors
            response = result[0]
            assert response.status_code == 200, response.text
            item = read_item(client, response.json()["request_id"])
            assert item["requested_assignment"]["model"] == first_assignment["concrete_model"]
            assert item["requested_assignment"]["model"] != replacement["concrete_model"]
        finally:
            release.set()
            thread.join(timeout=10)
            current = client.get("/v1/model-aliases/triage-agent", headers=auth(ADMIN))
            if current.status_code == 200 and current.json()["concrete_model"] != first_assignment["concrete_model"]:
                restored = client.put(
                    "/v1/model-aliases/triage-agent/assignment", headers=auth(ADMIN),
                    json={
                        "concrete_model": first_assignment["concrete_model"],
                        "router": first_assignment["router"],
                        "inference_provider": first_assignment["inference_provider"],
                        "expected_updated_at": current.json()["updated_at"],
                    },
                )
                assert restored.status_code == 200, restored.text


def test_canonical_openrouter_evidence_survives_http_persistence_and_read(
    migrated_database: Database,
) -> None:
    """Controlled OpenRouter HTTP metadata flows through DB into the request read."""
    requested = "openai/gpt-4o-mini"
    credited = "openai/gpt-4o-mini-20260915"
    secret = "test-only-openrouter-credential"

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = {
                "id": "gen-issue454-001", "model": requested, "status": "completed",
                "output": [{
                    "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": OUTPUT}],
                }],
                "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12, "cost": "0.0012300"},
                "created_at": 1789048800,
                "openrouter_metadata": {
                    "requested": requested, "strategy": "direct", "attempt": 1,
                    "endpoints": {"total": 1, "available": [{
                        "provider": "OpenAI", "model": credited, "selected": True,
                    }]},
                    "attempts": [{"provider": "OpenAI", "model": credited, "status": 200}],
                },
            }
            return httpx.Response(200, json=body)
        assert request.url.path == f"/api/v1/models/{requested}/endpoints"
        return httpx.Response(200, json={"data": {
            "id": requested, "endpoints": [{
                "model_id": requested, "provider_name": "OpenAI", "tag": "openai",
                "name": f"OpenAI | {credited}",
            }],
        }})

    transport = httpx.MockTransport(respond)
    upstream = httpx.AsyncClient(transport=transport, base_url="https://openrouter.test")
    provider = OpenRouterProvider(upstream, api_key=secret)
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/responses", headers=auth(CONSUMER),
                json={"model": "triage-agent", "input": PROMPT},
            )
            assert created.status_code == 200, created.text
            request_id = created.json()["request_id"]
            # Public response keeps requested model identity; credit is separate evidence.
            assert created.json()["model"] == requested
            item = read_item(client, request_id)
            assert item["requested_assignment"]["model"] == requested
            assert item["credited_model"] == {"availability": "available", "value": credited}
            assert item["credited_provider"] == {"availability": "available", "value": "openai"}
            assert item["attribution_status"] == "available"
            assert item["consumption"] == CONSUMPTION.model_dump(mode="json")
            assert secret not in repr(item) and OUTPUT not in repr(item) and PROMPT not in repr(item)
    finally:
        asyncio.run(upstream.aclose())


def test_provider_timeout_records_assignment_but_no_credited_identity(
    migrated_database: Database,
) -> None:
    provider = ControlledProvider(failure="timeout")
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses", headers=auth(CONSUMER),
            json={"model": "triage-agent", "input": PROMPT},
        )
        assert response.status_code == 504
        item = read_item(client, response.json()["request_id"])
        assert item["requested_assignment"]["availability"] == "available"
        assert item["credited_model"] == {"availability": "unavailable", "value": None}
        assert item["credited_provider"] == {"availability": "unavailable", "value": None}
        assert item["attribution_status"] == "partial"
        assert item["consumption"] is None or item["consumption"]["availability"] == "unavailable"


def test_legacy_audit_without_snapshot_is_explicitly_legacy(
    migrated_database: Database,
) -> None:
    request_id = UUID("00000000-0000-0000-0000-000000004540")
    legacy = historical_response_event(request_id, datetime(2026, 9, 1, tzinfo=UTC))

    async def persist() -> None:
        database = Database(DATABASE_URL)
        try:
            await PostgresAuditStore(database.sessions).append(legacy)
        finally:
            await database.dispose()

    asyncio.run(persist())
    app = create_application(Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY))
    with TestClient(app) as client:
        item = read_item(client, str(request_id))
        assert item["attribution_status"] == "legacy"
        assert item["requested_assignment"] == {
            "availability": "unavailable", "alias": None, "model": None,
            "provider": None, "router": None,
        }
        assert item["credited_model"] == {"availability": "unavailable", "value": None}
        assert item["credited_provider"] == {"availability": "unavailable", "value": None}


def test_request_attribution_read_rejects_unauthorized_and_invalid_filters(
    migrated_database: Database,
) -> None:
    provider = ControlledProvider()
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        for headers, status in (({}, 401), (auth(RESTRICTED), 403)):
            response = client.get(
                "/v1/usage/requests", params={"request_id": "00000000-0000-0000-0000-000000000001"},
                headers=headers,
            )
            assert response.status_code == status
            assert set(response.json()) == {"error", "request_id", "retryable"}
            assert set(response.json()["error"]) == {"code", "message"}
            assert response.json()["error"]["code"] == (
                "authentication_failed" if status == 401 else "resource_unavailable"
            )
            assert str(UUID(response.json()["request_id"])) == response.json()["request_id"]
            assert response.json()["retryable"] is False
            assert "items" not in response.text and "request_count" not in response.text
            assert "triage-agent" not in response.text and ADMIN not in response.text
        for params in (
            {},
            {"request_id": "not-a-uuid"},
            {"request_id": "00000000-0000-0000-0000-000000000001", "month": "2026-09"},
            {"month": "2026-09", "unexpected": "private"},
        ):
            response = client.get("/v1/usage/requests", params=params, headers=auth(ADMIN))
            assert response.status_code == 422
            assert "items" not in response.text
        denied_response = client.post(
            "/v1/responses", headers=auth(RESTRICTED),
            json={"model": "triage-agent", "input": PROMPT},
        )
        assert denied_response.status_code == 403
        assert provider.requests == []
        with psycopg.connect(DATABASE_URL) as connection:
            has_snapshot_table = connection.execute(
                "SELECT to_regclass('public.request_attributions') IS NOT NULL"
            ).fetchone()[0]
            rows = (
                connection.execute("SELECT count(*) FROM request_attributions").fetchone()[0]
                if has_snapshot_table else 0
            )
        assert rows == 0



def persist_audit_events(events: list[object]) -> None:
    async def persist() -> None:
        database = Database(DATABASE_URL)
        try:
            store = PostgresAuditStore(database.sessions)
            for audit_event in events:
                await store.append(audit_event)
        finally:
            await database.dispose()

    asyncio.run(persist())


def test_duplicate_audit_rows_use_earliest_month_at_boundary_once(
    migrated_database: Database,
) -> None:
    """A two-event month boundary produces one item in the canonical UTC month."""
    provider = ControlledProvider()
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
        )
        assert response.status_code == 200, response.text
        request_id = UUID(response.json()["request_id"])
        boundary = datetime(2000, 1, 31, 23, 59, 59, 999999, tzinfo=UTC)
        next_month = datetime(2000, 2, 1, 0, 0, 0, tzinfo=UTC)
        earlier = historical_response_event(request_id, boundary)
        later = historical_response_event(request_id, next_month)
        persist_audit_events([earlier, later])

        january = client.get(
            "/v1/usage/requests", params={"month": "2000-01"}, headers=auth(ADMIN)
        )
        february = client.get(
            "/v1/usage/requests", params={"month": "2000-02"}, headers=auth(ADMIN)
        )
        assert january.status_code == february.status_code == 200
        assert january.json()["filter"] == {"month": "2000-01"}
        assert len(january.json()["items"]) == 1
        assert january.json()["items"][0]["request_id"] == str(request_id)
        assert january.json()["items"][0]["month"] == "2000-01"
        assert february.json()["items"] == []


def test_snapshot_is_append_only_and_audit_failure_rolls_back_response_acceptance(
    migrated_database: Database, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ControlledProvider()
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app) as client:
        success = client.post(
            "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
        )
        assert success.status_code == 200, success.text
        request_id = success.json()["request_id"]
        item = read_item(client, request_id)

        # Storage-level guards, not a mocked repository, must reject mutations.
        with psycopg.connect(DATABASE_URL) as connection, pytest.raises(psycopg.Error):
            connection.execute(
                "UPDATE request_attributions SET request_id = request_id WHERE request_id = %s",
                (request_id,),
            )
        with psycopg.connect(DATABASE_URL) as connection, pytest.raises(psycopg.Error):
            connection.execute(
                "DELETE FROM request_attributions WHERE request_id = %s", (request_id,)
            )
        assert read_item(client, request_id) == item

        from sre_agent.persistence.repositories import AuditRepository

        async def fail_audit_append(*_args: object, **_kwargs: object) -> None:
            raise OSError("synthetic persistence failure")

        monkeypatch.setattr(AuditRepository, "append", fail_audit_append)
        failed = client.post(
            "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
        )
        assert failed.status_code == 503
        assert set(failed.json()) == {"error", "request_id", "retryable"}
        assert PROMPT not in failed.text and OUTPUT not in failed.text
        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute(
                "SELECT count(*) FROM request_attributions WHERE request_id = %s",
                (failed.json()["request_id"],),
            ).fetchone()[0] == 0


def test_persisted_request_read_outage_is_not_successful_empty(
    migrated_database: Database, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ControlledProvider()
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    database = app.state.database

    def fail_snapshot_query(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        if "request_attributions" in statement:
            raise psycopg.OperationalError("controlled read outage")

    event.listen(database.engine.sync_engine, "before_cursor_execute", fail_snapshot_query)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/usage/requests", params={"request_id": "00000000-0000-0000-0000-000000004541"},
                headers=auth(ADMIN),
            )
            assert response.status_code == 503
            assert set(response.json()) == {"error", "request_id", "retryable"}
            assert "items" not in response.text and "request_count" not in response.text
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", fail_snapshot_query)


def test_repeated_selector_and_unknown_query_are_closed_errors(
    migrated_database: Database,
) -> None:
    app = create_application(Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY))
    with TestClient(app) as client:
        repeated = client.get(
            "/v1/usage/requests",
            params=[("request_id", "00000000-0000-0000-0000-000000004542"),
                    ("request_id", "00000000-0000-0000-0000-000000004543")],
            headers=auth(ADMIN),
        )
        unknown = client.get(
            "/v1/usage/requests", params={"request_id": "00000000-0000-0000-0000-000000004542", "trace": "secret"},
            headers=auth(ADMIN),
        )
        assert repeated.status_code == unknown.status_code == 422
        for response in (repeated, unknown):
            assert set(response.json()) == {"error", "request_id", "retryable"}
            assert "items" not in response.text and "trace" not in response.text
