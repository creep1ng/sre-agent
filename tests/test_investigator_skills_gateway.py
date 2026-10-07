"""The investigator against the real gateway, PostgreSQL and the demo Skills (issue #32).

Real: the loop, its HTTP adapter, the producer of #331 and the control routes. Only model
replies are scripted. Each case starts with no Skill grant, so it passes alone and in any order.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import ADMIN_KEY, AUDIT_KEY, DATABASE_URL, SEED_ENV, headers
from test_control_acceptance import client as _client_fixture  # noqa: F401
from test_control_acceptance import migrated_acceptance_database as _database_fixture  # noqa: F401
from test_investigator_loop import HYPOTHESIS, TOOL, Provider, ScriptedGateway, ids
from test_investigator_skills import request_for

from sre_agent.application import create_application
from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.contract import InvestigationResult, Limits
from sre_agent.investigator.loop import investigate
from sre_agent.persistence.repositories import SkillVersionRepository
from sre_agent.settings import Settings

DEMO = {
    name: json.loads(Path(f"demo/skills/{name}/1.0.0.json").read_text(encoding="utf-8"))
    for name in ("incident-triage", "postmortem-writer")
}
TRIAGE, POSTMORTEM = DEMO["incident-triage"], DEMO["postmortem-writer"]
SECOND = {**TRIAGE, "version": "2.0.0", "manifest": {**TRIAGE["manifest"], "instructions": "v2"}}


@pytest.fixture
def client(request: pytest.FixtureRequest) -> TestClient:
    return request.getfixturevalue("_client_fixture")


def set_status(client: TestClient, skill: dict[str, Any], status: str) -> None:
    resource_id = f"{skill['skill_id']}@{skill['version']}"
    with psycopg.connect(DATABASE_URL) as connection:
        updated_at = connection.execute(
            "SELECT updated_at FROM resources WHERE resource_type='skill' AND resource_id=%s",
            (resource_id,),
        ).fetchone()[0]
    response = client.put(
        f"/v1/skills/{skill['skill_id']}/{skill['version']}/status",
        json={"status": status, "expected_updated_at": updated_at.isoformat()},
        headers=headers(ADMIN_KEY),
    )
    assert response.status_code == 200, response.text


@pytest.fixture(autouse=True)
def published(client: TestClient) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        # One grant row per principal, action and resource: start each case with none.
        connection.execute(
            "DELETE FROM grants WHERE principal_id='incident-harness' AND resource_type='skill'"
        )
    for skill in (TRIAGE, POSTMORTEM, SECOND):
        # A fresh key each time: the same content converges on the stored version.
        key = f"issue32-publish-{uuid4().hex}"
        response = client.post("/v1/skills/versions", json=skill, headers=headers(ADMIN_KEY, key))
        assert response.status_code == 201, response.text
        set_status(client, skill, "active")


def grant(client: TestClient, skill: dict[str, Any]) -> str:
    grant_id, ref = f"grant-issue32-{uuid4().hex[:16]}", f"{skill['skill_id']}@{skill['version']}"
    body = {"grant_id": grant_id, "principal_id": "incident-harness", "action": "invoke"}
    body |= {"resource": {"resource_type": "skill", "resource_id": ref}, "effect": "allow"}
    response = client.post("/v1/grants", json=body, headers=headers(ADMIN_KEY, grant_id))
    assert response.status_code == 201, response.text
    return grant_id


def pin(skill: dict[str, Any], digest: str | None = None) -> dict[str, Any]:
    return {"skill_id": skill["skill_id"], "version": skill["version"], "content_sha256": digest}


def harness(
    pins: list[dict[str, Any]], *replies: str, provider: Any = None
) -> tuple[InvestigationResult, ScriptedGateway]:
    """One investigator run: the real HTTP adapter against a fresh gateway application."""
    model = ScriptedGateway(*replies)
    key = SEED_ENV["INCIDENT_HARNESS_API_KEY"]
    settings = GatewaySettings(base_url="http://gateway", api_key=key, model_alias="triage-agent")

    async def run() -> InvestigationResult:
        app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
        skills = GatewayClient(settings, http)
        try:
            evidence = provider or Provider()
            return await investigate(
                request_for(pins), model, evidence, Limits(), ids(), skills=skills
            )
        finally:
            await http.aclose()
            await app.router.shutdown()

    return asyncio.run(run()), model


def audit(request_id: object) -> list[tuple[Any, ...]]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT operation, content_state, redacted_content, resource FROM audit_events "
            "WHERE correlation->>'request_id' = %s",
            (str(request_id),),
        ).fetchall()


def denied(result: InvestigationResult, model: ScriptedGateway, skill: dict[str, Any]) -> None:
    """The run ended before any model call, naming the version and nothing of its content."""
    ref = f"{skill['skill_id']}@{skill['version']}"
    assert (result.status, result.detail) == ("denied", f"skill unavailable: {ref}")
    assert (model.calls, result.turns, result.skills) == ([], [], [])


def test_the_harness_loads_only_what_the_gateway_grants_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    grant(client, TRIAGE)
    reads: list[str] = []
    original = SkillVersionRepository.get

    async def counted(self: SkillVersionRepository, skill_id: str, version: str) -> Any:
        reads.append(f"{skill_id}@{version}")
        return await original(self, skill_id, version)

    monkeypatch.setattr(SkillVersionRepository, "get", counted)
    caplog.set_level(logging.DEBUG)

    loaded, model = harness([pin(TRIAGE)], HYPOTHESIS)
    assert loaded.status == "completed"
    assert TRIAGE["manifest"]["instructions"] in model.calls[0]["input"]
    [record] = loaded.skills
    with psycopg.connect(DATABASE_URL) as connection:
        stored = connection.execute(
            "SELECT content_sha256 FROM skill_versions WHERE skill_id=%s AND version=%s",
            ("incident-triage", "1.0.0"),
        ).fetchone()[0]
    assert (record.content_sha256, record.dependencies) == (stored, [])
    # The pin names its resolution's audit event, which carries metadata only.
    [event] = audit(record.request_id)
    assert event[:3] == ("skills.resolve", "absent", None)

    # Not granted, inactive, and missing: one answer, and the artifact is never read.
    set_status(client, TRIAGE, "inactive")
    unknown = {**TRIAGE, "skill_id": "unknown-skill"}
    for skill in (POSTMORTEM, TRIAGE, unknown):
        reads.clear()
        refused, model = harness([pin(skill)], HYPOTHESIS)
        denied(refused, model, skill)
        assert reads == []
        for field in ("display_name", "description", "instructions"):
            assert POSTMORTEM["manifest"][field] not in refused.model_dump_json()
    audit_rows = json.dumps(audit(record.request_id), default=str)
    for text in (audit_rows, caplog.text):
        assert TRIAGE["manifest"]["instructions"] not in text


def test_a_dependency_needs_its_own_grant(client: TestClient) -> None:
    grant(client, POSTMORTEM)
    denied(*harness([pin(POSTMORTEM)], HYPOTHESIS), POSTMORTEM)

    grant(client, TRIAGE)
    loaded, model = harness([pin(POSTMORTEM)], HYPOTHESIS)
    assert loaded.status == "completed"
    prompt = model.calls[0]["input"]
    assert POSTMORTEM["manifest"]["instructions"] in prompt
    assert TRIAGE["manifest"]["instructions"] in prompt
    assert [(item.skill_id, item.version) for item in loaded.skills[0].dependencies] == [
        ("incident-triage", "1.0.0")
    ]


def test_a_pinned_version_survives_a_newer_one_and_is_never_swapped(client: TestClient) -> None:
    grant(client, TRIAGE)
    grant(client, SECOND)
    first, _ = harness([pin(TRIAGE)], HYPOTHESIS)
    newer, model = harness([pin(SECOND)], HYPOTHESIS)
    assert "v2" in model.calls[0]["input"].split("State: ")[0]

    recorded = pin(TRIAGE, first.skills[0].content_sha256)
    resumed, model = harness([recorded], HYPOTHESIS)
    assert resumed.status == "completed"
    assert TRIAGE["manifest"]["instructions"] in model.calls[0]["input"]
    assert resumed.skills[0].content_sha256 == first.skills[0].content_sha256
    assert newer.skills[0].content_sha256 != first.skills[0].content_sha256

    # Deactivated, the recorded version blocks the resumed run instead of moving it to 2.0.0.
    set_status(client, TRIAGE, "inactive")
    denied(*harness([recorded], HYPOTHESIS), TRIAGE)


def test_a_revocation_stops_the_next_use_without_a_restart(client: TestClient) -> None:
    grant_id = grant(client, TRIAGE)
    revoked_at: list[float] = []

    class Revoking(Provider):
        async def collect(self, tool: str, arguments: Any) -> Any:
            response = client.delete(f"/v1/grants/{grant_id}", headers=headers(ADMIN_KEY))
            assert response.status_code == 204, response.text
            revoked_at.append(time.monotonic())
            return await super().collect(tool, arguments)

    result, model = harness([pin(TRIAGE)], TOOL, HYPOTHESIS, provider=Revoking())

    assert (result.status, result.detail) == ("denied", "skill unavailable: incident-triage@1.0.0")
    assert (len(model.calls), len(result.turns)) == (1, 1)
    assert time.monotonic() - revoked_at[0] < 60
