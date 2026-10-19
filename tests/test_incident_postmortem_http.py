"""Issue #335 first cut: the persisted postmortem over HTTP, against real PostgreSQL.

Written from the ways it could fail before the store and routes existed:

1. The artifact lives only in memory or in the response: a fresh application
   (API restart) reads another id, another version, or nothing.
2. A writer holding an old version silently overwrites a newer edit instead of 409.
3. A retried create opens a second artifact for the same incident.
4. A timeline or action cites an event that does not exist, or one from another
   incident, and the artifact is still stored as if it were sourced.
5. A section of the #43 CA2 minimum is missing, or uncertainty is erased (a cause
   without a certainty grade), and the artifact is still accepted.
6. A reader with `run.read` but not `run.read_context` receives text fragments.
7. The review is attributed to a name in the body, not the authenticated principal.
8. An edit after the review keeps the old approval valid for the new version.
9. `start_postmortem` leaves `state.postmortem` empty or with an id the store
   never holds, so close is either impossible or satisfied by a bare `pm_` prefix.
10. Close is accepted with no artifact, an unreviewed version, or a stale review.
11. A rejected close mutates the incident.
"""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.incident.runtime import (
    ActorReference,
    IncidentCommand,
    IncidentRuntime,
    PreconditionFailedError,
)
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository
from sre_agent.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
INCIDENT_ID = "inc-335-postmortem"
NEIGHBOUR_ID = "inc-335-neighbour"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
BEARERS: dict[str, str] = {}
FACTS: dict[str, Any] = {}
SUMMARY = "Checkout payments failed for 14 minutes after a bad config push."


def _state(state: str) -> dict[str, Any]:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": state,
        "incident_id": INCIDENT_ID if state != "detected" else None,
        "linked_incident_id": None,
        "severity": "sev2" if state != "detected" else None,
        "impact": "Payment requests are failing.",
        "hypotheses": [],
        "evidence": [{"evidence_id": "ev_1", "summary": "Error rate back to baseline."}],
        "mitigation_strategy": {"mitigation_id": "mit_1", "verification_check": "error rate"},
        "postmortem": None,
        "updated_at": NOW.isoformat(),
    }


@pytest.fixture(scope="module", autouse=True)
def stack() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_reservations, request_attributions, alert_triage, "
            "consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, audit_events, skill_versions, grants, credentials, "
            "resources, mcp_tools, mcp_servers, principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES ('demo-human','human','Demo','active',now(),now()),"
            "('watcher-human','human','Watcher','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at, owner_id, "
            "source, source_ref, display_name, visibility, description) VALUES "
            "('incident_workflow','incident-response','active',now(),'papiarcacamilo',"
            "'incident_workflow','incident-response@1.0.0','Incident response','private','Demo')"
        )
    database = Database(DATABASE_URL)
    granted = [("demo-human", f"run.{action}") for action in ("start", "command", "approve", "read", "read_context")]  # noqa: E501  # fmt: skip

    async def _setup() -> None:
        async with database.transaction() as session:
            demo = await CredentialRepository(session).issue("demo-human")
            watcher = await CredentialRepository(session).issue("watcher-human")
            for index, (principal, action) in enumerate([*granted, ("watcher-human", "run.read")]):
                await GrantRepository(session).create(
                    f"grant-335-{index}",
                    principal,
                    action,
                    "incident_workflow",
                    "incident-response",
                )
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(INCIDENT_ID, _state("verifying"), now=NOW)
            await work.incidents.add(NEIGHBOUR_ID, _state("detected"), now=NOW)
            run_state = {"workflow_version": "1.0.0", "current_state": "verifying", "status": "running"}  # noqa: E501  # fmt: skip
            run = await work.runs.add("run_335verify01", INCIDENT_ID, run_state, now=NOW)
        FACTS["verify_run"] = run.run_id
        BEARERS.update(demo=f"Bearer {demo.key}", watcher=f"Bearer {watcher.key}")

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client() -> TestClient:
    """A fresh application per call: nothing survives in process between requests."""
    return TestClient(create_application(Settings(DATABASE_URL)))


def _headers(who: str = "demo", key: str | None = None) -> dict[str, str]:
    return {"Authorization": BEARERS[who]} | ({"Idempotency-Key": key} if key else {})


async def _transition(transition_id: str, run_id: str, **extra: Any) -> None:
    database = Database(DATABASE_URL)
    workflow = load_incident_workflow(REPOSITORY_ROOT / "agent/workflows/incident-response.yaml")
    try:
        runtime = IncidentRuntime(workflow, lambda: PostgresIncidentUnitOfWork(database))
        await runtime.execute(
            IncidentCommand(
                command_id=f"cmd-335-{transition_id}-{extra.get('expected_incident_version')}",
                incident_id=INCIDENT_ID,
                run_id=run_id,
                transition_id=transition_id,
                actor="human",
                actor_reference=ActorReference(principal_id="demo-human"),
                **extra,
            )
        )
    finally:
        await database.dispose()


def _sql(query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(query, params).fetchall()


def _incident() -> tuple[dict[str, Any], int]:
    query = "SELECT state, version FROM incident.incidents WHERE incident_id=%s"
    return _sql(query, INCIDENT_ID)[0]


def _content(timeline_event: str, action_event: str, **changes: Any) -> dict[str, Any]:
    return {
        "summary": SUMMARY,
        "impact": "About 3% of checkouts failed; revenue impact unknown.",
        "timeline": [{"event_id": timeline_event, "description": "Stability check passed."}],
        "cause": {"statement": "Config push removed the payment timeout.", "certainty": "probable"},
        "strategy": "Roll back the config and add a timeout guard.",
        "actions_taken": [{"event_id": action_event, "description": "Postmortem opened."}],
        "verification": "Error rate stayed at baseline for 30 minutes.",
        "pending": ["Add a config lint for timeouts."],
        "unknowns": ["Exact revenue impact."],
        **changes,
    }


def _put(content: Any, expected_version: int, who: str = "demo") -> Any:
    return _client().put(
        f"/v1/incidents/{INCIDENT_ID}/postmortem",
        json={"expected_version": expected_version, "content": content},
        headers=_headers(who),
    )


def _review(version: int, outcome: str = "approved", **extra: Any) -> Any:
    return _client().post(
        f"/v1/incidents/{INCIDENT_ID}/postmortem/reviews",
        json={"version": version, "outcome": outcome, **extra},
        headers=_headers(),
    )


def test_resolved_to_postmortem_reserves_the_artifact_id() -> None:
    asyncio.run(_transition("verification_passed", FACTS["verify_run"], outcome="stable"))
    assert _incident()[0]["state"] == "resolved"
    started = _client().post(
        f"/v1/incidents/{INCIDENT_ID}/runs",
        json={"workflow_version": "1.0.0", "objective": "postmortem"},
        headers=_headers(key="key-335-start-postmortem"),
    )
    assert started.status_code == 201, started.text
    FACTS["pm_run"] = started.json()["run_id"]
    state, _ = _incident()
    assert state["state"] == "postmortem"
    FACTS["pm_id"] = state["postmortem"]["postmortem_id"]
    assert FACTS["pm_id"].startswith("pm_")
    events = dict(_sql(
        "SELECT payload->>'transition_id', event_id FROM incident.run_events WHERE incident_id=%s",
        INCIDENT_ID,
    ))  # fmt: skip
    FACTS["verified_event"] = events["verification_passed"]
    FACTS["started_event"] = events["start_postmortem"]


def test_close_without_an_artifact_is_rejected_and_changes_nothing() -> None:
    state, version = _incident()
    with pytest.raises(PreconditionFailedError):
        asyncio.run(
            _transition(
                "close_incident", FACTS["pm_run"], approval=True, expected_incident_version=version
            )  # noqa: E501  # fmt: skip
        )
    assert _incident() == (state, version)


def test_citations_must_name_real_events_of_this_incident() -> None:
    neighbour = _client().post(
        f"/v1/incidents/{NEIGHBOUR_ID}/runs",
        json={"workflow_version": "1.0.0", "objective": "triage"},
        headers=_headers(key="key-335-neighbour-triage"),
    )
    assert neighbour.status_code == 201
    foreign = _sql("SELECT event_id FROM incident.run_events WHERE incident_id=%s", NEIGHBOUR_ID)
    for missing in ("evt_doesnotexist", foreign[0][0]):
        refused = _put(_content(FACTS["verified_event"], missing), 0)
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "unknown_event_reference"
    uncertain = _content(FACTS["verified_event"], FACTS["started_event"], cause={"statement": "x"})
    assert _put(uncertain, 0).status_code == 422
    assert _sql("SELECT count(*) FROM incident.postmortems") == [(0,)]


def test_create_survives_a_restart_and_a_retry_does_not_duplicate() -> None:
    content = _content(FACTS["verified_event"], FACTS["started_event"])
    created = _put(content, 0)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["postmortem_id"], body["version"]) == (FACTS["pm_id"], 1)
    assert sorted(body["run_ids"]) == sorted([FACTS["verify_run"], FACTS["pm_run"]])
    assert body["updated_by"] == "demo-human" and "content" not in body

    assert _put(content, 0).status_code == 409  # retried create: no second artifact
    reread = _client().get(f"/v1/incidents/{INCIDENT_ID}/postmortem", headers=_headers())
    assert reread.status_code == 200
    assert (reread.json()["postmortem_id"], reread.json()["version"]) == (FACTS["pm_id"], 1)
    assert reread.json()["content"] == content
    assert _sql("SELECT count(*) FROM incident.postmortems") == [(1,)]


def test_a_stale_edit_conflicts_and_a_current_one_advances() -> None:
    edited = _content(FACTS["verified_event"], FACTS["started_event"], summary=SUMMARY + " v2")
    assert _put(edited, 1).status_code == 200
    stale = _put(_content(FACTS["verified_event"], FACTS["started_event"]), 1)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "postmortem_version_conflict"
    assert _sql("SELECT max(version) FROM incident.postmortem_revisions") == [(2,)]


def test_progress_readers_get_no_text_and_cannot_write() -> None:
    seen = _client().get(f"/v1/incidents/{INCIDENT_ID}/postmortem", headers=_headers("watcher"))
    assert seen.status_code == 200
    assert seen.json()["content_included"] is False and "content" not in seen.json()
    for fragment in ("Checkout", "timeout", "revenue", "config"):
        assert fragment not in seen.text
    assert _put(_content(FACTS["verified_event"], FACTS["started_event"]), 2, "watcher").status_code == 403  # noqa: E501  # fmt: skip


def test_close_requires_an_approved_review_of_the_current_version() -> None:
    assert _review(1).status_code == 409  # the reviewer saw an older version
    assert _review(2, reviewer_id="admin-human").status_code == 422
    approved = _review(2, comment="Accurate and complete.")
    assert approved.status_code == 201
    review = approved.json()["review"]
    assert (review["status"], review["reviewed_version"]) == ("approved", 2)
    assert review["reviewer_id"] == "demo-human"
    # Editing after the review voids it for the new version.
    assert _put(_content(FACTS["verified_event"], FACTS["started_event"]), 2).status_code == 200
    state, version = _incident()
    with pytest.raises(PreconditionFailedError):
        asyncio.run(
            _transition(
                "close_incident", FACTS["pm_run"], approval=True, expected_incident_version=version
            )  # noqa: E501  # fmt: skip
        )
    assert _incident() == (state, version)

    assert _review(3).status_code == 201
    asyncio.run(
        _transition(
            "close_incident", FACTS["pm_run"], approval=True, expected_incident_version=version
        )  # noqa: E501  # fmt: skip
    )
    assert _incident()[0]["state"] == "closed"
    approval = _sql(
        "SELECT document->'approval' FROM incident.decisions WHERE incident_id=%s "
        "AND document->>'transition_id'='close_incident'",
        INCIDENT_ID,
    )[0][0]
    assert (approval["postmortem_id"], approval["postmortem_version"]) == (FACTS["pm_id"], 3)
    assert approval["actor_reference"]["principal_id"] == "demo-human"
