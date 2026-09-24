"""Issue #25 B2b: audit HTTP reads over the published 2.3.0 contract."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
from sre_agent.gateway.audit_reads import AuditReadsService
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
) -> AuditEvent:
    # Letter-leading ids satisfy the 2.3.0 Id pattern for detail lookup.
    return AuditEvent(
        event_id=UUID(int=0xB0000000000000000000000000000000 + number),
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


WINDOW_QS = "from=2026-09-20T00:00:00Z&to=2026-09-21T00:00:00Z"


def test_unauthenticated_and_forbidden() -> None:
    client = _client()
    assert client.get(f"/v1/audit-events?{WINDOW_QS}").status_code == 401
    bad = client.get(f"/v1/audit-events?{WINDOW_QS}", headers={"Authorization": "Bearer not-a-key"})
    assert bad.status_code == 401
    assert bad.headers["WWW-Authenticate"] == "Bearer"
    denied = client.get(
        f"/v1/audit-events?{WINDOW_QS}", headers={"Authorization": BEARERS["bystander"]}
    )
    assert denied.status_code == 403
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
    alone = client.get("/v1/audit-events?from=2026-09-21T00:00:00Z", headers=headers).json()
    assert alone == {"items": [], "limit": 100, "truncated": False}


def test_list_filters_default_limit_and_empty() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["admin"]}
    response = client.get(f"/v1/audit-events?{WINDOW_QS}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert (body["limit"], body["truncated"]) == (100, False)
    assert len(body["items"]) == 3
    mine = client.get("/v1/audit-events?principal_id=admin-human", headers=headers).json()
    assert len(mine["items"]) == 3
    denied = client.get("/v1/audit-events?decision=deny", headers=headers).json()
    assert len(denied["items"]) == 1
    requested = client.get(
        f"/v1/audit-events?request_id={UUID(int=0xC0000000000000000000000000000000 + 52)}",
        headers=headers,
    ).json()
    assert len(requested["items"]) == 1
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
    assert client.get("/v1/audit-events/NOPE!", headers=headers).status_code == 422


@pytest.mark.asyncio
async def test_storage_failure_is_503_without_list() -> None:
    def broken():
        raise RuntimeError("boom")

    service = AuditReadsService(broken, HMAC_KEY)
    response = await service.list_events(
        {"from": "2026-09-20T00:00:00Z", "to": "2026-09-21T00:00:00Z"}, BEARERS["admin"]
    )
    assert response.status_code == 503
    body = json.loads(response.body.decode())
    assert body["error"]["code"] == "audit_unavailable" and body["retryable"] is True
