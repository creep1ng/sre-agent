"""Each route moved to the gate, on the real application, seeds and PostgreSQL.

Failure modes, written before the gate: a denied request that runs its use case; a denial on an
audited route without its audit row; validation reported after authentication; an inactive
principal accepted; a malformed header accepted; an envelope with other keys, or a 401 without
`WWW-Authenticate`. Per route: one allowed and one denied request, a malformed and an unknown
credential, an inactive principal and, where the route validates, an invalid request with a bad
and with an ungranted credential. The use case the gate admits is observed directly: the allowed
request reaches it once, no refusal reaches it. A route that writes is also checked by its rows:
the allowed request writes, no refusal does, and each refusal carries its own body and
idempotency key, so it is not a replay of the allowed one. A route that audits is checked by the
audit rows of each request, found by its `request_id`. With GATE_EVIDENCE set, every request is
written there as JSON lines.
"""

import asyncio
import json
import os
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from database_support import migrate_database
from fastapi.testclient import TestClient
from sqlalchemy import text

from sre_agent.application import create_application
from sre_agent.gate import pipeline
from sre_agent.gate.pipeline import Admission, Gate
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.seeds import SeedSettings, seed, seed_mcp_demo
from sre_agent.settings import Settings

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from provision_demo import provision_demo  # noqa: E402
from provision_incident_workflow import build_service  # noqa: E402

URL = os.environ["TEST_DATABASE_URL"]
NAMES = ("ADMIN_HUMAN", "DEMO_HUMAN", "INCIDENT_HARNESS", "RESTRICTED_HARNESS")
KEYS = {
    name: "sre_" + prefix + "0123456789abcdefghijklmnopqrstuv"
    for name, prefix in zip(NAMES, ("admin", "human", "agent", "deny0"), strict=True)
}
# Not a seed key: the deploy-executor's credential, which alone holds change.write.
KEYS["DEPLOY_EXECUTOR"] = "sre_exec0123456789abcdefghijklmnopqrstuv"
ROUTE = (("MODEL", "openai/gpt-4o-mini"), ("PROVIDER", "openai"))
SECRET = "grafana-intake-" + "s" * 24
GRANT = text(
    "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, effect,"
    " status, created_at) VALUES (:grant, 'incident-harness', :action, :kind, :resource,"
    " 'allow', 'active', now())"
)
AUDIT_SQL = text(
    "SELECT operation, stage, outcome, response_status, reason_code, authorization_denial_cause"
    " FROM audit_events WHERE correlation->>'request_id' = :request_id ORDER BY occurred_at"
)
# What each writing route writes, counted before and after every request.
RUNS = "SELECT count(*) FROM incident.runs"
CHANGES = "SELECT count(*) FROM incident.change_events"
TRIAGE = "SELECT count(*) FROM alert_triage WHERE status <> 'open'"
RUN_EVENTS = "SELECT count(*) FROM incident.run_events"
POSTMORTEMS = "SELECT count(*) FROM incident.postmortem_revisions"
REVIEWS = "SELECT count(*) FROM incident.postmortem_reviews"
# The store requires a run's updated_at at or after its incident's created_at.
SEEDED_AT = datetime.now(UTC) - timedelta(hours=1)


@dataclass
class Case:
    method: str
    # Formatted with the fixture's facts: {incident}, {run}, {alert}, {declared}, {chunk},
    # {event}; a callable body is called with the facts.
    path: str
    allowed: str
    denied: str
    allowed_status: int
    denied_status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    # The route writes the terminal audit; `audits_401` when it also audits an unknown or a
    # malformed credential, `audits_invalid` when it audits a validation refusal.
    audited: bool = False
    audits_401: bool = True
    audits_invalid: bool = True
    # Whether a 401 carries `WWW-Authenticate: Bearer`.
    challenge: bool = True
    # A count the allowed request raises and no refusal changes.
    effect: str | None = None
    # A refusal's own body, from the allowed body and the refusal's label.
    vary: Callable[[Any, str], Any] | None = None
    # An invalid form of the request and the status it gets with a bad or an ungranted key.
    invalid: tuple[str, Any, int] | None = None


CHANGE = {"source": "ci", "external_id": "run-1021", "service": "checkout", "kind": "deploy"}
INCIDENT = "/v1/incidents/{incident}"
CLOSING = "/v1/incidents/{closing}/postmortem"
RUN = INCIDENT + "/runs/{run}"
KEY = {"Idempotency-Key": "gate-1021-request"}
START = {"workflow_version": "1.0.0", "objective": "investigate"}
ACTOR = {"reference_version": "1.0.0", "principal_id": "demo-human"}
COMMAND = {"command": "approve_mitigation", "actor": "human", "actor_reference": ACTOR,
           "expected_incident_version": 0}  # fmt: skip
DECLARE = {"operation": "triage_declare", "expected_version": 1, "reason": "Payment fails.",
           "severity": "sev1", "impact": "Customers cannot pay."}  # fmt: skip
BOK = "/v1/bok/collections/otel-demo-store/versions/1.0.0"

SEEDED = Path(__file__).parents[1] / "agent/fixtures/incidents/otel-payment-failure"
MITIGATION = {"mitigation_id": "mit_gate", "description": "d", "steps": ["s"], "risk": "low",
              "verification_check": "v", "approval_status": "pending", "execution_mode": "human",
              "created_by": "agent", "created_at": "2026-11-01T00:00:00Z"}  # fmt: skip


def _postmortem(facts: dict[str, Any]) -> dict[str, Any]:
    """The next version of the seeded postmortem, citing the event that opened it."""
    cited = [{"event_id": facts["opened"], "description": "Postmortem opened."}]
    content = {"summary": "s", "impact": "i", "strategy": "s", "verification": "v",
               "cause": {"statement": "c", "certainty": "unknown"}, "timeline": cited,
               "actions_taken": [], "pending": [], "unknowns": []}  # fmt: skip
    return {"expected_version": _version(facts), "content": content}


def _version(facts: dict[str, Any]) -> int:
    query = text("SELECT version FROM incident.postmortems WHERE incident_id = :incident")
    return next((row["version"] for row in _sql(query, incident=facts["closing"])), 0)


def _seed(incident: str, state: str, run: dict[str, Any]) -> str:
    """An incident in `state` with one run, stored as the incident tests store theirs."""
    document = yaml.safe_load((SEEDED / "initial-state.yaml").read_text())
    document |= {"state": state, "incident_id": incident, "severity": "sev2",
                 "mitigation_strategy": MITIGATION}  # fmt: skip
    run_id = "run_" + incident.replace("-", "")

    async def store() -> None:
        database = Database(URL)
        try:
            async with PostgresIncidentUnitOfWork(database) as work:
                await work.incidents.add(incident, document, now=SEEDED_AT)
                state_of_run = run | {"workflow_version": "1.0.0", "current_state": state}
                await work.runs.add(run_id, incident, state_of_run, now=SEEDED_AT)
        finally:
            await database.dispose()

    asyncio.run(store())
    return run_id


CASES = [
    Case("GET", "/v1/alerts", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403),  # alerts
    Case("POST", "/v1/changes", "DEPLOY_EXECUTOR", "DEMO_HUMAN", 201, 403, CHANGE,
         effect=CHANGES, vary=lambda body, label: body | {"external_id": _slug(label)},
         invalid=("/v1/changes", {}, 422)),  # changes
    Case("GET", "/v1/changes", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/changes?limit=0", None, 422)),  # changes
    Case("GET", "/v1/event-decisions", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/event-decisions?limit=0", None, 422)),  # changes
    Case("GET", RUN + "/context", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=(INCIDENT + "/runs/bad/context", None, 422)),  # context
    Case("GET", "/v1/action-catalog", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403),  # context
    Case("GET", "/v1/incidents", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/incidents?limit=0", None, 422)),  # incidents
    Case("GET", INCIDENT, "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/incidents/X", None, 422)),  # incidents
    Case("GET", INCIDENT + "/timeline", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=(INCIDENT + "/timeline?limit=0", None, 422)),  # incidents
    Case("GET", INCIDENT + "/snapshot", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=(INCIDENT + "/snapshot?run_id=bad", None, 422)),  # incidents
    Case("GET", RUN, "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=(INCIDENT + "/runs/bad", None, 422)),  # incidents
    Case("GET", RUN + "/events", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=(RUN + "/events?limit=0", None, 422)),  # incidents
    Case("PUT", CLOSING, "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403, _postmortem,
         effect=POSTMORTEMS, vary=lambda body, label: body | {"content": body["content"]
                                                              | {"summary": label}},
         invalid=(CLOSING, {}, 422)),  # postmortems
    Case("POST", CLOSING + "/reviews", "DEMO_HUMAN", "RESTRICTED_HARNESS", 201, 403,
         lambda facts: {"version": _version(facts), "outcome": "approved"}, effect=REVIEWS,
         vary=lambda body, label: body | {"outcome": "changes_requested", "comment": label},
         invalid=(CLOSING + "/reviews", {}, 422)),  # postmortems
    Case("GET", CLOSING, "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/incidents/X/postmortem", None, 422)),  # postmortems
    Case("GET", "/v1/incident-memory/changes", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200,
         403),  # postmortems
    Case("POST", "/v1/incidents/{mitigating}/runs/{approving}/commands", "DEMO_HUMAN",
         "RESTRICTED_HARNESS", 202, 403, COMMAND, {"Idempotency-Key": "gate-1021-command"},
         effect=RUN_EVENTS, invalid=(RUN + "/commands", {}, 422)),  # runs
    Case("POST", INCIDENT + "/runs", "DEMO_HUMAN", "RESTRICTED_HARNESS", 201, 403, START, KEY,
         effect=RUNS, invalid=(INCIDENT + "/runs", {}, 422)),  # runs
    Case("GET", "/v1/alerts/{declared}/triage", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/alerts/X/triage", None, 400)),  # triage
    Case("GET", "/v1/alerts/{declared}/triage/context", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200,
         403, invalid=("/v1/alerts/X/triage/context", None, 400)),  # triage
    Case("GET", "/v1/alerts/{alert}/triage/eligible-incidents", "DEMO_HUMAN",
         "RESTRICTED_HARNESS", 200, 403),  # triage
    Case("POST", "/v1/alerts/{alert}/triage/commands", "DEMO_HUMAN", "RESTRICTED_HARNESS", 201,
         403, lambda facts: DECLARE | {"alert_context": facts["context"]},
         {"Idempotency-Key": "gate-1021-triage-key"}, effect=TRIAGE,
         vary=lambda body, label: body | {"reason": f"Payment fails ({label})."},
         invalid=("/v1/alerts/{alert}/triage/commands",
                  {"operation": "triage_dismiss", "expected_version": 1}, 422)),  # triage
    Case("POST", "/v1/responses", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         {"model": "triage-agent", "input": "Summarize."}, audited=True, challenge=False,
         invalid=("/v1/responses", {"model": "X"}, 422)),  # responses
    Case("POST", BOK + "/search", "INCIDENT_HARNESS", "DEMO_HUMAN", 200, 403,
         {"query": "checkout"}, audited=True, audits_401=False,
         invalid=(BOK + "/search", {}, 422), audits_invalid=False),  # bok
    Case("GET", BOK + "/chunks/{chunk}", "INCIDENT_HARNESS", "DEMO_HUMAN", 200, 403,
         audited=True, audits_401=False),  # bok
    Case("GET", "/v1/skills/gate-skill/1.0.0/resolve", "INCIDENT_HARNESS", "DEMO_HUMAN", 200,
         404, audited=True, invalid=("/v1/skills/X/1.0.0/resolve", None, 422)),  # skills
    Case("GET", "/v1/usage/consumption?month=2026-11", "ADMIN_HUMAN", "DEMO_HUMAN", 200, 403,
         audited=True, invalid=("/v1/usage/consumption?from=x", None, 422)),  # usage1
    Case("GET", "/v1/usage/requests?month=2026-11", "ADMIN_HUMAN", "DEMO_HUMAN", 200, 403,
         audited=True, invalid=("/v1/usage/requests?from=x", None, 422)),  # usage2
]  # fmt: skip


class Provider:
    """A model provider that answers every request; the gate is what is under test."""

    async def create(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(
            response_id="resp_gate1021", model=request.model, text="ok", provider=request.provider
        )


class Upstream:
    """A Grafana MCP upstream with an empty Prometheus vector."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return {"data": {"resultType": "vector", "result": []}}


def _sql(statement: Any, **values: Any) -> list[dict[str, Any]]:
    async def run() -> list[dict[str, Any]]:
        database = Database(URL)
        try:
            async with database.transaction() as session:
                result = await session.execute(statement, values)
                return [dict(row) for row in result.mappings()] if result.returns_rows else []
        finally:
            await database.dispose()

    return asyncio.run(run())


def _count(query: str | None) -> int | None:
    return _sql(text(query))[0]["count"] if query else None


def _grafana(service: str) -> dict[str, Any]:
    starts = (datetime.now(UTC) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    alert = {
        "status": "firing", "fingerprint": f"gate-{service}", "startsAt": starts,
        "endsAt": "0001-01-01T00:00:00Z",
        "labels": {"alertname": "gate-error-rate", "service_name": service, "severity": "critical"},
        "annotations": {"summary": f"{service}: 100% of spans failed."},
    }  # fmt: skip
    return {"groupKey": f"gate:{service}", "status": "firing", "alerts": [alert]}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    migrate_database(URL)
    routes = {f"{a}_AGENT_{p}": v for a in ("TRIAGE", "REMEDIATION") for p, v in ROUTE}
    settings = SeedSettings.from_environment(
        {f"{name}_API_KEY": KEYS[name] for name in NAMES} | routes
    )

    async def prepare() -> None:
        database = Database(URL)
        try:
            await seed(database, settings)
            await seed_mcp_demo(database)
            await provision_demo(
                build_service(database, b"x" * 32),
                "Bearer " + KEYS["ADMIN_HUMAN"],
                KEYS["DEPLOY_EXECUTOR"],
            )
        finally:
            await database.dispose()

    asyncio.run(prepare())
    app = create_application(
        Settings(
            database_url=URL,
            audit_hmac_key="x" * 32,
            alert_intake_secret=SECRET,
            alert_intake_principal_id=None,
        ),
        llm_provider=Provider(),
        mcp_client=Upstream(),
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def facts(client: TestClient) -> dict[str, Any]:
    """An incident with a run, a second untriaged alert, a BoK chunk and an audit event."""
    human = {"Authorization": "Bearer " + KEYS["DEMO_HUMAN"]}
    for service in ("checkout", "payment"):
        delivered = client.post(
            "/v1/alert-intake/grafana",
            json=_grafana(service),
            headers={"Authorization": "Bearer " + SECRET},
        )
        assert delivered.status_code == 200, delivered.text
    listed = client.get("/v1/alerts", headers=human).json()["alerts"]
    alerts = {item["service"]: item for item in listed}
    first, second = alerts["checkout"], alerts["payment"]

    def context(alert: dict[str, Any]) -> dict[str, Any]:
        fields = ("service", "summary", "observed_at", "source", "severity")
        return {key: alert[key] for key in fields}

    declared = client.post(
        f"/v1/alerts/{first['alert_id']}/triage/commands",
        headers=human | {"Idempotency-Key": "gate-1021-declare"},
        json=DECLARE | {"alert_context": context(first)},
    )
    assert declared.status_code == 201, declared.text
    incident = declared.json()["incident_id"]
    started = client.post(
        f"/v1/incidents/{incident}/runs",
        headers=human | {"Idempotency-Key": "gate-1021-first-run"},
        json=START,
    )
    assert started.status_code == 201, started.text
    published = client.post(
        "/v1/skills/versions",
        json={"skill_id": "gate-skill", "version": "1.0.0", "owner_id": "demo-human",
              "manifest": {"display_name": "Gate skill", "description": "A gate fixture.",
                           "instructions": "Read the gate.", "dependencies": []}},
        headers={"Authorization": "Bearer " + KEYS["ADMIN_HUMAN"],
                 "Idempotency-Key": "publish-gate-skill-1021"},
    )  # fmt: skip
    assert published.status_code == 201, published.text
    _sql(text("UPDATE resources SET status = 'active' WHERE resource_id = 'gate-skill@1.0.0'"))
    for action, kind, resource in (
        ("invoke", "skill", "gate-skill@1.0.0"),
        ("bok.read", "bok_collection", "otel-demo-store@1.0.0"),
    ):
        _sql(GRANT, grant="grant-gate-" + action.replace(".", "-"), action=action, kind=kind,
             resource=resource)  # fmt: skip
    [chunk] = _sql(
        text(
            "SELECT document_id, section_id, chunk_index FROM bok_section_chunks"
            " WHERE collection_id = 'otel-demo-store' AND version = '1.0.0'"
            " ORDER BY document_id, section_id, chunk_index LIMIT 1"
        )
    )
    [event] = _sql(text("SELECT event_id FROM audit_events ORDER BY occurred_at LIMIT 1"))
    facts = {
        "incident": incident,
        "run": started.json()["run_id"],
        "alert": second["alert_id"],
        "declared": first["alert_id"],
        "context": context(second),
        "chunk": f"{chunk['document_id']}/{chunk['section_id']}/{chunk['chunk_index']}",
        "event": event["event_id"],
    }
    # A resolved incident whose postmortem the operator opened and wrote once.
    facts["closing"] = "inc-gate-closing"
    _seed(facts["closing"], "resolved", {"status": "completed"})
    opened = client.post(
        f"/v1/incidents/{facts['closing']}/runs",
        headers=human | {"Idempotency-Key": "gate-1021-postmortem"},
        json=START | {"objective": "postmortem"},
    )
    assert opened.status_code == 201, opened.text
    query = "SELECT event_id FROM incident.run_events WHERE incident_id = :incident LIMIT 1"
    facts["opened"] = _sql(text(query), incident=facts["closing"])[0]["event_id"]
    written = client.put(CLOSING.format(**facts), headers=human, json=_postmortem(facts))
    assert written.status_code == 201, written.text
    # An incident whose run awaits the operator's approval of its mitigation.
    facts["mitigating"] = "inc-gate-mitigating"
    pending = {"status": "awaiting_human", "pending_command": "approve_mitigation"}
    facts["approving"] = _seed(facts["mitigating"], "mitigating", pending)
    return facts


def _slug(label: str) -> str:
    return "gate-1021-" + label.replace(",", "").replace(" ", "-")


def _record(line: dict[str, Any]) -> None:
    if path := os.environ.get("GATE_EVIDENCE"):
        with open(path, "a", encoding="utf-8") as evidence:
            evidence.write(json.dumps(line, sort_keys=True) + "\n")


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.method} {case.path}")
def test_route_refuses_before_its_use_case_and_audits_where_it_audits(
    client: TestClient, facts: dict[str, Any], case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every use case the gate admits, observed where the gate calls it.
    admitted: list[Admission] = []
    run = Gate.run

    def observed(gate: Gate[Any], operation: Any, authorization: Any, scope: Any,
                 use_case: Any, **options: Any) -> Any:  # fmt: skip
        async def reached(admission: Admission, request: Any) -> Any:
            admitted.append(admission)
            return await use_case(admission, request)

        return run(gate, operation, authorization, scope, reached, **options)

    monkeypatch.setattr(pipeline.Gate, "run", observed)
    path = case.path.format(**facts)

    def send(label: str, url: str, body: Any, authorization: str | None) -> Any:
        headers = case.headers | ({"Authorization": authorization} if authorization else {})
        if label != "allowed" and "Idempotency-Key" in headers:
            headers["Idempotency-Key"] += "-" + _slug(label)
        before, written = len(admitted), _count(case.effect)
        response = client.request(case.method, url, headers=headers, json=body)
        assert response.headers["content-type"].startswith("application/json"), response.text
        answer = response.json()
        request_id = answer.get("request_id") if isinstance(answer, dict) else None
        if request_id is None and len(admitted) > before:
            request_id = str(admitted[-1].request_id)
        audit = _sql(AUDIT_SQL, request_id=str(request_id)) if request_id else []
        effect = None if case.effect is None else _count(case.effect) - written  # type: ignore[operator]
        _record(
            {
                "route": f"{case.method} {case.path}",
                "request": label,
                "status": response.status_code,
                "www_authenticate": response.headers.get("www-authenticate"),
                "error": answer.get("error") if isinstance(answer, dict) else None,
                "request_id": request_id,
                "use_case_reached": len(admitted) - before,
                "rows_written": effect,
                "audit_rows": audit,
            }
        )
        assert len(admitted) - before == (label == "allowed"), f"{label}: use case reached"
        return response, effect, audit

    def vary(body: Any, label: str) -> Any:
        return body if case.vary is None else case.vary(body, label)

    body = case.body(facts) if callable(case.body) else case.body
    allowed, effect, audit = send("allowed", path, body, "Bearer " + KEYS[case.allowed])
    assert allowed.status_code == case.allowed_status, allowed.text
    if case.effect is not None:
        assert effect and effect > 0, "the allowed request wrote nothing"
    if case.audited:
        assert [row["outcome"] for row in audit] == ["success"], audit

    refusals = [
        ("denied", "Bearer " + KEYS[case.denied], case.denied_status),
        ("malformed", "Basic " + KEYS[case.allowed], 401),
        ("unknown", "Bearer sre_unkn0123456789abcdefghijklmnopqrstuv", 401),
    ]
    for label, authorization, status in refusals:
        refused, effect, audit = send(label, path, vary(body, label), authorization)
        assert refused.status_code == status, (label, refused.text)
        assert set(refused.json()) == {"error", "request_id", "retryable"}
        assert not effect, f"{label}: the request wrote"
        if status == 401 and case.challenge:
            assert refused.headers["www-authenticate"] == "Bearer"
        if case.audited and label == "denied":
            assert [(row["stage"], row["outcome"]) for row in audit] == [
                ("authorization", "denied")
            ], audit
        if case.audited and status == 401:
            expected = [("authentication", 401)] if case.audits_401 else []
            assert [(row["stage"], row["response_status"]) for row in audit] == expected, audit

    if case.invalid is not None:
        url, invalid, status = case.invalid
        url = url.format(**facts)
        ungranted = "Bearer " + KEYS[case.denied]
        for label, key in (("invalid, bad key", "Basic x"), ("invalid, ungranted", ungranted)):
            refused, effect, audit = send(label, url, invalid, key)
            assert refused.status_code == status, (label, refused.text)
            assert not effect, f"{label}: the request wrote"
            if case.audited:
                expected = [("validation", status)] if case.audits_invalid else []
                assert [(row["stage"], row["response_status"]) for row in audit] == expected, audit

    principal = {"principal": case.allowed.lower().replace("_", "-")}
    _sql(
        text("UPDATE principals SET status = 'inactive' WHERE principal_id = :principal"),
        **principal,
    )
    try:
        own = "Bearer " + KEYS[case.allowed]
        refused = vary(body, "inactive principal")
        inactive, effect, audit = send("inactive principal", path, refused, own)
    finally:
        _sql(
            text("UPDATE principals SET status = 'active' WHERE principal_id = :principal"),
            **principal,
        )
    assert inactive.status_code == 401 and not effect
    if case.audited:
        assert [(row["stage"], row["response_status"]) for row in audit] == [
            ("authentication", 401)
        ], audit
