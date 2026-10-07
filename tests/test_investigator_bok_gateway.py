"""The investigator against the real gateway, PostgreSQL and the BoK demo (issue #34).

Real: the loop, its HTTP adapter, the producer of #332 and the control routes; only model
replies are scripted. Each case starts with no BoK grant for the harness, so it passes alone
and in any order. `reads` counts the producer's content queries per collection version."""

import asyncio
import logging
import time
from collections import Counter
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import ADMIN_KEY, AUDIT_KEY, DATABASE_URL, SEED_ENV, headers
from test_control_acceptance import client as _client_fixture  # noqa: F401
from test_control_acceptance import migrated_acceptance_database as _database_fixture  # noqa: F401
from test_investigator_bok import CONCLUDE, OPERATIONS, RESPONSE, allowed, request_for, search
from test_investigator_loop import Provider, ScriptedGateway, hypothesis, ids

from sre_agent.application import create_application
from sre_agent.bok.owner import seed_bok_demo
from sre_agent.bok.retrieval import BoKOwnerRepository
from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.contract import InvestigationResult, Limits
from sre_agent.investigator.loop import investigate
from sre_agent.persistence.database import Database
from sre_agent.settings import Settings

KEY = SEED_ENV["INCIDENT_HARNESS_API_KEY"]
CONTENT = "Assign severity from customer impact, scope, and active risk."
RESTRICTED = ("Deployment checks", "rollback readiness before deployment")
LOCKED = "/v1/bok/collections/demo-platform-operations/versions/1.0.0/chunks/deployment-checks/"


@pytest.fixture
def client(request: pytest.FixtureRequest) -> TestClient:
    return request.getfixturevalue("_client_fixture")


@pytest.fixture(autouse=True)
def published(client: TestClient) -> None:
    async def converge() -> None:
        database = Database(DATABASE_URL)
        try:
            async with database.transaction() as session:
                await seed_bok_demo(session)
        finally:
            await database.dispose()

    asyncio.run(converge())
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "DELETE FROM grants WHERE principal_id='incident-harness' "
            "AND resource_type='bok_collection'"
        )


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    counted: Counter[str] = Counter()
    for name in ("search", "read_chunk"):
        original = getattr(BoKOwnerRepository, name)

        async def counting(self: Any, collection_id: str, version: str, *rest: Any, _o=original):
            counted[f"{collection_id}@{version}"] += 1
            return await _o(self, collection_id, version, *rest)

        monkeypatch.setattr(BoKOwnerRepository, name, counting)
    return counted


def grant(client: TestClient, collection: str, action: str = "bok.search") -> str:
    grant_id = f"grant-issue34-{uuid4().hex[:16]}"
    body = {"grant_id": grant_id, "principal_id": "incident-harness", "action": action}
    body |= {"resource": {"resource_type": "bok_collection", "resource_id": collection}}
    response = client.post(
        "/v1/grants", json=body | {"effect": "allow"}, headers=headers(ADMIN_KEY, grant_id)
    )
    assert response.status_code == 201, response.text
    return grant_id


def harness(
    collections: list[str], *replies: str, model: ScriptedGateway | None = None, down: bool = False
) -> tuple[InvestigationResult, ScriptedGateway, Provider]:
    model = model or ScriptedGateway(*replies)
    provider = Provider()
    url = "http://127.0.0.1:9" if down else "http://gateway"
    settings = GatewaySettings(base_url=url, api_key=KEY, model_alias="triage-agent")

    async def run() -> InvestigationResult:
        app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
        transport = None if down else httpx.ASGITransport(app=app)
        http = httpx.AsyncClient(transport=transport, trust_env=False)
        try:
            request = request_for(*(allowed(item) for item in collections))
            return await investigate(
                request, model, provider, Limits(), ids(), bok=GatewayClient(settings, http)
            )
        finally:
            await http.aclose()
            await app.router.shutdown()

    return asyncio.run(run()), model, provider


def test_a_granted_collection_answers_with_a_citation_that_reads_back(
    client: TestClient, reads: Counter[str]
) -> None:
    grant(client, RESPONSE)
    grant(client, RESPONSE, "bok.read")
    result, _, _ = harness([RESPONSE], search(), hypothesis("ev_00000000"))

    assert result.status == "completed"
    [item] = result.evidence
    assert (item.source, item.datasource_uid) == ("bok", RESPONSE)
    assert item.summary.endswith(CONTENT)
    # The citation is verifiable: its query is the producer's read of exactly that chunk.
    read = client.get(item.query or "", headers=headers(KEY))
    assert (read.status_code, read.json().get("content")) == (200, CONTENT)
    assert reads == Counter({RESPONSE: 2})


def test_a_collection_without_a_grant_contributes_nothing_and_its_ids_open_nothing(
    client: TestClient, reads: Counter[str]
) -> None:
    grant(client, RESPONSE)
    replies = search(), search(OPERATIONS, "rollback")
    result, model, provider = harness([RESPONSE, OPERATIONS], *replies)

    assert (result.status, result.detail) == ("denied", f"bok collection unavailable: {OPERATIONS}")
    assert [item.datasource_uid for item in result.evidence] == [RESPONSE]
    assert (provider.calls, len(model.calls)) == ([], 2)
    # Asking for a restricted chunk by its IDs is denied without reading it either.
    direct = client.get(LOCKED + "preflight/0", headers=headers(KEY))
    assert direct.status_code == 403
    for text in RESTRICTED:
        assert text not in result.model_dump_json() and text not in direct.text
    assert reads == Counter({RESPONSE: 1})


def test_an_empty_search_is_an_answer_and_never_a_fixture(
    reads: Counter[str], client: TestClient
) -> None:
    grant(client, RESPONSE)
    result, _, provider = harness([RESPONSE], search(query="zebra unicorn"), CONCLUDE)

    assert (result.status, result.evidence, provider.calls) == ("completed", [], [])
    assert getattr(result.turns[0].tool_invocation, "result_summary", None) == "no results"
    assert reads == Counter({RESPONSE: 1})


# Each outage and its repair; a producer that is down needs no SQL, only a closed port.
OUTAGES = {
    "index_unavailable": (
        "UPDATE bok_collection_versions SET status='inactive' WHERE version='1.0.0'",
        "UPDATE bok_collection_versions SET status='active' WHERE version='1.0.0'",
    ),
    "storage_unavailable": (
        "ALTER TABLE bok_section_chunks RENAME TO unavailable_bok_chunks",
        "ALTER TABLE unavailable_bok_chunks RENAME TO bok_section_chunks",
    ),
    "network": ("SELECT 1", "SELECT 1"),
}


@pytest.mark.parametrize(
    "code",
    ["index_unavailable", "storage_unavailable", "network"],
    ids=["retired-version", "storage-down", "producer-down"],
)
def test_a_retired_version_a_storage_failure_and_a_down_producer_are_told_apart(
    client: TestClient, code: str
) -> None:
    grant(client, RESPONSE)
    outage, repair = OUTAGES[code]
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(outage)
        try:
            result, model, provider = harness([RESPONSE], search(), down=code == "network")
        finally:
            connection.execute(repair)

    assert (result.status, result.detail) == (
        "upstream_unavailable",
        f"bok search failed: {RESPONSE} ({code})",
    )
    assert (result.evidence, provider.calls, len(model.calls)) == ([], [], 1)


def test_a_revocation_stops_the_next_search_without_a_restart(
    client: TestClient, reads: Counter[str]
) -> None:
    grant_id = grant(client, RESPONSE)
    revoked_at: list[float] = []

    class Revoking(ScriptedGateway):
        async def respond(self, **request: str) -> Any:
            if self.calls:
                response = client.delete(f"/v1/grants/{grant_id}", headers=headers(ADMIN_KEY))
                assert response.status_code == 204, response.text
                revoked_at.append(time.monotonic())
            return await super().respond(**request)

    result, _, _ = harness([RESPONSE], model=Revoking(search(), search()))

    assert (result.status, result.detail) == ("denied", f"bok collection unavailable: {RESPONSE}")
    assert [item.evidence_id for item in result.evidence] == ["ev_00000000"]
    assert reads == Counter({RESPONSE: 1})
    assert time.monotonic() - revoked_at[0] < 60


def test_the_audit_keeps_decision_and_resource_but_no_query_or_fragment(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with psycopg.connect(DATABASE_URL) as connection:
        before = [row for (row,) in connection.execute("SELECT event_id FROM audit_events")]
    grant(client, RESPONSE)
    harness([RESPONSE], search(), hypothesis("ev_00000000"))
    harness([RESPONSE, OPERATIONS], search(OPERATIONS, "rollback readiness"))

    with psycopg.connect(DATABASE_URL) as connection:
        events = connection.execute(
            "SELECT response_status, outcome, policy_decision->>'decision', content_state, "
            "correlation->>'request_id' IS NOT NULL, resource->>'resource_type', "
            "to_jsonb(audit_events)::text FROM audit_events "
            "WHERE operation = 'bok.search' AND NOT event_id = ANY(%s) ORDER BY occurred_at",
            (before,),
        ).fetchall()
    assert [row[:6] for row in events] == [
        (200, "success", "allow", "absent", True, "bok_collection"),
        (403, "denied", "deny", "absent", True, "bok_collection"),
    ]
    stored = " ".join(row[6] for row in events) + caplog.text
    for text in ("severity impact", "rollback readiness", CONTENT, *RESTRICTED):
        assert text not in stored
