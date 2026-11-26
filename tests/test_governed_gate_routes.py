"""Each route moved to the gate, on the real application, seeds and PostgreSQL.

Failure modes, written before the gate: a denied request that runs its use case; a denial on an
audited route without its audit row; validation reported after authentication; an inactive
principal accepted; a malformed header accepted; an envelope with other keys, or a 401 without
`WWW-Authenticate`. Per route: one allowed and one denied request, a malformed and an unknown
credential, an inactive principal and, where the route validates, an invalid request with a bad
and with an ungranted credential. The use case the gate admits is observed directly: the allowed
request reaches it once, no refusal reaches it. A route that writes is also checked by its rows,
so a handler that writes outside the use case it hands the gate is caught too: every refusal is
sent before the allowed request, with its own idempotency key and a body built when it is sent,
and the denied caller is one the use case itself would accept where one exists, so that the
refusal would write if it ran; no refusal writes, and the allowed request then does. A route
that audits is checked by the audit rows of each request, found by its `request_id`. The control
plane's own wording (no challenge on its 401s but on consumption limits, refusals before
authorization audited at stage `audit`, a denial hidden as 404) is data of its cases. With
GATE_EVIDENCE set, every request is written there as JSON lines.
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
    # A count the allowed request raises and no refusal changes.
    effect: str | None = None
    # A refusal's own body, from the allowed body and the refusal's label.
    vary: Callable[[Any, str], Any] | None = None
    # An invalid form of the request and the status it gets with a bad or an ungranted key; a
    # `bytes` body is sent as it is, as JSON.
    invalid: tuple[str, Any, int] | None = None
    # The challenge a 401 carries: the control plane sends none, but on consumption limits.
    challenge: str | None = "Bearer"
    # The stage a refusal before authorization is audited at, when not the refusal's own
    # (`authentication`, `validation`): the control plane audits those at `audit`.
    refused_at: str | None = None


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
    # A human without the grant is refused by the gate; the use case refuses an agent itself.
    Case("PUT", CLOSING, "DEMO_HUMAN", "ADMIN_HUMAN", 200, 403, _postmortem,
         effect=POSTMORTEMS, vary=lambda body, label: body | {"content": body["content"]
                                                              | {"summary": label}},
         invalid=(CLOSING, {}, 422)),  # postmortems
    Case("POST", CLOSING + "/reviews", "DEMO_HUMAN", "ADMIN_HUMAN", 201, 403,
         lambda facts: {"version": _version(facts), "outcome": "approved"}, effect=REVIEWS,
         vary=lambda body, label: body | {"outcome": "changes_requested", "comment": label},
         invalid=(CLOSING + "/reviews", {}, 422)),  # postmortems
    Case("GET", CLOSING, "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/incidents/X/postmortem", None, 422)),  # postmortems
    Case("GET", "/v1/incident-memory/changes", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200,
         403),  # postmortems
    # The denied human sends the command in their own name, as the use case requires.
    Case("POST", "/v1/incidents/{mitigating}/runs/{approving}/commands", "DEMO_HUMAN",
         "ADMIN_HUMAN", 202, 403, COMMAND, {"Idempotency-Key": "gate-1021-command"},
         effect=RUN_EVENTS, vary=lambda body, label: body | {"actor_reference": ACTOR | {
             "principal_id": "admin-human" if label == "denied" else "demo-human"}},
         invalid=(RUN + "/commands", {}, 422)),  # runs
    Case("POST", INCIDENT + "/runs", "DEMO_HUMAN", "ADMIN_HUMAN", 201, 403, START, KEY,
         effect=RUNS, invalid=(INCIDENT + "/runs", {}, 422)),  # runs
    Case("GET", "/v1/alerts/{declared}/triage", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         invalid=("/v1/alerts/X/triage", None, 400)),  # triage
    Case("GET", "/v1/alerts/{declared}/triage/context", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200,
         403, invalid=("/v1/alerts/X/triage/context", None, 400)),  # triage
    Case("GET", "/v1/alerts/{alert}/triage/eligible-incidents", "DEMO_HUMAN",
         "RESTRICTED_HARNESS", 200, 403),  # triage
    # The triage service checks the gate's grant again in its transaction: no caller the gate
    # refuses can make it write, so here the rows cannot catch a write outside the use case.
    Case("POST", "/v1/alerts/{alert}/triage/commands", "DEMO_HUMAN", "ADMIN_HUMAN", 201,
         403, lambda facts: DECLARE | {"alert_context": facts["context"]},
         {"Idempotency-Key": "gate-1021-triage-key"}, effect=TRIAGE,
         vary=lambda body, label: body | {"reason": f"Payment fails ({label})."},
         invalid=("/v1/alerts/{alert}/triage/commands",
                  {"operation": "triage_dismiss", "expected_version": 1}, 422)),  # triage
    Case("POST", "/v1/responses", "DEMO_HUMAN", "RESTRICTED_HARNESS", 200, 403,
         {"model": "triage-agent", "input": "Summarize."}, audited=True,
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
    Case("GET", "/v1/audit-events?decision=deny", "ADMIN_HUMAN", "DEMO_HUMAN", 200, 403,
         audited=True, invalid=("/v1/audit-events", None, 422)),  # audit
    Case("GET", "/v1/audit-events/{event}", "ADMIN_HUMAN", "DEMO_HUMAN", 200, 403, audited=True,
         invalid=("/v1/audit-events/{event}?content=1", None, 422)),  # audit
    Case("GET", "/v1/mcp/discovery", "INCIDENT_HARNESS", "RESTRICTED_HARNESS", 200, 403,
         audited=True, audits_401=False,
         invalid=("/v1/mcp/discovery?query=1", None, 422)),  # mcp1
    Case("POST", "/v1/mcp/tools/query_prometheus", "INCIDENT_HARNESS", "RESTRICTED_HARNESS",
         200, 403, {"datasource_uid": "webstore-metrics", "expr": "up", "query_type": "instant",
                    "end_time": "now"}, audited=True, audits_401=False,
         invalid=("/v1/mcp/tools/query_prometheus", {}, 422)),  # mcp2
]  # fmt: skip

# The control plane: every operation of `sre_agent.control.operations`, allowed for the
# administrator and denied to a human without its grant. Control routes audit every request,
# refusals before authorization at stage `audit`, and send no challenge but on consumption limits;
# the credential list hides a denial as 404. Writes target the fixture's `gate-1022-*` resources.
TARGET = "/v1/principals/gate-1022-target"
ALIAS = "/v1/model-aliases/gate-1022-alias"
SKILL = "/v1/skills/gate-1022-skill/1.0.0"
STALE = "2020-01-01T00:00:00+00:00"
# A body nested past the JSON parser's recursion limit is invalid like any body that is not JSON.
NESTED = b"[" * 20000 + b"]" * 20000


def _updated(table: str, column: str, value: str) -> str:
    query = text(f"SELECT updated_at FROM {table} WHERE {column} = :value")  # noqa: S608
    return _sql(query, value=value)[0]["updated_at"].isoformat()


def _named(field: str) -> Callable[[Any, str], Any]:
    """A refusal's body naming its own resource, so it would write if it ran."""
    return lambda body, label: body | {field: _slug(label)}


def _control(method: str, path: str, status: int = 200, body: Any = None, **options: Any) -> Case:
    # Every control POST is idempotent, and so is the consumption-limits PUT.
    idempotent = method == "POST" or path == "/v1/consumption-limits"
    options.setdefault("headers", {"Idempotency-Key": "gate-1022-request"} if idempotent else {})
    options.setdefault("challenge", None)
    return Case(method, path, "ADMIN_HUMAN", "DEMO_HUMAN", status, options.pop("denied", 403),
                body, audited=True, refused_at="audit", **options)  # fmt: skip


def _policy(facts: dict[str, Any]) -> dict[str, Any]:
    [row] = _sql(text("SELECT version FROM consumption_limit_policies WHERE policy_id = 1"))
    return {"expected_version": row["version"], "incident_token_limit": 1022,
            "monthly_usd_limit": "10.22"}  # fmt: skip


VERSION = "SELECT max(version) AS count FROM consumption_limit_policies"
CATALOG = "SELECT count(*) FROM resources WHERE resource_id = '{}' AND status = 'inactive'"
SERVER = {"resource_type": "mcp_server", "resource_id": "gate-1022-server",
          "owner_id": "mcp-platform", "source": "mcp", "source_ref": "mcp-platform/gate-1022",
          "status": "registered", "discoverability": {"display_name": "Gate server",
          "visibility": "private", "description": "Gate.", "tags": ["mcp"]}}  # fmt: skip
CONTROL_CASES = [
    _control("PUT", "/v1/consumption-limits", 200, _policy, effect=VERSION, challenge="Bearer",
             invalid=("/v1/consumption-limits", {"expected_version": -1}, 422)),
    _control("GET", "/v1/consumption-limits", challenge="Bearer"),
    _control("POST", "/v1/principals", 201,
             {"principal_id": "gate-1022-new", "kind": "agent", "display_name": "New"},
             effect="SELECT count(*) FROM principals", vary=_named("principal_id"),
             invalid=("/v1/principals", {}, 422)),
    _control("GET", "/v1/principals", invalid=("/v1/principals?limit=0", None, 422)),
    _control("GET", TARGET, invalid=("/v1/principals/X!", None, 422)),
    _control("PUT", "/v1/principals/gate-1022-status/status", 200,
             lambda facts: {"status": "inactive", "expected_updated_at":
                            _updated("principals", "principal_id", "gate-1022-status")},
             effect="SELECT count(*) FROM principals WHERE status = 'inactive'",
             invalid=("/v1/principals/gate-1022-status/status", {"status": "gone"}, 422)),
    _control("POST", TARGET + "/credentials", 201, {},
             effect="SELECT count(*) FROM credentials",
             invalid=(TARGET + "/credentials", {"expires_at": "soon"}, 422)),
    _control("GET", TARGET + "/credentials", denied=404,
             invalid=(TARGET + "/credentials?limit=500", None, 422)),
    _control("DELETE", "/v1/credentials/{credential}", 204,
             effect="SELECT count(*) FROM credentials WHERE status = 'revoked'",
             invalid=("/v1/credentials/X!", None, 422)),
    _control("POST", "/v1/credentials/{rotating}/rotation", 201, {},
             effect="SELECT count(*) FROM credentials",
             invalid=("/v1/credentials/{rotating}/rotation", {"expires_at": 3}, 422)),
    # The grant goes to the fixture's principal, so no case's denied caller gains it.
    _control("POST", "/v1/grants", 201,
             {"grant_id": "gate-1022-grant", "principal_id": "gate-1022-target",
              "action": "admin.read", "effect": "allow",
              "resource": {"resource_type": "administrative_control", "resource_id": "grants"}},
             effect="SELECT count(*) FROM grants", vary=_named("grant_id"),
             invalid=("/v1/grants", NESTED, 422)),
    _control("GET", "/v1/grants?principal_id=gate-1022-target",
             invalid=("/v1/grants", None, 422)),
    _control("DELETE", "/v1/grants/{grant}", 204,
             effect="SELECT count(*) FROM grants WHERE status = 'revoked'",
             invalid=("/v1/grants/X!", None, 422)),
    _control("POST", "/v1/model-aliases", 201,
             {"model_alias_id": "gate-1022-new", "alias": "gate-1022-new",
              "concrete_model": "openai/gpt-4o-mini", "router": "openrouter",
              "inference_provider": "openai"},
             effect="SELECT count(*) FROM resources", vary=lambda body, label: body | {
                 "model_alias_id": _slug(label), "alias": _slug(label)},
             invalid=("/v1/model-aliases", {"model_alias_id": "x"}, 422)),
    _control("GET", "/v1/model-aliases", invalid=("/v1/model-aliases?limit=x", None, 422)),
    _control("GET", ALIAS, invalid=("/v1/model-aliases/X!", None, 422)),
    _control("PUT", ALIAS + "/assignment", 200,
             lambda facts: {"concrete_model": "openai/gpt-4o", "router": "openrouter",
                            "inference_provider": "openai", "expected_updated_at":
                            _updated("resources", "resource_id", "gate-1022-alias")},
             effect="SELECT count(*) FROM resources WHERE concrete_model = "
                                "'openai/gpt-4o' AND resource_id = 'gate-1022-alias'",
             invalid=(ALIAS + "/assignment", {"concrete_model": "openai/gpt-4o"}, 422)),
    _control("PUT", ALIAS + "/status", 200,
             lambda facts: {"status": "inactive", "expected_updated_at":
                            _updated("resources", "resource_id", "gate-1022-alias")},
             effect=CATALOG.format("gate-1022-alias"),
             invalid=(ALIAS + "/status", {"status": "gone"}, 422)),
    _control("POST", "/v1/catalog/resources", 201, SERVER,
             effect="SELECT count(*) FROM resources", vary=lambda body, label: body | {
                 "resource_id": _slug(label), "source_ref": "mcp-platform/" + _slug(label)},
             invalid=("/v1/catalog/resources", {"resource_type": "mcp_server"}, 422)),
    _control("GET", "/v1/catalog/resources",
             invalid=("/v1/catalog/resources?resource_type=nope", None, 422)),
    _control("GET", "/v1/catalog/resources/skill/gate-1022-skill@1.0.0",
             invalid=("/v1/catalog/resources/nope/x", None, 422)),
    _control("POST", "/v1/skills/versions", 201,
             {"skill_id": "gate-1022-new", "version": "1.0.0", "owner_id": "demo-human",
              "manifest": {"display_name": "New", "description": "A gate fixture.",
                           "instructions": "Read the gate.", "dependencies": []}},
             effect="SELECT count(*) FROM skill_versions", vary=_named("skill_id"),
             invalid=("/v1/skills/versions", {"skill_id": "X"}, 422)),
    _control("GET", SKILL, invalid=("/v1/skills/X/1.0.0", None, 422)),
    _control("PUT", SKILL + "/status", 200,
             lambda facts: {"status": "inactive", "expected_updated_at":
                            _updated("resources", "resource_id", "gate-1022-skill@1.0.0")},
             effect=CATALOG.format("gate-1022-skill@1.0.0"),
             invalid=(SKILL + "/status", {"status": "draft"}, 422)),
    _control("GET", SKILL + "/status", invalid=("/v1/skills/X/1.0.0/status", None, 422)),
    _control("POST", "/v1/bok/collections/versions", 201,
             {"collection_id": "gate-1022-new", "version": "1.0.0", "display_name": "New",
              "description": "Gate.", "documents": [{"document_id": "doc-1", "title": "Doc",
              "source_ref": "https://example.invalid/d", "chunks": [{"section_id": "steps",
              "chunk_index": 0, "content": "Rotate."}]}]},
             effect="SELECT count(*) FROM bok_collection_versions", vary=_named("collection_id"),
             invalid=("/v1/bok/collections/versions", {"collection_id": "x"}, 422)),
    _control("GET", "/v1/bok/collections/otel-demo-store/versions/1.0.0",
             invalid=("/v1/bok/collections/X/versions/1.0.0", None, 422)),
]  # fmt: skip
CASES += CONTROL_CASES


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
    return facts | _control_facts(client)


def _control_facts(client: TestClient) -> dict[str, Any]:
    """What the control cases act on: two principals, two credentials of the first (one to
    revoke, one to rotate), a grant to revoke, a model alias and an active skill."""
    admin = {"Authorization": "Bearer " + KEYS["ADMIN_HUMAN"]}

    def create(path: str, body: dict[str, Any], key: str) -> dict[str, Any]:
        created = client.post(path, json=body, headers=admin | {"Idempotency-Key": key})
        assert created.status_code == 201, created.text
        return created.json()

    for principal in ("gate-1022-target", "gate-1022-status"):
        create("/v1/principals", {"principal_id": principal, "kind": "human",
                                  "display_name": "Gate"}, f"{principal}-create")  # fmt: skip
    credentials = [
        create(TARGET + "/credentials", {}, f"gate-1022-credential-{n}")["credential"]
        for n in (1, 2)
    ]
    grant = {"grant_id": "gate-1022-revoked", "principal_id": "gate-1022-target",
             "action": "admin.read", "effect": "allow",
             "resource": {"resource_type": "administrative_control",
                          "resource_id": "principals"}}  # fmt: skip
    create("/v1/grants", grant, "gate-1022-grant-create")
    alias = {"model_alias_id": "gate-1022-alias", "alias": "gate-1022-alias",
             "concrete_model": "openai/gpt-4o-mini", "router": "openrouter",
             "inference_provider": "openai"}  # fmt: skip
    create("/v1/model-aliases", alias, "gate-1022-alias-create")
    skill = {"skill_id": "gate-1022-skill", "version": "1.0.0", "owner_id": "demo-human",
             "manifest": {"display_name": "Gate", "description": "A gate fixture.",
                          "instructions": "Read the gate.", "dependencies": []}}  # fmt: skip
    create("/v1/skills/versions", skill, "gate-1022-skill-create")
    _sql(text("UPDATE resources SET status = 'active' WHERE resource_id = 'gate-1022-skill@1.0.0'"))
    return {
        "credential": credentials[0]["credential_id"],
        "rotating": credentials[1]["credential_id"],
        "grant": grant["grant_id"],
    }


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
        if isinstance(body, bytes):
            headers["Content-Type"] = "application/json"
            response = client.request(case.method, url, headers=headers, content=body)
        else:
            response = client.request(case.method, url, headers=headers, json=body)
        answer = None
        if response.status_code != 204:
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

    def body(label: str) -> Any:
        """The request's body as of now: the refusals go first, each one a request that would
        write if it ran, and the allowed request last."""
        current = case.body(facts) if callable(case.body) else case.body
        return current if case.vary is None or label == "allowed" else case.vary(current, label)

    refusals = [
        ("denied", "Bearer " + KEYS[case.denied], case.denied_status),
        ("malformed", "Basic " + KEYS[case.allowed], 401),
        ("unknown", "Bearer sre_unkn0123456789abcdefghijklmnopqrstuv", 401),
    ]
    for label, authorization, status in refusals:
        refused, effect, audit = send(label, path, body(label), authorization)
        assert refused.status_code == status, (label, refused.text)
        assert set(refused.json()) == {"error", "request_id", "retryable"}
        assert not effect, f"{label}: the request wrote"
        if status == 401:
            assert refused.headers.get("www-authenticate") == case.challenge
        if case.audited and label == "denied":
            assert [(row["stage"], row["outcome"]) for row in audit] == [
                ("authorization", "denied")
            ], audit
        if case.audited and status == 401:
            expected = [(case.refused_at or "authentication", 401)] if case.audits_401 else []
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
                stage = case.refused_at or "validation"
                expected = [(stage, status)] if case.audits_invalid else []
                assert [(row["stage"], row["response_status"]) for row in audit] == expected, audit

    principal = {"principal": case.allowed.lower().replace("_", "-")}
    _sql(
        text("UPDATE principals SET status = 'inactive' WHERE principal_id = :principal"),
        **principal,
    )
    try:
        own = "Bearer " + KEYS[case.allowed]
        refused = body("inactive principal")
        inactive, effect, audit = send("inactive principal", path, refused, own)
    finally:
        _sql(
            text("UPDATE principals SET status = 'active' WHERE principal_id = :principal"),
            **principal,
        )
    assert inactive.status_code == 401 and not effect
    if case.audited:
        assert [(row["stage"], row["response_status"]) for row in audit] == [
            (case.refused_at or "authentication", 401)
        ], audit

    allowed, effect, audit = send("allowed", path, body("allowed"), "Bearer " + KEYS[case.allowed])
    assert allowed.status_code == case.allowed_status, allowed.text
    if case.effect is not None:
        assert effect and effect > 0, "the allowed request wrote nothing"
    if case.audited:
        assert [row["outcome"] for row in audit] == ["success"], audit
