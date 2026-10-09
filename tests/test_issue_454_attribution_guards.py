"""Authorization and persistence guard acceptance for request attribution."""

import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from issue454_support import (
    ADMIN,
    AUDIT_KEY,
    CONSUMER,
    DATABASE_URL,
    OUTPUT,
    PROMPT,
    RESTRICTED,
    ControlledProvider,
    auth,
    read_item,
    record_artifact,
)
from issue454_support import (
    clean_history as clean_history,
)
from issue454_support import migrated_database as migrated_database
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from sqlalchemy import event

from sre_agent.application import create_application
from sre_agent.settings import Settings


def test_request_attribution_read_rejects_unauthorized_and_invalid_filters() -> None:
    provider = ControlledProvider()
    app = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY), llm_provider=provider
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        runtime = client.get("/openapi.json").json()
        error = json.loads(
            Path("schemas/releases/2.8.0/json-schema/http/error-envelope.schema.json").read_text()
        )
        registry = Registry().with_resource(error["$id"], Resource.from_contents(error))
        for path in ("/v1/audit-events", "/v1/usage/requests"):
            denied = client.get(path, params={"request_id": str(UUID(int=1))})
            assert denied.status_code == 401
            schema = runtime["paths"][path]["get"]["responses"]["401"]["content"][
                "application/json"
            ]["schema"]
            Draft202012Validator(schema, registry=registry).validate(denied.json())
        for headers, status in (({}, 401), (auth(RESTRICTED), 403)):
            response = client.get(
                "/v1/usage/requests",
                params={"request_id": "00000000-0000-0000-0000-000000000001"},
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
            "/v1/responses",
            headers=auth(RESTRICTED),
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
                if has_snapshot_table
                else 0
            )
        assert rows == 0
        record_artifact(
            "denied-read",
            {
                "request_status": denied_response.status_code,
                "provider_calls": len(provider.requests),
                "snapshot_count": rows,
            },
        )


def test_snapshot_is_append_only_and_audit_failure_rolls_back_response_acceptance(
    monkeypatch: pytest.MonkeyPatch,
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

        original_append = AuditRepository.append
        appended: list[str] = []

        async def fail_after_audit_append(repository, audit_event) -> None:
            await original_append(repository, audit_event)
            appended.append(str(audit_event.event_id))
            raise OSError("synthetic failure after real audit insert and flush")

        monkeypatch.setattr(AuditRepository, "append", fail_after_audit_append)
        failed = client.post(
            "/v1/responses", headers=auth(CONSUMER), json={"model": "triage-agent", "input": PROMPT}
        )
        assert failed.status_code == 503
        assert appended, "the controlled failure must occur after a real audit insert"
        assert set(failed.json()) == {"error", "request_id", "retryable"}
        assert PROMPT not in failed.text and OUTPUT not in failed.text
        with psycopg.connect(DATABASE_URL) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM audit_events WHERE event_id = ANY(%s)", (appended,)
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM request_attributions WHERE request_id = %s",
                    (failed.json()["request_id"],),
                ).fetchone()[0]
                == 0
            )
            audit_count = connection.execute(
                "SELECT count(*) FROM audit_events WHERE event_id = ANY(%s)", (appended,)
            ).fetchone()[0]
            snapshot_count = connection.execute(
                "SELECT count(*) FROM request_attributions WHERE request_id = %s",
                (failed.json()["request_id"],),
            ).fetchone()[0]
        record_artifact(
            "post-insert-rollback",
            {
                "failure_status": failed.status_code,
                "inserted_before_failure": len(appended),
                "audit_survivors": audit_count,
                "snapshot_survivors": snapshot_count,
                "historical_item_after_rejected_mutations": item["requested_assignment"],
            },
        )


def test_persisted_request_read_outage_is_not_successful_empty(
    monkeypatch: pytest.MonkeyPatch,
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
                "/v1/usage/requests",
                params={"request_id": "00000000-0000-0000-0000-000000004541"},
                headers=auth(ADMIN),
            )
            assert response.status_code == 503
            assert set(response.json()) == {"error", "request_id", "retryable"}
            assert "items" not in response.text and "request_count" not in response.text
            record_artifact(
                "storage-outage",
                {"http_status": response.status_code, "error": response.json()["error"]["code"]},
            )
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", fail_snapshot_query)


def test_repeated_selector_and_unknown_query_are_closed_errors() -> None:
    app = create_application(Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY))
    with TestClient(app) as client:
        repeated = client.get(
            "/v1/usage/requests",
            params=[
                ("request_id", "00000000-0000-0000-0000-000000004542"),
                ("request_id", "00000000-0000-0000-0000-000000004543"),
            ],
            headers=auth(ADMIN),
        )
        unknown = client.get(
            "/v1/usage/requests",
            params={"request_id": "00000000-0000-0000-0000-000000004542", "trace": "secret"},
            headers=auth(ADMIN),
        )
        body = client.request(
            "GET",
            "/v1/usage/requests",
            headers=auth(ADMIN),
            params={"request_id": "00000000-0000-0000-0000-000000004542"},
            json={"unsupported": "synthetic-read-content"},
        )
        assert repeated.status_code == unknown.status_code == body.status_code == 422
        for response in (repeated, unknown, body):
            assert set(response.json()) == {"error", "request_id", "retryable"}
            assert "items" not in response.text and "trace" not in response.text
        record_artifact(
            "closed-read",
            {
                "repeated_status": repeated.status_code,
                "unknown_status": unknown.status_code,
                "body_status": body.status_code,
                "body_error": body.json(),
            },
        )
