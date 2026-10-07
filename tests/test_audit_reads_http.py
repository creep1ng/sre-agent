"""Issue #25 B2b: audit HTTP reads over the published 2.3.0 contract."""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from sre_agent.application import create_application
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.audit_reads import AuditReadsService, _valid_event_id, project_metadata
from sre_agent.gateway.responses import PostgresAuditStore
from sre_agent.governance.dto import AuditEvent
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import AuditRepository, GrantRepository
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
HMAC_KEY = b"test-audit-hmac-key-32-bytes!!"
DAY = datetime(2026, 9, 20, tzinfo=UTC)
PROJECTOR = AuditProjector(HMAC_KEY)
BEARERS: dict[str, str] = {}
DIGIT_EVENT_ID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
REDACTION = {
    "policy_version": "redaction-1.0.0",
    "result": "success",
    "source_class": "none",
    "categories": [],
    "match_count": 0,
    "sink_eligible": False,
}
ROOT = Path(__file__).parents[1]


def _ref(domain: str, value: str) -> dict:
    return PROJECTOR.reference(domain, value).model_dump(mode="json")


def make_event(
    number: int,
    *,
    hours: int = 0,
    allowed: bool = True,
    request: int = 51,
    principal: str = "admin-human",
    event_id: UUID | None = None,
) -> AuditEvent:
    # Contract universe: any UUID (digit-leading included) plus cor_ ids.
    return AuditEvent(
        event_id=event_id
        if event_id is not None
        else UUID(int=0xB0000000000000000000000000000000 + number),
        occurred_at=DAY + timedelta(hours=hours),
        operation="responses.create",
        action="invoke",
        stage="authorization",
        outcome="success" if allowed else "denied",
        reason_code="grant_matched" if allowed else "no_matching_grant",
        response_status=200 if allowed else 403,
        retryable=False,
        latency_ms=number,
        correlation={"request_id": UUID(int=0xC0000000000000000000000000000000 + request)},
        identity={
            "principal_ref": _ref("principal", principal),
            "principal_kind": "human",
            "principal_status": "active",
            "credential_ref": _ref("credential", f"credential-{principal}"),
            "authenticated_at": DAY,
        },
        resource={
            "resource_type": "llm_model",
            "resource_ref": _ref("resource", "llm_model/triage-agent"),
        },
        model_alias_ref=_ref("model_alias", "triage-agent"),
        policy_decision={
            "decision": "allow" if allowed else "deny",
            "reason_code": "grant_matched" if allowed else "no_matching_grant",
            **({"grant_ref": _ref("grant", "g")} if allowed else {}),
        },
        routing=None,
        consumption=None,
        untrusted_input=None,
        redaction=REDACTION,
        content_state="absent",
        redacted_content=None,
        authoritative_acceptance="accepted",
        ordinary_result="released",
        exporter_result="not_attempted",
        correction_of_event_id=None,
    )


@pytest.fixture(scope="module", autouse=True)
def audit_http_database() -> None:
    prepare_audit_http_database()


def prepare_audit_http_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
        for (table,) in tables:
            connection.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('admin-human','human','Admin','active',now(),now()),"
            "('bystander-human','human','Bystander','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at,"
            " owner_id, source, source_ref, display_name, visibility, description,"
            " tags) VALUES ('administrative_control','audit','active',now(),"
            " NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> None:
        async with database.transaction() as session:
            from sre_agent.persistence.repositories import CredentialRepository

            admin = await CredentialRepository(session).issue("admin-human")
            bystander = await CredentialRepository(session).issue("bystander-human")
            await GrantRepository(session).create(
                "grant-admin-human-admin-read-audit",
                "admin-human",
                "admin.read",
                "administrative_control",
                "audit",
            )
            repository = AuditRepository(session)
            await repository.append(make_event(101, hours=1))
            await repository.append(make_event(102, hours=2, allowed=False))
            await repository.append(make_event(103, hours=3, request=52))
            await repository.append(make_event(104, hours=4, event_id=UUID(DIGIT_EVENT_ID)))
        BEARERS["admin"] = f"Bearer {admin.key}"
        BEARERS["bystander"] = f"Bearer {bystander.key}"

    import asyncio

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client() -> TestClient:
    settings = Settings(DATABASE_URL, None, 30.0, HMAC_KEY.decode())
    return TestClient(create_application(settings))


def _metadata_validator():
    schemas = {}
    for path in (ROOT / "schemas/releases/2.3.0/json-schema").rglob("*.schema.json"):
        schema = json.loads(path.read_text())
        schemas[schema["$id"]] = schema
    registry = Registry().with_resources(
        [(sid, Resource.from_contents(s)) for sid, s in schemas.items()]
    )
    return Draft202012Validator(
        schemas["urn:sre-agent:schema:audit-event-metadata:2.3.0"],
        registry=registry,
        format_checker=FormatChecker(),
    )


def _resolve_openapi_schema(schema: Any, document: dict[str, Any]) -> Any:
    if isinstance(schema, list):
        return [_resolve_openapi_schema(value, document) for value in schema]
    if not isinstance(schema, dict):
        return schema
    reference = schema.get("$ref")
    if reference is not None:
        prefix = "#/components/schemas/"
        if not reference.startswith(prefix):
            return schema
        target = deepcopy(document["components"]["schemas"][reference.removeprefix(prefix)])
        target.update({key: value for key, value in schema.items() if key != "$ref"})
        return _resolve_openapi_schema(target, document)
    return {
        key: _resolve_openapi_schema(value, document) if isinstance(value, dict | list) else value
        for key, value in schema.items()
    }


def _runtime_audit_metadata_validator(client: TestClient):
    document = client.get("/openapi.json").json()
    detail = document["paths"]["/v1/audit-events/{id}"]["get"]
    schema = detail["responses"]["200"]["content"]["application/json"]["schema"]
    reference = schema.get("$ref")
    if reference is not None and reference.startswith("urn:"):
        schemas = {}
        for path in (ROOT / "schemas/releases/2.7.0/json-schema").rglob("*.schema.json"):
            value = json.loads(path.read_text())
            schemas[value["$id"]] = value
        registry = Registry().with_resources(
            [(schema_id, Resource.from_contents(value)) for schema_id, value in schemas.items()]
        )
        return Draft202012Validator(
            schemas[reference], registry=registry, format_checker=FormatChecker()
        )
    resolved = _resolve_openapi_schema(schema, document)
    return Draft202012Validator(resolved, format_checker=FormatChecker())


def make_non_llm_event(number: int, operation: str) -> AuditEvent:
    event = make_event(number, hours=5 + number % 15)
    values = event.model_dump(mode="python")
    values["operation"] = operation
    values["model_alias_ref"] = None
    values["action"] = {
        "bok.search": "read_metadata",
        "bok.read": "read_metadata",
        "catalog.status.replace": "admin.write",
        "skills.resolve": "invoke",
        "consumption_limits.get": "admin.read",
        "consumption_limits.replace": "admin.write",
    }[operation]
    resource_type = (
        "bok_collection"
        if operation.startswith("bok.")
        else ("skill" if operation == "skills.resolve" else "administrative_control")
    )
    values["resource"] = {
        "resource_type": resource_type,
        "resource_ref": _ref("resource", f"{resource_type}/metadata-schema-{number}"),
    }
    values["routing"] = None
    values["consumption"] = None
    return AuditEvent.model_validate(values)


WINDOW_QS = "from=2026-09-20T00:00:00Z&to=2026-09-21T00:00:00Z"


def test_unauthenticated_and_forbidden() -> None:
    client = _client()
    assert client.get(f"/v1/audit-events?{WINDOW_QS}").status_code == 401
    canonical_request_id = str(UUID(int=0xC0000000000000000000000000000000 + 52)).upper()
    assert (
        client.get("/v1/audit-events", params={"request_id": canonical_request_id}).status_code
        == 401
    )
    bad = client.get(f"/v1/audit-events?{WINDOW_QS}", headers={"Authorization": "Bearer not-a-key"})
    assert bad.status_code == 401
    assert bad.headers["WWW-Authenticate"] == "Bearer"
    denied = client.get(
        f"/v1/audit-events?{WINDOW_QS}", headers={"Authorization": BEARERS["bystander"]}
    )
    assert denied.status_code == 403
    assert (
        client.get(
            "/v1/audit-events",
            params={"request_id": canonical_request_id},
            headers={"Authorization": BEARERS["bystander"]},
        ).status_code
        == 403
    )
    assert "grant_matched" not in denied.text


def test_any_of_forbidden_and_invalid_filters() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["admin"]}
    assert client.get("/v1/audit-events", headers=headers).status_code == 422
    for query in (
        "cursor=abc",
        "page=1",
        "offset=5",
        "content=x",
        "decision=maybe",
        "request_id=nope",
        "principal_id=ABC",
        "from=2026-09-21T00:00:00Z&to=2026-09-20T00:00:00Z",
        "from=2026-09-20T00:00:00&to=2026-09-21T00:00:00Z",
        "limit=0",
        "limit=101",
        "limit=x",
    ):
        response = client.get(f"/v1/audit-events?{query}", headers=headers)
        assert response.status_code == 422, query
    for forbidden in (
        "cursor=abc",
        "page=1",
        "offset=5",
        "continuation_token=abc",
        "next=abc",
        "content=x",
        "raw_content=x",
        "redacted_content=x",
        "include_content=true",
    ):
        query = f"{forbidden}&decision=deny"
        response = client.get(f"/v1/audit-events?{query}", headers=headers)
        assert response.status_code == 422, query
    alone = client.get("/v1/audit-events?from=2026-09-21T00:00:00Z", headers=headers).json()
    assert (alone["limit"], alone["truncated"]) == (100, False)
    lower_bound = datetime(2026, 9, 21, tzinfo=UTC)
    for item in alone["items"]:
        occurred_at = datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00"))
        assert occurred_at >= lower_bound
        AuditEvent.model_validate_json(json.dumps(item))
        assert "redacted_content" not in item


def test_list_filters_default_limit_and_empty() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["admin"]}
    response = client.get(f"/v1/audit-events?{WINDOW_QS}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert (body["limit"], body["truncated"]) == (100, False)
    assert len(body["items"]) == 4
    mine = client.get(
        f"/v1/audit-events?{WINDOW_QS}&principal_id=admin-human", headers=headers
    ).json()
    assert len(mine["items"]) == 4
    denied = client.get(f"/v1/audit-events?{WINDOW_QS}&decision=deny", headers=headers).json()
    assert len(denied["items"]) == 1
    requested = client.get(
        f"/v1/audit-events?request_id={UUID(int=0xC0000000000000000000000000000000 + 52)}",
        headers=headers,
    ).json()
    assert len(requested["items"]) == 1
    requested_uppercase = client.get(
        "/v1/audit-events",
        params={"request_id": str(UUID(int=0xC0000000000000000000000000000000 + 52)).upper()},
        headers=headers,
    ).json()
    assert len(requested_uppercase["items"]) == 1
    empty = client.get(
        "/v1/audit-events?from=2026-09-22T00:00:00Z&to=2026-09-22T01:00:00Z", headers=headers
    ).json()
    assert empty == {"items": [], "limit": 100, "truncated": False}
    for item in body["items"]:
        assert "redacted_content" not in item
    assert "redacted_content" not in response.text


def test_detail_metadata_conforms_and_404() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["admin"]}
    event_id = client.get(f"/v1/audit-events?{WINDOW_QS}", headers=headers).json()["items"][0][
        "event_id"
    ]
    assert client.get(f"/v1/audit-events/{event_id}").status_code == 401
    assert (
        client.get(
            f"/v1/audit-events/{event_id}?raw_content=true",
            headers={"Authorization": BEARERS["bystander"]},
        ).status_code
        == 403
    )
    detail = client.get(f"/v1/audit-events/{event_id}", headers=headers)
    assert detail.status_code == 200
    assert list(_metadata_validator().iter_errors(detail.json())) == []
    assert "redacted_content" not in detail.text
    assert (
        client.get(
            "/v1/audit-events/b0000000-0000-4000-8000-000000000099", headers=headers
        ).status_code
        == 404
    )
    legacy_compact_id = "abcdefabcdefabcdefabcdefabcdefab"
    legacy_missing = client.get(f"/v1/audit-events/{legacy_compact_id}", headers=headers)
    assert legacy_missing.status_code == 404
    _assert_terminal_validation_record(legacy_missing, 404, "authorization")
    assert client.get("/v1/audit-events/NOPE!", headers=headers).status_code == 422

    with psycopg.connect(DATABASE_URL) as connection:
        prior_terminal_ids = {
            row[0]
            for row in connection.execute(
                "SELECT event_id::text FROM audit_events "
                "WHERE operation='audit.project' AND action='read_metadata'"
            ).fetchall()
        }
    uppercase_uuid = client.get(f"/v1/audit-events/{DIGIT_EVENT_ID.upper()}", headers=headers)
    assert uppercase_uuid.status_code == 200, uppercase_uuid.text
    assert uppercase_uuid.json()["event_id"] == DIGIT_EVENT_ID
    assert list(_metadata_validator().iter_errors(uppercase_uuid.json())) == []
    assert "redacted_content" not in uppercase_uuid.text
    with psycopg.connect(DATABASE_URL) as connection:
        terminal_records = {
            event_id: row
            for event_id, row in connection.execute(
                "SELECT event_id::text, to_jsonb(a) FROM audit_events a "
                "WHERE operation='audit.project' AND action='read_metadata'"
            ).fetchall()
        }
    new_terminal_ids = set(terminal_records) - prior_terminal_ids
    assert len(new_terminal_ids) == 1
    terminal = terminal_records[next(iter(new_terminal_ids))]
    assert terminal["response_status"] == 200
    assert terminal["stage"] == "authorization"
    assert terminal["content_state"] == "absent"
    assert terminal["identity"]["principal_ref"] == _ref("principal", "admin-human")
    assert terminal["resource"]["resource_type"] == "administrative_control"
    assert terminal["resource"]["resource_ref"] == _ref("resource", "administrative_control/audit")


def test_mounted_operations_validate_in_list_and_detail_metadata() -> None:
    import asyncio

    operations = (
        "bok.search",
        "bok.read",
        "catalog.status.replace",
        "skills.resolve",
        "consumption_limits.get",
        "consumption_limits.replace",
    )
    events = [
        make_non_llm_event(201 + index, operation) for index, operation in enumerate(operations)
    ]
    database = Database(DATABASE_URL)

    async def append_mounted_operations() -> None:
        async with database.transaction() as session:
            repository = AuditRepository(session)
            for event in events:
                await repository.append(event)

    asyncio.run(append_mounted_operations())
    asyncio.run(database.dispose())

    client = _client()
    validator = _runtime_audit_metadata_validator(client)
    headers = {"Authorization": BEARERS["admin"]}
    listed = client.get(f"/v1/audit-events?{WINDOW_QS}", headers=headers)
    assert listed.status_code == 200, listed.text
    by_id = {item["event_id"]: item for item in listed.json()["items"]}
    for event in events:
        event_id = str(event.event_id)
        assert event_id in by_id
        assert by_id[event_id]["operation"] == event.operation
        validator.validate(by_id[event_id])

        detail = client.get(f"/v1/audit-events/{event_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["operation"] == event.operation
        validator.validate(detail.json())

    # Both event-ID forms accepted by the route remain represented by the
    # runtime-local schema; the published examples remain unchanged.
    projected = project_metadata(events[0].model_dump(mode="json"))
    validator.validate(projected)
    for event_id in (DIGIT_EVENT_ID, "cor_12345678-1234-1234-8234-123456789012"):
        candidate = {**projected, "event_id": event_id}
        assert _valid_event_id(event_id)
        validator.validate(candidate)

    for forbidden in (
        {"redacted_content": {"representation": "fully_redacted"}},
        {"redaction": {**projected["redaction"], "tool_schema_version": "1.0.0"}},
        {
            "policy_decision": {
                **projected["policy_decision"],
                "policy_ref": {"algorithm": "hmac-sha-256"},
            }
        },
    ):
        assert not validator.is_valid({**projected, **forbidden})


def _assert_terminal_validation_record(response, status: int, stage: str) -> None:
    request_id = response.json()["request_id"]
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT to_jsonb(a) FROM audit_events a WHERE operation='audit.project' "
            "AND correlation->>'request_id'=%s",
            (request_id,),
        ).fetchall()
    assert len(rows) == 1
    row = rows[0][0]
    assert row["operation"] == "audit.project"
    assert row["action"] == "read_metadata"
    assert row["response_status"] == status
    assert row["stage"] == stage
    assert row["content_state"] == "absent"
    assert row["correlation"]["request_id"] == request_id


@pytest.mark.parametrize(
    "event_id",
    (
        "3f2504e04f8911d39a0c0305e82c3301",
        "{3f2504e0-4f89-11d3-9a0c-0305e82c3301}",
        "urn:uuid:3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    ),
)
def test_noncanonical_uuid_path_forms_are_audited_validation_errors(event_id: str) -> None:
    response = _client().get(
        f"/v1/audit-events/{event_id}", headers={"Authorization": BEARERS["admin"]}
    )
    assert response.status_code == 422, response.text
    _assert_terminal_validation_record(response, 422, "validation")


@pytest.mark.parametrize(
    "request_id",
    (
        "3f2504e04f8911d39a0c0305e82c3301",
        "{3f2504e0-4f89-11d3-9a0c-0305e82c3301}",
        "urn:uuid:3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    ),
)
def test_noncanonical_request_id_forms_are_audited_validation_errors(
    request_id: str,
) -> None:
    response = _client().get(
        "/v1/audit-events",
        params={"request_id": request_id},
        headers={"Authorization": BEARERS["admin"]},
    )
    assert response.status_code == 422, response.text
    _assert_terminal_validation_record(response, 422, "validation")


@pytest.mark.parametrize("parameter", ("content", "raw_content", "redacted_content"))
def test_detail_content_parameters_are_rejected_and_audited(parameter: str) -> None:
    response = _client().get(
        f"/v1/audit-events/{DIGIT_EVENT_ID}",
        params={parameter: "true"},
        headers={"Authorization": BEARERS["admin"]},
    )
    assert response.status_code == 422, response.text
    assert "redacted_content" not in response.text
    assert "raw_content" not in response.text
    assert "content" not in response.text
    _assert_terminal_validation_record(response, 422, "validation")


def test_event_id_accepts_digit_leading_uuids() -> None:
    assert _valid_event_id(DIGIT_EVENT_ID)
    assert _valid_event_id("cor_12345678-1234-1234-8234-123456789012")
    assert _valid_event_id("not-a-uuid")
    assert not _valid_event_id("NOPE!")


def test_digit_leading_uuid_round_trip() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["admin"]}
    items = client.get(f"/v1/audit-events?{WINDOW_QS}&decision=allow", headers=headers).json()[
        "items"
    ]
    assert DIGIT_EVENT_ID in [item["event_id"] for item in items]
    detail = client.get(f"/v1/audit-events/{DIGIT_EVENT_ID}", headers=headers)
    assert detail.status_code == 200
    assert list(_metadata_validator().iter_errors(detail.json())) == []
    assert detail.json()["event_id"] == DIGIT_EVENT_ID


@pytest.mark.asyncio
async def test_storage_failure_is_503_without_list() -> None:
    """Service-level 503 with an injected unavailable sessions adapter.

    This case does not kill PostgreSQL; it proves the service maps a dead
    store to the contractual 503 envelope without leaking a list.
    """

    def broken():
        raise RuntimeError("boom")

    service = AuditReadsService(broken, HMAC_KEY, PostgresAuditStore(broken))
    response = await service.list_events(
        {"from": "2026-09-20T00:00:00Z", "to": "2026-09-21T00:00:00Z"}, BEARERS["admin"]
    )
    assert response.status_code == 503
    body = json.loads(response.body.decode())
    assert body["error"]["code"] == "audit_unavailable" and body["retryable"] is True
