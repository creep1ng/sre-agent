"""PostgreSQL-backed HTTP acceptance tests for governed BoK retrieval.

Failure modes listed before implementation:
- denied search/read accidentally touches chunk rows or leaks titles/counts;
- catalog-active but owner-unready/revoked versions deliver content;
- a collection ID or exact chunk ID bypasses its version grant;
- FTS uses session-dependent configuration or unstable tie ordering;
- no-match, denial, unready index, and a real PostgreSQL storage fault collapse;
- audit persistence accidentally records the query or returned chunk body.
- ambient TypeSafe-key presence enables evaluation or an ordinary request opts in;
- denied, unready, no-match, direct-read, or non-synthetic content reaches Jev;
- evaluator scores alter lexical order, failures leak provider detail, or an
  unpinned/invalid HTTP response is accepted.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.bok.jev import (
    JEV_ENDPOINT,
    JEV_MODEL,
    MAX_JEV_CANDIDATES,
    JevEvaluation,
    TypeSafeJevEvaluator,
)
from sre_agent.bok.owner import activate_version, ingest_bundle, seed_bok_demo
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import GrantRow, ResourceRow
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
DEMO_KEY = "sre_demo_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue332-bok-http-audit-key"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": "sre_admn_0123456789abcdefghijklmnop",
    "DEMO_HUMAN_API_KEY": DEMO_KEY,
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS bok_section_chunks, bok_documents, bok_collection_versions, "
            "audit_events, grants, credentials, resources, mcp_tools, mcp_servers, "
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
            async with database.transaction() as session:
                await seed_bok_demo(session)
                for action in ("bok.search", "bok.read"):
                    session.add(
                        GrantRow(
                            grant_id=f"grant-demo-{action.replace('.', '-')}",
                            principal_id="demo-human",
                            action=action,
                            resource_type="bok_collection",
                            resource_id="demo-incident-response@1.0.0",
                            effect="allow",
                            status="active",
                            created_at=datetime.now(UTC),
                        )
                    )
                alternate = {
                    "collection_id": "demo-incident-response",
                    "version": "2.0.0",
                    "owner_id": "bok-platform",
                    "display_name": "Incident Response Basics v2",
                    "description": "Un-granted synthetic successor version.",
                    "visibility": "private",
                    "documents": [
                        {
                            "document_id": "incident-triage-v2",
                            "title": "Incident triage v2",
                            "source_ref": "synthetic://incident-response/triage-v2",
                            "chunks": [
                                {
                                    "section_id": "severity",
                                    "chunk_index": 0,
                                    "content": "Assign severity using impact and scope.",
                                }
                            ],
                        }
                    ],
                }
                await ingest_bundle(session, alternate)
                await activate_version(session, "demo-incident-response", "2.0.0")
                session.add(
                    ResourceRow(
                        resource_type="bok_collection",
                        resource_id="demo-incident-response@2.0.0",
                        status="active",
                        owner_id="bok-platform",
                        source="bok",
                        source_ref="demo-incident-response@2.0.0",
                        display_name="Incident Response Basics v2",
                        visibility="private",
                        description="Un-granted synthetic successor version.",
                        tags=["demo"],
                    )
                )
                unready = {
                    "collection_id": "demo-unready",
                    "version": "1.0.0",
                    "owner_id": "bok-platform",
                    "display_name": "Unready collection",
                    "description": "Synthetic indexing fixture.",
                    "visibility": "private",
                    "documents": [
                        {
                            "document_id": "empty-doc",
                            "title": "Not ready",
                            "source_ref": "synthetic://unready/empty",
                            "chunks": [
                                {
                                    "section_id": "empty",
                                    "chunk_index": 0,
                                    "content": "",
                                }
                            ],
                        }
                    ],
                }
                await ingest_bundle(session, unready)
                session.add(
                    ResourceRow(
                        resource_type="bok_collection",
                        resource_id="demo-unready@1.0.0",
                        status="active",
                        owner_id="bok-platform",
                        source="bok",
                        source_ref="demo-unready@1.0.0",
                        display_name="Unready collection",
                        visibility="private",
                        description="Synthetic indexing fixture.",
                        tags=["demo"],
                    )
                )
                await session.flush()
                session.add(
                    GrantRow(
                        grant_id="grant-demo-unready-search",
                        principal_id="demo-human",
                        action="bok.search",
                        resource_type="bok_collection",
                        resource_id="demo-unready@1.0.0",
                        effect="allow",
                        status="active",
                        created_at=datetime.now(UTC),
                    )
                )
                ordered = {
                    "collection_id": "demo-stable-order",
                    "version": "1.0.0",
                    "owner_id": "bok-platform",
                    "display_name": "Stable order collection",
                    "description": "Synthetic deterministic search fixture.",
                    "visibility": "private",
                    "documents": [
                        {
                            "document_id": document_id,
                            "title": f"Document {document_id}",
                            "source_ref": f"synthetic://stable-order/{document_id}",
                            "chunks": [
                                {
                                    "section_id": "operations",
                                    "chunk_index": 0,
                                    "content": "operations stable match",
                                }
                            ],
                        }
                        for document_id in ("zeta-doc", "alpha-doc")
                    ],
                }
                await ingest_bundle(session, ordered)
                await activate_version(session, "demo-stable-order", "1.0.0")
                session.add(
                    ResourceRow(
                        resource_type="bok_collection",
                        resource_id="demo-stable-order@1.0.0",
                        status="active",
                        owner_id="bok-platform",
                        source="bok",
                        source_ref="demo-stable-order@1.0.0",
                        display_name="Stable order collection",
                        visibility="private",
                        description="Synthetic deterministic search fixture.",
                        tags=["demo"],
                    )
                )
                await session.flush()
                session.add(
                    GrantRow(
                        grant_id="grant-demo-stable-order-search",
                        principal_id="demo-human",
                        action="bok.search",
                        resource_type="bok_collection",
                        resource_id="demo-stable-order@1.0.0",
                        effect="allow",
                        status="active",
                        created_at=datetime.now(UTC),
                    )
                )
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


@pytest.fixture(scope="module")
def client(migrated_database: None):
    application = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(application) as test_client:
        yield test_client


def _url(collection: str, version: str = "1.0.0") -> str:
    return f"/v1/bok/collections/{collection}/versions/{version}"


def test_authorized_search_has_versioned_provenance_and_stable_order(client: TestClient) -> None:
    response = client.post(
        _url("demo-stable-order") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "operations stable", "limit": 5},
    )
    assert response.status_code == 200, response.text
    assert [item["document_id"] for item in response.json()["results"]] == ["alpha-doc", "zeta-doc"]
    assert all(
        item["collection_id"] == "demo-stable-order"
        and item["version"] == "1.0.0"
        and item["section_id"] == "operations"
        for item in response.json()["results"]
    )


def test_denied_search_and_direct_id_read_do_not_read_or_enumerate(client: TestClient) -> None:
    service = client.app.state.bok_service
    before = dict(service.content_reads_by_collection)
    denied_search = client.post(
        _url("demo-platform-operations") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "rollback readiness", "limit": 5},
    )
    denied_read = client.get(
        _url("demo-platform-operations") + "/chunks/deployment-checks/preflight/0",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
    )
    denied_version = client.post(
        _url("demo-incident-response", version="2.0.0") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "severity impact", "limit": 5},
    )
    assert denied_search.status_code == denied_read.status_code == denied_version.status_code == 403
    assert denied_search.json()["error"] == denied_read.json()["error"]
    assert denied_version.json()["error"] == denied_search.json()["error"]
    assert "Deployment checks" not in denied_search.text
    assert service.content_reads_by_collection == before


def test_no_match_unready_and_authorized_chunk_read_are_distinct(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    no_match = client.post(
        _url("demo-incident-response") + "/search",
        headers=headers,
        json={"query": "nonexistent-needle", "limit": 5},
    )
    assert no_match.status_code == 200
    assert no_match.json()["results"] == []
    unready = client.post(
        _url("demo-unready") + "/search",
        headers=headers,
        json={"query": "anything", "limit": 5},
    )
    assert unready.status_code == 503
    assert unready.json()["error"]["code"] == "index_unavailable"
    assert client.app.state.bok_service.content_reads_by_collection["demo-unready@1.0.0"] == 0
    read = client.get(
        _url("demo-incident-response") + "/chunks/incident-triage/severity/0",
        headers=headers,
    )
    assert read.status_code == 200
    result = read.json()
    assert result["collection_id"] == "demo-incident-response"
    assert result["version"] == "1.0.0"
    assert result["document_id"] == "incident-triage"
    assert result["title"] == "Incident triage"
    assert "Assign severity" in result["content"]


def test_revoked_owner_version_is_not_delivered_and_audit_has_no_content(
    client: TestClient,
) -> None:
    service = client.app.state.bok_service
    database = client.app.state.database

    stable_reads_before_revoke = service.content_reads_by_collection["demo-stable-order@1.0.0"]

    async def revoke_grant() -> None:
        async with database.transaction() as session:
            row = await session.get(GrantRow, "grant-demo-stable-order-search")
            assert row is not None
            row.status = "revoked"

    asyncio.run(revoke_grant())
    denied_by_grant = client.post(
        _url("demo-stable-order") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "operations stable", "limit": 5},
    )
    assert denied_by_grant.status_code == 403
    assert (
        service.content_reads_by_collection["demo-stable-order@1.0.0"] == stable_reads_before_revoke
    )

    async def revoke() -> None:
        from sre_agent.persistence.models import BoKCollectionVersionRow

        async with database.transaction() as session:
            row = await session.get(BoKCollectionVersionRow, ("demo-incident-response", "1.0.0"))
            assert row is not None
            row.status = "revoked"

    asyncio.run(revoke())
    denied_by_owner = client.get(
        _url("demo-incident-response") + "/chunks/incident-triage/severity/0",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
    )
    assert denied_by_owner.status_code == 503
    assert denied_by_owner.json()["error"]["code"] == "index_unavailable"
    assert service.content_reads_by_collection["demo-incident-response@1.0.0"] == 2

    with psycopg.connect(DATABASE_URL) as connection:
        events = connection.execute(
            "SELECT operation, content_state, to_jsonb(audit_events)::text "
            "FROM audit_events WHERE operation IN ('bok.search','bok.read')"
        ).fetchall()
    assert events
    assert all(row[1] == "absent" for row in events)
    serialized = " ".join(row[2] for row in events)
    for private_value in (
        "operations stable match",
        "Assign severity from customer impact",
        "nonexistent-needle",
        "rollback readiness",
    ):
        assert private_value not in serialized


class SyntheticJevProbe:
    """Test-only evaluator probe; it never makes a network request."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    async def evaluate(self, query: str, candidates: list[dict[str, object]]):
        self.calls.append(
            (
                query,
                [str(candidate["document_id"]) for candidate in candidates],
            )
        )
        if self.fail:
            raise RuntimeError("synthetic evaluator failure")
        return SimpleNamespace(
            model="jev-1.13.0",
            input_tokens=84,
            output_tokens=2,
            latency_ms=7,
            scores=[0.77 for _ in candidates],
        )


@pytest.fixture
def jev_client(migrated_database: None):
    async def restore_authority() -> None:
        from sre_agent.persistence.models import BoKCollectionVersionRow

        database = Database(DATABASE_URL)
        try:
            async with database.transaction() as session:
                for grant_id in (
                    "grant-demo-stable-order-search",
                    "grant-demo-bok-search",
                    "grant-demo-bok-read",
                ):
                    row = await session.get(GrantRow, grant_id)
                    if row is not None:
                        row.status = "active"
                version = await session.get(
                    BoKCollectionVersionRow, ("demo-incident-response", "1.0.0")
                )
                assert version is not None
                version.status = "active"
        finally:
            await database.dispose()

    asyncio.run(restore_authority())
    probe = SyntheticJevProbe()
    application = create_application(
        Settings(
            DATABASE_URL,
            audit_hmac_key=AUDIT_KEY,
            bok_jev_enabled=True,
        ),
        bok_jev_evaluator=probe,
    )
    with TestClient(application) as test_client:
        yield test_client, probe


def test_typesafe_key_presence_does_not_enable_jev() -> None:
    settings = Settings.from_environment(
        {"DATABASE_URL": DATABASE_URL, "TYPESAFE_API_KEY": "synthetic-test-key"}
    )
    assert settings.bok_jev_enabled is False
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY is required"):
        Settings.from_environment({"DATABASE_URL": DATABASE_URL, "BOK_JEV_ENABLED": "true"})


def test_jev_is_per_request_opt_in_shadow_and_preserves_lexical_results(
    client: TestClient, jev_client: tuple[TestClient, SyntheticJevProbe]
) -> None:
    shadow_client, evaluator = jev_client
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    lexical = client.post(
        _url("demo-stable-order") + "/search",
        headers=headers,
        json={"query": "operations stable", "limit": 5},
    )
    no_opt_in = shadow_client.post(
        _url("demo-stable-order") + "/search",
        headers=headers,
        json={"query": "operations stable", "limit": 5},
    )
    not_configured = client.post(
        _url("demo-stable-order") + "/search",
        headers=headers,
        json={
            "query": "operations stable",
            "limit": 5,
            "evaluation_mode": "shadow",
        },
    )
    opted_in = shadow_client.post(
        _url("demo-stable-order") + "/search",
        headers=headers,
        json={
            "query": "operations stable",
            "limit": 5,
            "evaluation_mode": "shadow",
        },
    )

    assert lexical.status_code == no_opt_in.status_code == opted_in.status_code == 200
    assert no_opt_in.json() == lexical.json()
    assert not_configured.json()["results"] == lexical.json()["results"]
    assert not_configured.json()["evaluation"]["status"] == "disabled"
    assert evaluator.calls == [("operations stable", ["alpha-doc", "zeta-doc"])]
    assert opted_in.json()["results"] == lexical.json()["results"]
    assert opted_in.json()["evaluation"] == {
        "mode": "shadow",
        "status": "evaluated",
        "model": "jev-1.13.0",
        "input_tokens": 84,
        "output_tokens": 2,
        "latency_ms": 7,
        "omitted_candidate_count": 0,
        "scores": [
            {
                "document_id": "alpha-doc",
                "section_id": "operations",
                "chunk_index": 0,
                "score": 0.77,
            },
            {
                "document_id": "zeta-doc",
                "section_id": "operations",
                "chunk_index": 0,
                "score": 0.77,
            },
        ],
    }
    with psycopg.connect(DATABASE_URL) as connection:
        audit_rows = connection.execute(
            "SELECT to_jsonb(audit_events)::text FROM audit_events WHERE operation = 'bok.search'"
        ).fetchall()
    audit_text = " ".join(row[0] for row in audit_rows)
    assert "operations stable" not in audit_text
    assert "operations stable match" not in audit_text


def test_jev_is_not_called_for_denied_unready_no_match_or_direct_read(
    jev_client: tuple[TestClient, SyntheticJevProbe],
) -> None:
    shadow_client, evaluator = jev_client
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    opted_in = {"evaluation_mode": "shadow"}
    denied = shadow_client.post(
        _url("demo-platform-operations") + "/search",
        headers=headers,
        json={"query": "rollback readiness", **opted_in},
    )
    unready = shadow_client.post(
        _url("demo-unready") + "/search",
        headers=headers,
        json={"query": "anything", **opted_in},
    )
    no_match = shadow_client.post(
        _url("demo-incident-response") + "/search",
        headers=headers,
        json={"query": "nonexistent-needle", **opted_in},
    )
    direct_read = shadow_client.get(
        _url("demo-incident-response") + "/chunks/incident-triage/severity/0",
        headers=headers,
    )

    assert denied.status_code == 403
    assert unready.status_code == 503
    assert no_match.status_code == direct_read.status_code == 200
    assert no_match.json()["results"] == []
    assert evaluator.calls == []


def test_jev_failure_keeps_lexical_results_and_returns_safe_fallback(
    client: TestClient, jev_client: tuple[TestClient, SyntheticJevProbe]
) -> None:
    shadow_client, evaluator = jev_client
    evaluator.fail = True
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    lexical = client.post(
        _url("demo-stable-order") + "/search",
        headers=headers,
        json={"query": "operations stable", "limit": 5},
    )
    evaluated = shadow_client.post(
        _url("demo-stable-order") + "/search",
        headers=headers,
        json={
            "query": "operations stable",
            "limit": 5,
            "evaluation_mode": "shadow",
        },
    )

    assert lexical.status_code == evaluated.status_code == 200
    assert evaluated.json()["results"] == lexical.json()["results"]
    assert evaluated.json()["evaluation"] == {
        "mode": "shadow",
        "status": "fallback",
        "reason": "evaluator_unavailable",
    }
    assert "synthetic evaluator failure" not in evaluated.text


def test_typesafe_adapter_uses_pinned_http_contract_without_network_access() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": JEV_MODEL,
                "answers": {"is_relevant": {"type": "noul", "noul": 0.61}},
                "usage": {"input_tokens": 84, "output_tokens": 2},
            },
        )

    candidates = [
        {
            "document_id": f"synthetic-doc-{index}",
            "section_id": "ops",
            "chunk_index": 0,
            "content": f"Synthetic passage {index}",
        }
        for index in range(2)
    ]

    async def evaluate() -> JevEvaluation:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await TypeSafeJevEvaluator(client, "synthetic-test-key").evaluate(
                "synthetic query", candidates
            )

    result = asyncio.run(evaluate())

    assert len(requests) == 2
    assert all(str(request.url) == JEV_ENDPOINT for request in requests)
    assert all(
        request.headers["authorization"] == "Bearer synthetic-test-key" for request in requests
    )
    states = [json.loads(request.content)["state"] for request in requests]
    assert all(state["query"] == "synthetic query" for state in states)
    assert [state["passage"]["id"] for state in states] == [
        "synthetic-doc-0/ops/0",
        "synthetic-doc-1/ops/0",
    ]
    assert result.model == JEV_MODEL
    assert result.scores == [0.61, 0.61]
    assert result.input_tokens == 168
    assert result.output_tokens == 4
    assert MAX_JEV_CANDIDATES == 5


def test_typesafe_adapter_rejects_boolean_token_usage() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": JEV_MODEL,
                "answers": {"is_relevant": {"type": "noul", "noul": 0.61}},
                "usage": {"input_tokens": True, "output_tokens": 2},
            },
        )

    async def evaluate() -> JevEvaluation:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await TypeSafeJevEvaluator(client, "synthetic-test-key").evaluate(
                "synthetic query",
                [
                    {
                        "document_id": "synthetic-doc",
                        "section_id": "ops",
                        "chunk_index": 0,
                        "content": "Synthetic passage",
                    }
                ],
            )

    with pytest.raises(RuntimeError, match="Jev evaluation request failed"):
        asyncio.run(evaluate())


def test_jev_refuses_non_synthetic_candidate_sources(
    jev_client: tuple[TestClient, SyntheticJevProbe],
) -> None:
    shadow_client, evaluator = jev_client
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE bok_documents SET source_ref = 'internal://not-synthetic' "
            "WHERE collection_id = 'demo-stable-order'"
        )
    response = shadow_client.post(
        _url("demo-stable-order") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={
            "query": "operations stable",
            "limit": 5,
            "evaluation_mode": "shadow",
        },
    )
    assert response.status_code == 200
    assert response.json()["evaluation"] == {
        "mode": "shadow",
        "status": "ineligible_source",
    }
    assert evaluator.calls == []


def test_postgresql_content_storage_failure_is_not_a_no_match(client: TestClient) -> None:
    async def restore_search_grant() -> None:
        async with client.app.state.database.transaction() as session:
            row = await session.get(GrantRow, "grant-demo-stable-order-search")
            assert row is not None
            row.status = "active"

    asyncio.run(restore_search_grant())
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE bok_section_chunks CASCADE")
    response = client.post(
        _url("demo-platform-operations") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "rollback readiness", "limit": 5},
    )
    assert response.status_code == 403
    response = client.post(
        _url("demo-stable-order") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "severity impact", "limit": 5},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
