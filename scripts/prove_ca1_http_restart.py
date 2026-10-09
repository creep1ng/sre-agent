"""Prove that a run created only through HTTP survives an API restart.

Detects pre-existing runs, invalid HTTP schemas/status, broken SQL/HTTP correlation,
changed restart reads, duplicate replay/resume, and unauthorized state/event reads.

Run from the checks container with `prepare`, `before`, or `after`. The evidence
directory is expected to be a mounted path at /evidence. Secrets are never saved
or printed; only synthetic request data and selected persistence facts are stored.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import psycopg
from jsonschema import Draft202012Validator, FormatChecker
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import validate_run_api  # noqa: E402

EVIDENCE = Path("/evidence")
INCIDENT_ID = os.getenv("CA1_INCIDENT_ID", "inc-ca1-http-restart")
IDEMPOTENCY_KEY = os.getenv("CA1_IDEMPOTENCY_KEY", f"ca1-http-restart-{uuid4().hex}")
RESUME_KEY = "ca1-http-restart-resume-v1"
START_BODY = {"workflow_version": "1.0.0", "objective": "triage"}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def env(name: str) -> str:
    value = os.getenv(name)
    require(bool(value), f"required environment variable {name} is missing")
    return value or ""


def validate_schema(schema: dict, value: Any, name: str) -> None:
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    require(not errors, f"{name} schema rejected response ({len(errors)} violation(s))")


def validate(name: str, value: Any) -> None:
    validate_schema(validate_run_api.load_yaml(validate_run_api.SCHEMAS[name]), value, name)


def compare(label: str, expected: Any, actual: Any, evidence: dict) -> None:
    if expected != actual:
        evidence["failure"] = {"check": label, "expected": expected, "observed": actual}
        write_artifact("ca1-after.json", evidence)
        raise AssertionError(
            f"{label} differs; expected/observed preserved in /evidence/ca1-after.json"
        )


def call(
    client: httpx.Client,
    method: str,
    suffix: str,
    status: int,
    label: str,
    *,
    key: str | None = None,
    body: dict | None = None,
    token: str | None = None,
    schema: str | None = None,
) -> Any:
    """Make a real HTTP request and validate its status, JSON, and optional schema."""
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    if key is not None:
        headers["Idempotency-Key"] = key
    try:
        response = client.request(
            method,
            env("API_URL").rstrip("/") + f"/v1/incidents/{quote(INCIDENT_ID, safe='')}{suffix}",
            headers=headers,
            json=body,
        )
    except Exception as exc:  # avoid leaking URL, headers, or credentials in exceptions
        raise AssertionError(f"HTTP {method} failed ({type(exc).__name__})") from None
    require(
        response.status_code == status,
        f"{label}: expected HTTP {status}, got {response.status_code}",
    )
    try:
        value = response.json()
    except ValueError:
        raise AssertionError(f"{label}: response was not JSON") from None
    if schema is not None:
        validate(schema, value)
    return value


def read_run(client: httpx.Client, run_id: str, token: str, label: str) -> tuple[dict, dict]:
    """Read the same public state and event surface before and after restart."""
    root = f"/runs/{run_id}"
    state = call(client, "GET", root, 200, f"{label} state", token=token, schema="run-state")
    events = call(
        client, "GET", root + "/events", 200, f"{label} events", token=token, schema="run-event"
    )
    return state, events


def capture_sql(
    *, run_id: str | None = None, missing_ok: bool = False, require_empty: bool = False
) -> dict[str, Any] | None:
    dsn = env("DATABASE_URL")
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            incident = conn.execute(
                "SELECT incident_id,state,version,created_at,updated_at "
                "FROM incident.incidents WHERE incident_id=%s",
                (INCIDENT_ID,),
            ).fetchone()
            if incident is None:
                require(missing_ok, "SQL incident row is missing")
                return None
            runs = conn.execute(
                "SELECT run_id,incident_id,state,version,created_at,updated_at "
                "FROM incident.runs WHERE incident_id=%s ORDER BY run_id",
                (INCIDENT_ID,),
            ).fetchall()
            if run_id is not None:
                require(
                    len(runs) == 1 and runs[0]["run_id"] == run_id,
                    "SQL run identity/count differs from HTTP-created identity",
                )
            require(not require_empty or not runs, "SQL incident already has run rows")
            queries = {
                "events": "SELECT event_id,incident_id,run_id,turn_id,sequence,kind,payload,"
                "occurred_at "
                "FROM incident.run_events WHERE incident_id=%s ORDER BY run_id,sequence,event_id",
                "snapshots": "SELECT snapshot_id,incident_id,run_id,version,event_sequence,"
                "incident_state,"
                "run_state,created_at FROM incident.snapshots WHERE incident_id=%s "
                "ORDER BY run_id,version,snapshot_id",
                "transition_commits": "SELECT incident_id,command_id,payload_sha256,result,"
                "committed_at "
                "FROM incident.transition_commits WHERE incident_id=%s ORDER BY command_id",
            }
            rows = {
                name: conn.execute(query, (INCIDENT_ID,)).fetchall()
                for name, query in queries.items()
            }
            grants = conn.execute(
                "SELECT count(*) AS count FROM grants WHERE principal_id='demo-human' "
                "AND resource_type='incident_workflow' AND resource_id='incident-response' "
                "AND status='active' AND action IN ('run.read','run.start')"
            ).fetchone()["count"]
            credentials = conn.execute(
                "SELECT count(*) AS count FROM credentials "
                "WHERE principal_id IN ('demo-human','restricted-harness') AND status='active'"
            ).fetchone()["count"]
            return json.loads(
                json.dumps(
                    {
                        "incident": incident,
                        "runs": runs,
                        **rows,
                        "active_demo_read_start_grants": grants,
                        "active_demo_restricted_credential_count": credentials,
                    },
                    default=lambda value: value.isoformat(),
                )
            )
    except AssertionError:
        raise
    except Exception as exc:
        raise AssertionError(f"read-only SQL capture failed ({type(exc).__name__})") from None


def write_artifact(name: str, data: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE / name
    destination.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    destination.chmod(0o600)


async def prepare_async() -> None:
    """Provision governed workflow grants, then create only the synthetic incident."""
    from provision_incident_workflow import build_service, provision

    from sre_agent.persistence.database import Database
    from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

    database = Database(env("DATABASE_URL"))
    try:
        before = capture_sql(missing_ok=True)
        require(not before, "prepare refuses to proceed: incident already exists")
        result = await provision(
            build_service(database, env("AUDIT_HMAC_KEY").encode()),
            f"Bearer {env('ADMIN_HUMAN_API_KEY')}",
        )
        require(
            result.run_read_active and result.run_start_active,
            "governed demo-human run grants did not persist",
        )
        now = datetime.now(UTC)
        state = {
            "workflow_id": "incident-response",
            "workflow_version": "1.0.0",
            "state": "detected",
            "alert": {
                "alert_id": "al-ca1-synthetic",
                "service": "synthetic-service",
                "severity": "sev3",
                "status": "new",
                "observed_at": now.isoformat(),
                "summary": "Synthetic CA1 restart proof.",
                "source": "ca1-http-restart-harness",
            },
            "updated_at": now.isoformat(),
        }
        incident_schema = validate_run_api.load_yaml(
            ROOT / "agent/schemas/incident-state.schema.yaml"
        )
        validate_schema(incident_schema, state, "incident-state")
        async with PostgresIncidentUnitOfWork(database) as work:
            require(
                await work.incidents.get(INCIDENT_ID) is None,
                "prepare refuses to overwrite an existing incident",
            )
            await work.incidents.add(INCIDENT_ID, state, now=now)
        check = capture_sql(require_empty=True)
        require(check, "synthetic incident was not persisted")
        print(f"prepared {INCIDENT_ID}; pre-start runs=0; governed read/start grants active")
    finally:
        await database.dispose()


def before() -> None:
    token = env("DEMO_HUMAN_API_KEY")
    with httpx.Client(timeout=15.0) as client:
        incident = call(client, "GET", "", 200, "incident detail", token=token)
        require(incident.get("runs") == [], "HTTP incident detail is not empty before start")
        pre = capture_sql(require_empty=True)
        require(pre is not None, "synthetic incident must be prepared before start")
        validate("run-start-request", START_BODY)
        created = call(
            client,
            "POST",
            "/runs",
            201,
            "HTTP run start",
            key=IDEMPOTENCY_KEY,
            body=START_BODY,
            token=token,
            schema="run-state",
        )
        run_id = created["run_id"]
        require(created["incident_id"] == INCIDENT_ID, "HTTP response incident identity mismatch")
        state, events = read_run(client, run_id, token, "immediate")
        require(created == state, "created response differs from immediate state read")
    sql = capture_sql(run_id=run_id)
    require(sql is not None, "SQL snapshot is missing")
    require(
        len(sql["events"]) > 0 and len(sql["snapshots"]) > 0,
        "run start did not persist events and snapshots",
    )
    event_seq = max(event["sequence"] for event in sql["events"])
    require(state["cursor"] == f"seq:{event_seq}", "HTTP cursor does not match SQL event sequence")
    require(
        events["events"] and events["events"][-1]["sequence"] == event_seq,
        "HTTP event page does not end at persisted cursor",
    )
    require(
        [(e["event_id"], e["sequence"]) for e in events["events"]]
        == [(e["event_id"], e["sequence"]) for e in sql["events"]],
        "HTTP event identities/order differ from durable SQL events",
    )
    latest = sql["snapshots"][-1]
    require(
        latest["run_id"] == run_id and latest["incident_id"] == INCIDENT_ID,
        "snapshot identity does not correlate to HTTP run",
    )
    require(
        latest["version"] == sql["runs"][0]["version"] and latest["event_sequence"] == event_seq,
        "latest snapshot version/cursor does not correlate to run",
    )
    require(
        latest["run_state"] == sql["runs"][0]["state"],
        "snapshot run state differs from durable run state",
    )
    require(
        state["status"] == sql["runs"][0]["state"]["status"]
        and state["current_state"] == sql["runs"][0]["state"]["current_state"],
        "HTTP state differs from durable SQL run state",
    )
    require(
        len(sql["transition_commits"]) == 1,
        "expected exactly one transition commit for the synthetic run",
    )
    require(
        latest["incident_state"] == sql["incident"]["state"],
        "Snapshot incident state differs from durable incident",
    )
    commit = sql["transition_commits"][0]
    require(
        commit["command_id"] == IDEMPOTENCY_KEY and commit["result"]["run"]["run_id"] == run_id,
        "transition commit does not correlate to the HTTP idempotency key and run",
    )
    baseline = {
        "incident_id": INCIDENT_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "start_body": START_BODY,
        "preflight": {"incident_detail": incident, "sql": pre},
        "run_id": run_id,
        "created": created,
        "state": state,
        "events": events,
        "sql": sql,
    }
    write_artifact("ca1-before.json", baseline)
    print(
        f"before incident={INCIDENT_ID} run={run_id} status=201 "
        f"state={state['current_state']}/{state['status']} version={sql['runs'][0]['version']} "
        f"cursor=seq:{event_seq} events={len(events['events'])} snapshots={len(sql['snapshots'])} "
        f"commits={len(sql['transition_commits'])} preflight_runs={len(pre['runs'])} "
        "evidence=/evidence/ca1-before.json"
    )


def after() -> None:
    try:
        baseline = json.loads((EVIDENCE / "ca1-before.json").read_text())
    except Exception:
        raise AssertionError("before-phase evidence is missing or invalid") from None
    require(baseline.get("incident_id") == INCIDENT_ID, "before evidence incident differs")
    run_id = baseline["run_id"]
    token = env("DEMO_HUMAN_API_KEY")
    restricted = env("RESTRICTED_HARNESS_API_KEY")
    check_evidence: dict[str, Any] = {
        "phase": "post-restart-read",
        "incident_id": INCIDENT_ID,
        "run_id": run_id,
    }
    with httpx.Client(timeout=15.0) as client:
        state, events = read_run(client, run_id, token, "post-restart")
        check_evidence.update({"state": state, "events": events})
        compare("state after restart", baseline["state"], state, check_evidence)
        compare("events after restart", baseline["events"], events, check_evidence)
        sql_restart = capture_sql(run_id=run_id)
        require(sql_restart is not None, "SQL snapshot is missing after restart")
        check_evidence["sql"] = sql_restart
        compare("SQL rows immediately after restart", baseline["sql"], sql_restart, check_evidence)
        check_evidence["restart_reads_identical"] = True
        write_artifact("ca1-after.json", check_evidence)
        replay = call(
            client,
            "POST",
            "/runs",
            200,
            "idempotent replay",
            key=baseline["idempotency_key"],
            body=baseline["start_body"],
            token=token,
            schema="run-state",
        )
        compare("idempotent replay", state, replay, {**check_evidence, "replay": replay})
        resume_body = {**baseline["start_body"], "resume_from_run_id": run_id}
        validate("run-start-request", resume_body)
        resumed = call(
            client,
            "POST",
            "/runs",
            200,
            "resume",
            key=RESUME_KEY,
            body=resume_body,
            token=token,
            schema="run-state",
        )
        compare(
            "resumed run", state, resumed, {**check_evidence, "replay": replay, "resume": resumed}
        )
        for auth, expected, label in ((None, 401, "anonymous"), (restricted, 403, "restricted")):
            for suffix in (f"/runs/{run_id}", f"/runs/{run_id}/events"):
                call(client, "GET", suffix, expected, f"{label} read", token=auth)
    sql = capture_sql(run_id=run_id)
    require(sql is not None, "SQL snapshot is missing after replay/resume")
    compare(
        "SQL rows after replay/resume",
        baseline["sql"],
        sql,
        {**check_evidence, "replay": replay, "resume": resumed, "sql": sql},
    )
    artifact = {
        "incident_id": INCIDENT_ID,
        "run_id": run_id,
        "state": state,
        "events": events,
        "replay": replay,
        "resume": resumed,
        "sql": sql,
        "authorization_statuses": {
            "anonymous_state": 401,
            "anonymous_events": 401,
            "restricted_state": 403,
            "restricted_events": 403,
        },
    }
    write_artifact("ca1-after.json", artifact)
    print(
        f"after incident={INCIDENT_ID} run={run_id} restart_reads=identical "
        f"replay=200 resume=200 sql_runs={len(sql['runs'])} "
        f"auth=401/403 evidence=/evidence/ca1-after.json"
    )


def main() -> int:
    commands = {"before": before, "after": after}
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", *commands}:
        print(
            "usage: python scripts/prove_ca1_http_restart.py {prepare|before|after}",
            file=sys.stderr,
        )
        return 2
    try:
        asyncio.run(prepare_async()) if sys.argv[1] == "prepare" else commands[sys.argv[1]]()
    except Exception as exc:
        # Assertion text is intentionally value-free; never print raw exceptions.
        message = str(exc) if isinstance(exc, AssertionError) else type(exc).__name__
        print(f"CA1 proof failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
