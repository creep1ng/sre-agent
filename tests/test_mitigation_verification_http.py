"""The agent verifies what an approval ran, after a delay, in the same run (#723, cut b2).

Written before the verification was dispatched. Ways this can fail:
1. an approval that ran its operation is never verified, so the incident waits in verifying
   with nothing measuring it, or it is measured before VERIFICATION_DELAY_SECONDS pass;
2. a measured recovery does not resolve the incident, or a measured failure does not return
   it to investigating with the run ended, or the incident does not keep what was measured;
3. the verification is not told what ran, or it reruns the run's investigation instead of
   being a dispatch of its own, with its own receipts;
4. a verification that reaches no verdict moves the incident or takes the manual commands
   away;
5. a person who verified first is overridden by the agent.
Principals, the model alias and the MCP catalog come from the investigator's suite; the model,
the MCP server and the deploy-executor are scripted.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import test_incident_investigator_http as suite
from test_incident_investigator_http import seeded_database  # noqa: F401  (module fixture)
from test_mitigation_execution_http import CALLS, SIGNING_KEY, _executor

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.persistence.database import Database
from sre_agent.settings import Settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provision_demo import SERVICE_OPERATIONS, demo_grants, service_operation  # noqa: E402
from provision_incident_workflow import build_service  # noqa: E402

CHECK = "The synthetic payment error rate returns to zero."
PASSED = {"action": "verify_mitigation", "passed": True, "summary": "5xx back to 0."}
FAILED = {"action": "verify_mitigation", "passed": False, "summary": "5xx still at 0.3."}
HUMAN = {"action": "request_human", "reason": "The metric is not there yet."}
RAN = ["rolled_back", "demo/checkout:1.5.0", "demo/checkout:1.4.0"]
MEASURE = suite._scripted_decision({"incident": {"hypotheses": []}, "collected_evidence": []}, "")


@pytest.fixture(scope="module", autouse=True)
def operation_grant(request: pytest.FixtureRequest) -> None:
    """The executor's catalog and the grant the demo provisions: roll sre-checkout back."""
    request.getfixturevalue("seeded_database")
    database, admin = Database(suite.DATABASE_URL), f"Bearer {suite.ADMIN_KEY}"

    async def setup() -> None:
        control = build_service(database, suite.AUDIT_KEY.encode())
        for resource_id, description in SERVICE_OPERATIONS.items():
            body = service_operation(resource_id, description)
            created = await control.create_catalog_resource(body, admin, resource_id)
            assert created.status_code == 201
        [grant] = [body for body in demo_grants() if body["action"] == "mitigation.execute"]
        assert (await control.create_grant(grant, admin, grant["grant_id"])).status_code == 201
        await database.dispose()

    asyncio.run(setup())


class VerifyingLLM(suite.ScriptedLLM):
    """Investigates to the rollback; once it ran, measures again and answers `verdict`."""

    def __init__(self, verdict: dict[str, Any]) -> None:
        super().__init__()
        self.verdict, self.verifying = verdict, []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        state = suite._state(request)
        reply = suite._scripted_decision(state, "Orders fail since release 1.5.0 started.")
        if state["objective"] == "verify":
            self.verifying.append(state)
            measured = [item["evidence_id"] for item in state["collected_evidence"]]
            reply = self.verdict if measured or "reason" in self.verdict else MEASURE
            reply = reply | ({"supporting_evidence": measured} if "passed" in reply else {})
        elif reply["action"] == "propose_mitigation":
            reply |= {"operation": suite.ROLLBACK, "verification_check": CHECK}
        return ProviderResult(
            response_id=f"resp_verify_{len(self.requests):04d}",
            model=request.model,
            text=json.dumps(reply),
            provider=request.provider,
        )


def _settings(port: int, executor_url: str, delay: float) -> Settings:
    return Settings.from_environment(
        suite.SEED_ENV
        | {
            "DATABASE_URL": suite.DATABASE_URL,
            "AUDIT_HMAC_KEY": suite.AUDIT_KEY,
            "INVESTIGATOR_GATEWAY_URL": f"http://127.0.0.1:{port}",
            "INVESTIGATOR_GATEWAY_API_KEY": suite.HARNESS_KEY,
            "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
            "DEPLOY_EXECUTOR_URL": executor_url,
            "DEPLOY_EXECUTOR_SIGNING_KEY": SIGNING_KEY,
            "VERIFICATION_DELAY_SECONDS": str(delay),
        }
    )


def _verifications(events: list[dict[str, Any]], run_id: str) -> list[tuple[str, str]]:
    receipts = suite._receipts(events)
    return [(r["phase"], r["status"]) for r in receipts if r["dispatch_id"] == f"{run_id}-verify"]


def _approved(
    incident_id: str,
    llm: VerifyingLLM,
    delay: float,
    then: Any = None,
    after: Any = None,
    wait: bool = True,
) -> Any:
    """Investigate to the rollback and approve it; `then` acts at once, `after` once the
    verification ended."""
    suite._add_incident(incident_id, "sre-checkout")
    suite._grant_run_access()
    port = suite._free_port()
    with _executor("demo/checkout:1.5.0") as executor_url:
        app = create_application(
            _settings(port, executor_url, delay), llm_provider=llm, mcp_client=suite.ScriptedMCP()
        )
        with suite._serve(app, port) as url, httpx.Client(base_url=url, timeout=15) as client:
            suite._add_agent_mcp_grants(client, "positive")
            started = suite._start(client, incident_id, f"{incident_id}-start")
            assert started.json()["current_state"] == "mitigating", started.text
            run_id = started.json()["run_id"]
            assert suite._send_command(client, incident_id, run_id, "approve_mitigation") == 202
            assert len(CALLS) == 1, "the rollback runs once"
            if then is not None:
                then(client, run_id)
            deadline = time.monotonic() + (20 if wait else 0)
            while time.monotonic() < deadline:
                events = suite._database_rows(incident_id, run_id)[1]
                if ("outcome", "success") in _verifications(events, run_id):
                    break
                time.sleep(0.2)
            if after is not None:
                after(client, run_id)
            headers = {"Authorization": f"Bearer {suite.HUMAN_KEY}"}
            page = client.get(f"/v1/incidents/{incident_id}/runs/{run_id}/events", headers=headers)
            timeline = [event["summary"] for event in page.json()["events"]]
    with psycopg.connect(suite.DATABASE_URL) as connection:
        query = "SELECT state->>'status' FROM incident.runs WHERE run_id=%s"
        [run_status] = connection.execute(query, (run_id,)).fetchone()
    state, events, _ = suite._database_rows(incident_id, run_id)
    return state, events, timeline, run_id, run_status


@pytest.mark.parametrize(
    ("verdict", "reached", "told", "run_status"),
    [
        (PASSED, "resolved", "found the service recovered", "running"),
        (FAILED, "investigating", "found the service had not recovered", "terminated"),
    ],
    ids=["recovered", "not-recovered"],
)
def test_a_measured_verdict_moves_the_incident_and_keeps_what_was_measured(
    verdict: dict[str, Any], reached: str, told: str, run_status: str
) -> None:
    def not_yet(_client: httpx.Client, run_id: str) -> None:
        events = suite._database_rows(f"inc-verify-{reached}", run_id)[1]
        assert _verifications(events, run_id) == [], "nothing is measured before the delay"

    llm = VerifyingLLM(verdict)
    state, events, timeline, run_id, status = _approved(f"inc-verify-{reached}", llm, 1, not_yet)

    # This run's own last transition: after a failure the system's next run (#710) may already
    # have moved the incident on.
    moved_to = [event["to"] for event in events if "transition_id" in event][-1]
    assert (moved_to, status) == (reached, run_status)
    assert _verifications(events, run_id) == [("intent", "pending"), ("outcome", "success")]
    investigation = [r["phase"] for r in suite._receipts(events) if r["dispatch_id"] == run_id]
    assert investigation == ["intent", "outcome"]
    shown = llm.verifying[0]["mitigation"]
    assert (shown["verification_check"], shown["operation"]) == (CHECK, suite.ROLLBACK)
    assert [shown["execution"][key] for key in ("outcome", "before_image", "after_image")] == RAN
    measured = llm.verifying[-1]["collected_evidence"][-1]["evidence_id"]
    assert measured in [item["evidence_id"] for item in state["evidence"]]
    transition = "Service verified stable." if verdict["passed"] else "Verification failed"
    assert f"Verification {told}." in timeline
    assert any(summary.startswith(transition) for summary in timeline)


def test_a_verification_without_a_verdict_leaves_the_manual_commands() -> None:
    waited: list[str] = []

    def decide(client: httpx.Client, run_id: str) -> None:
        waited.append(suite._database_rows("inc-verify-human", run_id)[0]["state"])
        decided = suite._send_command(client, "inc-verify-human", run_id, "verification_passed")
        assert decided == 202

    state, events, timeline, run_id, _ = _approved(
        "inc-verify-human", VerifyingLLM(HUMAN), 0, after=decide
    )

    assert waited == ["verifying"] and state["state"] == "resolved"
    assert _verifications(events, run_id) == [("intent", "pending"), ("outcome", "success")]
    assert "Verification requested human review." in timeline


def test_a_person_who_verified_first_is_never_overridden() -> None:
    def verify_first(client: httpx.Client, run_id: str) -> None:
        decided = suite._send_command(client, "inc-verify-person", run_id, "verification_passed")
        assert decided == 202
        time.sleep(2.5)

    state, events, _, run_id, _ = _approved(
        "inc-verify-person", VerifyingLLM(FAILED), 1.5, verify_first, wait=False
    )

    assert state["state"] == "resolved"
    assert _verifications(events, run_id) == []
