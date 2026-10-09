"""HTTP/provider evidence acceptance for historical request attribution."""

import asyncio
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from issue454_support import (
    ADMIN,
    AUDIT_KEY,
    CONSUMER,
    CONSUMPTION,
    OUTPUT,
    PROMPT,
    ControlledProvider,
    expected_assignment,
    historical_response_event,
    persist_audit_events,
    read_item,
    record_artifact,
)
from issue454_support import (
    DATABASE_URL as DATABASE_URL,
)
from issue454_support import (
    auth as auth,
)
from issue454_support import (
    clean_history as clean_history,
)
from issue454_support import migrated_database as migrated_database

from sre_agent.application import create_application
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.responses import PostgresAuditStore
from sre_agent.persistence.database import Database
from sre_agent.settings import Settings


def test_alias_change_while_provider_is_in_flight_keeps_invocation_snapshot() -> None:
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
                result.append(
                    client.post(
                        "/v1/responses",
                        headers=auth(CONSUMER),
                        json={"model": "triage-agent", "input": PROMPT},
                    )
                )
            except BaseException as error:  # propagate worker failures to the test thread
                errors.append(error)

        thread = threading.Thread(target=invoke)
        thread.start()
        try:
            assert entered.wait(timeout=5), "provider invocation was not reached"
            assert provider.requests[0].model == first_assignment["concrete_model"]
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
            release.set()
            thread.join(timeout=10)
            assert not thread.is_alive() and not errors
            response = result[0]
            assert response.status_code == 200, response.text
            item = read_item(client, response.json()["request_id"])
            assert item["requested_assignment"] == expected_assignment(first_assignment)
            assert item["requested_assignment"]["model"] != replacement["concrete_model"]
            record_artifact(
                "alias-race",
                {
                    "request_id": item["request_id"],
                    "historical_assignment": item["requested_assignment"],
                    "current_model": changed.json()["concrete_model"],
                },
            )
        finally:
            release.set()
            thread.join(timeout=10)
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


@pytest.mark.parametrize(
    "empty_output, valid_model", [(False, True), (True, True), (False, False)]
)
def test_canonical_openrouter_evidence_survives_http_persistence_and_read(
    empty_output: bool, valid_model: bool,
) -> None:
    """Controlled OpenRouter HTTP metadata flows through DB into the request read."""
    requested = "openai/gpt-4o-mini"
    credited = "openai/gpt-4o-mini-20260915" if valid_model else "invalid canonical model"
    secret = "test-only-openrouter-credential"

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = {
                "id": "gen-issue454-001",
                "model": requested,
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": OUTPUT}],
                    }
                ],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 7,
                    "total_tokens": 12,
                    "cost": "0.0012300",
                },
                "created_at": 1789048800,
                "openrouter_metadata": {
                    "requested": requested,
                    "strategy": "direct",
                    "attempt": 1,
                    "endpoints": {
                        "total": 1,
                        "available": [
                            {
                                "provider": "OpenAI",
                                "model": credited,
                                "selected": True,
                            }
                        ],
                    },
                    "attempts": [{"provider": "OpenAI", "model": credited, "status": 200}],
                },
            }
            if empty_output:
                body["output"] = []
            return httpx.Response(200, json=body)
        assert request.url.path == f"/api/v1/models/{requested}/endpoints"
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": requested,
                    "endpoints": [
                        {
                            "model_id": requested,
                            "provider_name": "OpenAI",
                            "tag": "openai",
                            "name": f"OpenAI | {credited}",
                        }
                    ],
                }
            },
        )

    transport = httpx.MockTransport(respond)
    upstream = httpx.AsyncClient(transport=transport, base_url="https://openrouter.test")
    provider = OpenRouterProvider(upstream, api_key=secret)
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/responses",
                headers=auth(CONSUMER),
                json={"model": "triage-agent", "input": PROMPT},
            )
            assert created.status_code == (502 if empty_output or not valid_model else 200), created.text
            request_id = created.json()["request_id"]
            # Public response keeps requested model identity; credit is separate evidence.
            if empty_output or not valid_model:
                assert created.json()["error"]["code"] == (
                    "upstream_invalid_response" if valid_model else "provider_evidence_invalid"
                )
            else:
                assert created.json()["model"] == requested
            item = read_item(client, request_id)
            assert item["requested_assignment"]["model"] == requested
            assert item["credited_model"] == (
                {"availability": "available", "value": credited}
                if valid_model
                else {"availability": "unavailable", "value": None}
            )
            assert item["credited_provider"] == (
                {"availability": "available", "value": "openai"}
                if valid_model
                else {"availability": "unavailable", "value": None}
            )
            assert item["attribution_status"] == ("available" if valid_model else "partial")
            assert item["consumption"] == CONSUMPTION.model_dump(mode="json")
            assert (
                secret not in repr(item) and OUTPUT not in repr(item) and PROMPT not in repr(item)
            )
            record_artifact(
                "canonical-invalid-model"
                if not valid_model
                else "canonical-empty-output"
                if empty_output
                else "canonical",
                {
                    "http_status": created.status_code,
                    "empty_output": empty_output,
                    "valid_model": valid_model,
                    "request_id": item["request_id"],
                    "requested_model": item["requested_assignment"]["model"],
                    "credited_model": item["credited_model"],
                    "credited_provider": item["credited_provider"],
                },
            )
            Path(
                "/tmp/issue454-canonical-invalid-model-artifact.json"
                if not valid_model
                else "/tmp/issue454-canonical-empty-output-artifact.json"
                if empty_output
                else "/tmp/issue454-canonical-adapter-artifact.json"
            ).write_text(
                json.dumps(
                    {
                        "scenario": "canonical OpenRouter credit survives capture and read",
                        "evidence_kind": "controlled integration",
                        "provider": "OpenRouter adapter/httpx.MockTransport; no live/paid call",
                        "http_status": created.status_code,
                        "empty_output": empty_output,
                        "valid_model": valid_model,
                        "historical_item": item,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    finally:
        asyncio.run(upstream.aclose())


def test_provider_timeout_records_assignment_but_no_credited_identity() -> None:
    provider = ControlledProvider(failure="timeout")
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            headers=auth(CONSUMER),
            json={"model": "triage-agent", "input": PROMPT},
        )
        assert response.status_code == 504
        item = read_item(client, response.json()["request_id"])
        assert item["requested_assignment"]["availability"] == "available"
        assert item["credited_model"] == {"availability": "unavailable", "value": None}
        assert item["credited_provider"] == {"availability": "unavailable", "value": None}
        assert item["attribution_status"] == "partial"
        assert item["consumption"]["availability"] == "unavailable"
        record_artifact(
            "timeout",
            {
                "http_status": response.status_code,
                "attribution_status": item["attribution_status"],
                "credited_model": item["credited_model"],
                "credited_provider": item["credited_provider"],
                "consumption_availability": item["consumption"]["availability"],
            },
        )


def test_legacy_audit_without_snapshot_is_explicitly_legacy() -> None:
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
            "availability": "unavailable",
            "alias": None,
            "model": None,
            "provider": None,
            "router": None,
        }
        assert item["credited_model"] == {"availability": "unavailable", "value": None}
        assert item["credited_provider"] == {"availability": "unavailable", "value": None}
        record_artifact(
            "legacy",
            {
                "request_id": item["request_id"],
                "attribution_status": item["attribution_status"],
                "requested_assignment": item["requested_assignment"],
            },
        )


def test_duplicate_audit_rows_use_earliest_month_at_boundary_once() -> None:
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

        january = client.get("/v1/usage/requests", params={"month": "2000-01"}, headers=auth(ADMIN))
        february = client.get(
            "/v1/usage/requests", params={"month": "2000-02"}, headers=auth(ADMIN)
        )
        assert january.status_code == february.status_code == 200
        assert january.json()["filter"] == {"month": "2000-01"}
        assert len(january.json()["items"]) == 1
        assert january.json()["items"][0]["request_id"] == str(request_id)
        assert january.json()["items"][0]["month"] == "2000-01"
        assert february.json()["items"] == []
        record_artifact(
            "month-boundary",
            {
                "request_id": str(request_id),
                "january_count": len(january.json()["items"]),
                "canonical_month": january.json()["items"][0]["month"],
                "february_count": len(february.json()["items"]),
            },
        )


def test_append_only_injected_store_cannot_accept_invocation_without_snapshot() -> None:
    """Real API/DB must fail closed if its injected store cannot capture atomically."""
    provider = ControlledProvider()
    writes: list[str] = []

    class AppendOnlyStore:
        async def append(self, audit_event) -> None:
            writes.append(str(audit_event.event_id))
            await PostgresAuditStore(injected.state.database.sessions).append(audit_event)

    injected = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY),
        llm_provider=provider,
        audit_store=AppendOnlyStore(),
    )
    with TestClient(injected) as client:
        response = client.post(
            "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
        )
        assert len(provider.requests) == 1
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "audit_unavailable"
        assert set(response.json()) == {"error", "request_id", "retryable"}
        assert PROMPT not in response.text and OUTPUT not in response.text
        assert not writes, "non-atomic response audit must not be accepted on its own"
        with psycopg.connect(DATABASE_URL) as connection:
            counts = {}
            for name, query in (
                ("snapshots", "SELECT count(*) FROM request_attributions WHERE request_id = %s"),
                (
                    "audits",
                    "SELECT count(*) FROM audit_events WHERE correlation->>'request_id' = %s",
                ),
            ):
                count = connection.execute(query, (response.json()["request_id"],)).fetchone()[0]
                assert count == 0
                counts[name] = count
        record_artifact(
            "append-only-store",
            {
                "http_status": response.status_code,
                "error": response.json()["error"]["code"],
                "standalone_writes": len(writes),
                "persisted_counts": counts,
            },
        )
