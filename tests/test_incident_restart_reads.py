"""Issue #189 A4 (CA3): restart the packaged HTTP service, reread, compare.

Real uvicorn subprocess serving sre_agent.main:app (the exact packaged
entrypoint), real TCP HTTP, real PostgreSQL. Kill the server, start it
again on the SAME database without re-registering or re-granting anything,
then prove detail/timeline/snapshot are identical and auth still holds.
Issue #330 adds the run state and run events: the run is re-read through the
runs contract after the restart, with the cursor still at its last event.
"""

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
from test_incident_authorized_reads import (
    BEARERS,
    INCIDENT_ID,
    NOW,
    RUN_ID,
    _base_state,
    prepare_authorized_database,
)

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
START_INCIDENT_ID = "inc-a4-process-start"
PATHS = (
    f"/v1/incidents/{INCIDENT_ID}",
    f"/v1/incidents/{INCIDENT_ID}/timeline",
    f"/v1/incidents/{INCIDENT_ID}/snapshot",
    # Issue #330: the run state and run events of the runs contract.
    f"/v1/incidents/{INCIDENT_ID}/runs/{RUN_ID}",
    f"/v1/incidents/{INCIDENT_ID}/runs/{RUN_ID}/events",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["DATABASE_URL"] = DATABASE_URL
    env["PYTHONPATH"] = str(REPOSITORY_ROOT / "src")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "sre_agent.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPOSITORY_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("packaged server exited during startup")
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health/live", timeout=2)
            if response.status_code == 200:
                return process
        except httpx.ConnectError:
            time.sleep(0.5)
    process.kill()
    raise RuntimeError("packaged server did not become ready")


def _stop_server(process: subprocess.Popen) -> None:
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


def _reads(port: int, headers: dict[str, str]) -> dict[str, dict]:
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
        return {path: client.get(path, headers=headers).json() for path in PATHS}


def _grant_count() -> int:
    with psycopg.connect(DATABASE_URL) as connection:
        return int(connection.execute("SELECT count(*) FROM grants").fetchone()[0])


def _seed_start_incident() -> None:
    database = Database(DATABASE_URL)

    async def _seed() -> None:
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(START_INCIDENT_ID, _base_state(), now=NOW)

    try:
        asyncio.run(_seed())
    finally:
        asyncio.run(database.dispose())


def test_packaged_restart_preserves_reads_and_authorization() -> None:
    prepare_authorized_database()
    headers = {"Authorization": BEARERS["demo"]}
    grants_before = _grant_count()
    port = _free_port()
    server = _start_server(port)
    try:
        before = _reads(port, headers)
    finally:
        _stop_server(server)
    assert server.returncode is not None
    assert before[PATHS[0]]["runs"][0]["run_id"] == RUN_ID
    assert before[PATHS[3]]["run_id"] == RUN_ID
    assert before[PATHS[3]]["cursor"] == before[PATHS[4]]["next_cursor"]
    server = _start_server(port)
    try:
        after = _reads(port, headers)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            anonymous = client.get(PATHS[0])
            forbidden = client.get(PATHS[0], headers={"Authorization": BEARERS["bystander"]})
    finally:
        _stop_server(server)
    assert after == before
    assert after[PATHS[2]]["snapshot_id"] == before[PATHS[2]]["snapshot_id"]
    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert _grant_count() == grants_before


def test_http_started_run_survives_process_restart_read_and_resume() -> None:
    prepare_authorized_database()
    _seed_start_incident()
    headers = {"Authorization": BEARERS["demo"]}
    base_url = "http://127.0.0.1"
    port = _free_port()
    runs_path = f"/v1/incidents/{START_INCIDENT_ID}/runs"
    body = {"workflow_version": "1.0.0", "objective": "triage"}

    first_server = _start_server(port)
    first_pid = first_server.pid
    try:
        with httpx.Client(base_url=f"{base_url}:{port}", timeout=10) as client:
            started = client.post(
                runs_path,
                json=body,
                headers=headers | {"Idempotency-Key": "restart-http-start-0001"},
            )
    finally:
        _stop_server(first_server)

    assert started.status_code == 201, started.text
    started_state = started.json()
    run_id = started_state["run_id"]
    assert (started_state["incident_id"], started_state["current_state"]) == (
        START_INCIDENT_ID,
        "triage",
    )
    assert started_state["cursor"] == "seq:0"
    assert first_server.returncode is not None

    second_server = _start_server(port)
    try:
        with httpx.Client(base_url=f"{base_url}:{port}", timeout=10) as client:
            state_response = client.get(f"{runs_path}/{run_id}", headers=headers)
            events_response = client.get(f"{runs_path}/{run_id}/events", headers=headers)
            resumed = client.post(
                runs_path,
                json=body | {"resume_from_run_id": run_id},
                headers=headers | {"Idempotency-Key": "restart-http-resume-0001"},
            )
            events_after_resume = client.get(f"{runs_path}/{run_id}/events", headers=headers)
    finally:
        _stop_server(second_server)

    assert second_server.pid != first_pid
    assert second_server.returncode is not None
    assert state_response.status_code == 200, state_response.text
    assert events_response.status_code == 200, events_response.text
    assert resumed.status_code == 200, resumed.text
    assert events_after_resume.status_code == 200, events_after_resume.text
    state = state_response.json()
    events = events_response.json()
    assert state == started_state
    assert resumed.json() == state
    assert events_after_resume.json() == events
    assert (state["incident_id"], state["run_id"], state["current_state"], state["cursor"]) == (
        START_INCIDENT_ID,
        run_id,
        "triage",
        "seq:0",
    )
    assert [event["sequence"] for event in events["events"]] == [0]
    assert (events["has_more"], events["next_cursor"]) == (False, state["cursor"])
    with psycopg.connect(DATABASE_URL) as connection:
        persisted = connection.execute(
            "SELECT count(*), min(sequence), max(sequence) FROM incident.run_events "
            "WHERE incident_id=%s AND run_id=%s",
            (START_INCIDENT_ID, run_id),
        ).fetchone()
    assert persisted == (1, 0, 0)

    print(
        "HTTP_START status=201 "
        f"incident_id={START_INCIDENT_ID} run_id={run_id} "
        f"state={started_state['current_state']} cursor={started_state['cursor']}"
    )
    print(
        f"PROCESS_RESTART old_pid={first_pid} old_exit={first_server.returncode} "
        f"new_pid={second_server.pid} new_exit={second_server.returncode}"
    )
    print(
        f"HTTP_RESTART_READ status={state_response.status_code} "
        f"event_count={len(events['events'])} persisted_event_count={persisted[0]} "
        f"state={state['current_state']} cursor={state['cursor']}"
    )
    print(
        f"HTTP_RESUME status={resumed.status_code} incident_id={state['incident_id']} "
        f"run_id={state['run_id']} state={state['current_state']} "
        f"cursor={state['cursor']} persisted_event_count={persisted[0]}"
    )
