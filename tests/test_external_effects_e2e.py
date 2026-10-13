"""Real HTTP/process/SQL evidence for #567; external gateway is controlled."""

from __future__ import annotations

import dataclasses
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn
from test_incident_investigator_http import (
    AUDIT_KEY,
    DATABASE_URL,
    HARNESS_KEY,
    HUMAN_KEY,
    ROOT,
    SEED_ENV,
    _add_incident,
    _database_rows,
    _free_port,
    _grant_receipt_from_any_run,
    _grant_run_access,
    _receipts,
    _start,
    _stop_app_process,
    migrated_database,  # noqa: F401 -- reuse the existing synthetic DB fixture
)

from sre_agent.application import create_application
from sre_agent.settings import Settings


def run_api(port: int, receiver: str, mode: str) -> None:
    environment = SEED_ENV | {"DATABASE_URL": DATABASE_URL, "AUDIT_HMAC_KEY": AUDIT_KEY}
    if mode != "pre_dispatch":
        environment |= {
            "INVESTIGATOR_GATEWAY_URL": receiver,
            "INVESTIGATOR_GATEWAY_API_KEY": HARNESS_KEY,
            "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
        }
    settings = Settings.from_environment(environment)
    if mode == "timeout":
        assert settings.investigator_gateway is not None
        settings = dataclasses.replace(
            settings,
            investigator_gateway=settings.investigator_gateway.model_copy(
                update={"timeout_seconds": 0.2}
            ),
        )
    uvicorn.run(create_application(settings), host="127.0.0.1", port=port, log_level="critical")


def wait_for(predicate: Any, label: str) -> Any:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {label}")


def spawn(expression: str, *arguments: str) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-c", expression, *arguments],
        cwd=ROOT,
        env=os.environ | {"PYTHONPATH": f"{ROOT / 'src'}:{ROOT / 'tests'}"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process


def ready(url: str, process: subprocess.Popen) -> bool:
    assert process.poll() is None, "owned fixture process exited during startup"
    try:
        return httpx.get(url, timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def start_http(url: str, incident: str, key: str) -> httpx.Response:
    with httpx.Client(base_url=url, timeout=60) as client:
        return _start(client, incident, key)


SCENARIOS = (
    "success",
    "reject",
    "pre_dispatch",
    "5xx",
    "loss",
    "timeout",
    "before_dispatch",
    "before_effect",
    "after_effect",
    "before_commit",
    "concurrent",
)
CRASHES = {"before_dispatch", "before_effect", "after_effect", "before_commit"}


@pytest.mark.parametrize("mode", SCENARIOS)
def test_external_effect_recovery(mode: str) -> None:
    incident, key = f"inc-effects-{mode}", f"effects-{mode}-0001"
    _add_incident(incident)
    _grant_run_access()
    output = Path(os.environ.get("ISSUE567_OUTPUT", "/tmp/issue567-proof"))
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="effects-") as temporary:
        receiver_port, api_port = _free_port(), _free_port()
        receiver_url, api_url = f"http://127.0.0.1:{receiver_port}", f"http://127.0.0.1:{api_port}"
        receiver = spawn(
            "import sys; from effect_receiver import serve; "
            "serve(int(sys.argv[1]), sys.argv[2], sys.argv[3])",
            str(receiver_port),
            temporary,
            mode,
        )
        applications: list[subprocess.Popen] = []
        blocker = None
        observations_at_boundary = None
        concurrent_codes: list[int] = []
        persistence_wait_observed = False
        try:
            wait_for(lambda: ready(f"{receiver_url}/observations", receiver), "receiver ready")
            application = spawn(
                "import sys; from test_external_effects_e2e import run_api; "
                "run_api(int(sys.argv[1]), sys.argv[2], sys.argv[3])",
                str(api_port),
                receiver_url,
                mode,
            )
            applications.append(application)
            wait_for(lambda: ready(f"{api_url}/health/ready", application), "application ready")
            with httpx.Client(base_url=receiver_url, timeout=5) as witness:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    initial = executor.submit(start_http, api_url, incident, key)
                    if mode in CRASHES | {"concurrent"}:
                        wait_for(lambda: witness.get("/checkpoint").json()["held"], "held boundary")
                        observations_at_boundary = witness.get("/observations").json()
                        identity, events = _grant_receipt_from_any_run(incident)
                        run_id = identity["run_id"]
                        assert [r["status"] for r in _receipts(events)] == ["pending"]
                        if mode == "concurrent":
                            retries = [
                                executor.submit(start_http, api_url, incident, key)
                                for _ in range(4)
                            ]
                            concurrent_codes = [r.result(timeout=15).status_code for r in retries]
                            assert concurrent_codes == [200] * 4
                            _, events = _grant_receipt_from_any_run(incident)
                            assert [r["status"] for r in _receipts(events)] == ["pending"]
                            assert witness.get("/observations").json() == observations_at_boundary
                            witness.post("/release").raise_for_status()
                        if mode == "before_commit":
                            blocker = psycopg.connect(DATABASE_URL)
                            blocker.execute("LOCK TABLE incident.run_events IN SHARE MODE")
                            witness.post("/release").raise_for_status()

                            def insertion_waiting() -> bool:
                                with psycopg.connect(DATABASE_URL) as connection:
                                    return connection.execute(
                                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                        "WHERE datname=current_database() "
                                        "AND wait_event_type='Lock' "
                                        "AND query LIKE '%%INSERT INTO incident.run_events%%')"
                                    ).fetchone()[0]

                            wait_for(insertion_waiting, "real outcome INSERT blocked before commit")
                            persistence_wait_observed = True
                        if mode in CRASHES:
                            application.kill()
                            assert application.wait(timeout=10) == -signal.SIGKILL
                            with pytest.raises(httpx.HTTPError):
                                initial.result(timeout=10)
                            if blocker is not None:
                                blocker.rollback()
                                blocker.close()
                                blocker = None
                            _, events = _grant_receipt_from_any_run(incident)
                            assert [r["status"] for r in _receipts(events)] == ["pending"]
                            assert not any(
                                event.get("outcome", {}).get("action") for event in events
                            )
                            initial_code = None
                        else:
                            response = initial.result(timeout=20)
                            initial_code, run_id = response.status_code, response.json()["run_id"]
                    else:
                        response = initial.result(timeout=20)
                        initial_code, run_id = response.status_code, response.json()["run_id"]
                        assert initial_code == 201
                if mode == "timeout":
                    observations_at_boundary = witness.get("/observations").json()
                    assert observations_at_boundary["counter"] == 0
                    wait_for(
                        lambda: witness.get("/observations").json()["counter"] == 1,
                        "late effect after timeout",
                    )
                state_before = _receipts(_database_rows(incident, run_id)[1])
                _stop_app_process(application)
                restarted_port = _free_port()
                application = spawn(
                    "import sys; from test_external_effects_e2e import run_api; "
                    "run_api(int(sys.argv[1]), sys.argv[2], sys.argv[3])",
                    str(restarted_port),
                    receiver_url,
                    mode,
                )
                applications.append(application)
                restarted_url = f"http://127.0.0.1:{restarted_port}"
                wait_for(lambda: ready(f"{restarted_url}/health/ready", application), "restart")
                before_reads = witness.get("/observations").json()
                with httpx.Client(base_url=restarted_url, timeout=15) as client:
                    headers = {"Authorization": f"Bearer {HUMAN_KEY}"}
                    read = client.get(f"/v1/incidents/{incident}/runs/{run_id}", headers=headers)
                    resume = client.post(
                        f"/v1/incidents/{incident}/runs",
                        headers=headers | {"Idempotency-Key": f"resume-{key}"},
                        json={
                            "workflow_version": "1.0.0",
                            "objective": "investigate",
                            "resume_from_run_id": run_id,
                        },
                    )
                    assert read.status_code == resume.status_code == 200
                    assert read.json() == resume.json()
                    assert _receipts(_database_rows(incident, run_id)[1]) == state_before
                    assert witness.get("/observations").json() == before_reads
                    replay = _start(client, incident, key)
                    assert replay.status_code == 200 and replay.json()["run_id"] == run_id
                    terminal = _receipts(_database_rows(incident, run_id)[1])
                    expected = (
                        "success"
                        if mode in {"success", "concurrent"}
                        else "confirmed_failure"
                        if mode in {"reject", "pre_dispatch"}
                        else "unknown"
                    )
                    assert [r["status"] for r in terminal] == ["pending", expected]
                    assert witness.get("/observations").json() == before_reads
                    if mode in CRASHES:
                        assert terminal[-1]["reason_code"] == "producer_interrupted"
                        witness.post("/release").raise_for_status()
                        if mode == "before_effect":
                            wait_for(
                                lambda: witness.get("/observations").json()["counter"] == 1,
                                "late effect after restart and ambiguous replay",
                            )
                    final_external = witness.get("/observations").json()
                    again = _start(client, incident, key)
                    assert again.status_code == 200 and again.json()["run_id"] == run_id
                    assert _receipts(_database_rows(incident, run_id)[1]) == terminal
                    assert witness.get("/observations").json() == final_external
                count = 0 if mode in {"pre_dispatch", "before_dispatch"} else 1
                effect = 0 if mode in {"reject", "pre_dispatch", "before_dispatch"} else 1
                assert len(final_external["operations"]) == count
                assert final_external["counter"] == effect
                for operation in final_external["operations"]:
                    assert operation["run_id"] == terminal[-1]["dispatch_id"] == run_id
                    assert operation["incident_id"] == incident
                    assert operation["task_id"].startswith("task_")
                    if mode in {"success", "reject", "5xx", "concurrent"}:
                        assert operation["request_id"] in terminal[-1]["request_ids"]
                if mode == "reject":
                    assert final_external["operations"][0]["status"] == "rejected"
                    assert terminal[-1]["reason_code"] == "governed_call_denied"
                if mode == "pre_dispatch":
                    assert final_external["discovery_calls"] == 0
                    assert terminal[-1]["reason_code"] == "harness_not_configured"
                with psycopg.connect(DATABASE_URL) as connection:
                    postgres_version = connection.execute("SHOW server_version").fetchone()[0]
                report = {
                    "scenario": mode,
                    "evidence_kind": "controlled integration",
                    "tested_sha": os.environ.get("ISSUE567_TESTED_SHA", "unrecorded"),
                    "base_sha": os.environ.get("ISSUE567_BASE_SHA", "unrecorded"),
                    "environment": {
                        "python": sys.version.split()[0],
                        "postgres": postgres_version,
                        "fastapi": version("fastapi"),
                        "httpx": version("httpx"),
                        "sqlalchemy": version("sqlalchemy"),
                        "psycopg": version("psycopg"),
                    },
                    "expected_outcome": expected,
                    "observed_outcome": terminal[-1]["status"],
                    "initial_http": initial_code,
                    "read_http": read.status_code,
                    "resume_http": resume.status_code,
                    "replay_http": replay.status_code,
                    "read_state": read.json(),
                    "receipts_before_replay": state_before,
                    "terminal_receipts": terminal,
                    "receiver_at_boundary": observations_at_boundary,
                    "receiver_final": final_external,
                    "concurrent_http": concurrent_codes,
                    "outcome_insert_wait_observed": persistence_wait_observed,
                    "receiver_pid": receiver.pid,
                    "runtime_pids": [p.pid for p in applications],
                    "first_runtime_exit": applications[0].returncode,
                    "database_query": "SELECT payload FROM incident.run_events "
                    "WHERE run_id = %s ORDER BY sequence",
                }
                (output / f"{mode}.json").write_text(json.dumps(report, indent=2) + "\n")
                print(
                    f"E567 {mode}: {expected}; receiver operations={count} counter={effect}; "
                    "read/resume/replay did not redispatch"
                )
        finally:
            if blocker is not None:
                blocker.rollback()
                blocker.close()
            for process in applications:
                _stop_app_process(process)
            _stop_app_process(receiver)
            ledger = Path(temporary) / "receiver.sqlite"
            if ledger.exists():
                import shutil

                shutil.copyfile(ledger, output / f"{mode}-receiver.sqlite")
