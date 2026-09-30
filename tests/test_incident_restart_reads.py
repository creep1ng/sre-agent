"""Issue #189 A4 (CA3): restart the packaged HTTP service, reread, compare.

Real uvicorn subprocess serving sre_agent.main:app (the exact packaged
entrypoint), real TCP HTTP, real PostgreSQL. Kill the server, start it
again on the SAME database without re-registering or re-granting anything,
then prove detail/timeline/snapshot are identical and auth still holds.
"""

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
    RUN_ID,
    prepare_authorized_database,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
PATHS = (
    f"/v1/incidents/{INCIDENT_ID}",
    f"/v1/incidents/{INCIDENT_ID}/timeline",
    f"/v1/incidents/{INCIDENT_ID}/snapshot",
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
