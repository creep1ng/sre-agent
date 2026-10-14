"""Real Docker/HTTP E2E of the canonical CLI against a PREPARED controlled MCP.

Failure modes: cold/repeat setup, data/key loss, occupied port, destination down,
readiness falsely successful, diagnostics leaking secrets, unsafe stop. Does not
provision fixtures or clean volumes. Required private .env follows operator guide.
Run from a Linux Docker-enabled container with host networking and mounted CLI.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from setup_config import load_config  # noqa: E402


def main():
    path = Path(sys.argv[1]).resolve()
    config = load_config(path)
    command = [sys.executable, str(ROOT / "scripts/setup_sre.py"), "--env-file", str(path)]
    env = {**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"}
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(path),
        "-p",
        config["SRE_SETUP_PROJECT"],
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.mcp.yaml"),
        "-f",
        str(Path(config["DEMO_STATE_DIR"]) / "sre-setup" / (config["SRE_SETUP_PROJECT"] + ".json")),
    ]
    base = "http://127.0.0.1:" + config.get("API_PORT", "8000")

    def invoke(expected=0):
        done = subprocess.run(command, capture_output=True, text=True, env=env, timeout=900)
        secrets = [v for k, v in config.items() if v and ("KEY" in k or "PASSWORD" in k)]
        assert not any(value in done.stdout + done.stderr for value in secrets)
        print(done.stdout + done.stderr, end="")
        assert (done.returncode == 0) == (expected == 0), "unexpected setup exit status"

    def snapshot():
        sql = """SELECT json_build_object(
            'principals',(SELECT json_agg(principal_id ORDER BY principal_id) FROM principals),
            'credentials',(SELECT json_agg(row(credential_id,key_hash) ORDER BY credential_id)
                           FROM credentials),
            'grants',(SELECT json_agg(row(grant_id,status) ORDER BY grant_id) FROM grants),
            'incidents',(SELECT json_agg(row(incident_id,state) ORDER BY incident_id)
                         FROM incident.incidents),
            'audit_count',(SELECT count(*) FROM audit_events))"""
        output = subprocess.check_output(
            compose
            + [
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                config["POSTGRES_USER"],
                "-d",
                config["POSTGRES_DB"],
                "-Atc",
                sql,
            ],
            env=env,
            text=True,
        )
        payload = json.loads(output)
        audit = payload.pop("audit_count")
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), audit

    invoke()
    suffix = uuid4().hex[:12]
    alert = "/v1/alerts/al-setup-" + suffix + "/triage/commands"

    def api(method, endpoint, key, body=None, expected=200):
        import urllib.error
        import urllib.request

        headers = {
            "Authorization": "Bearer " + config[key],
            "Content-Type": "application/json",
            "Idempotency-Key": "setup-e2e-" + uuid4().hex,
        }
        data = None if body is None else json.dumps(body).encode()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(base + endpoint, data, headers, method=method), timeout=90
            ) as response:
                status, payload = response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            status, payload = error.code, {}
        print(f"{method} {endpoint} -> HTTP {status}")
        assert status == expected
        return payload

    opened = {"operation": "open_triage", "expected_version": 1}
    api("POST", alert, "RESTRICTED_HARNESS_API_KEY", opened, 403)
    api("POST", alert, "DEMO_HUMAN_API_KEY", opened)
    declared = api(
        "POST",
        alert,
        "DEMO_HUMAN_API_KEY",
        {
            "operation": "triage_declare",
            "expected_version": 1,
            "severity": "sev2",
            "reason": "Controlled setup proof",
            "impact": "Synthetic checkout errors",
            "alert_context": {
                "service": "checkout",
                "summary": "Synthetic alert",
                "observed_at": "2026-10-13T10:00:00-05:00",
                "source": "setup-proof",
                "severity": "sev2",
            },
        },
        201,
    )
    incident = declared["incident_id"]
    started = api(
        "POST",
        f"/v1/incidents/{incident}/runs",
        "DEMO_HUMAN_API_KEY",
        {"workflow_version": "1.0.0", "objective": "investigate"},
        201,
    )
    run = started["run_id"]
    for ending in ("", "/events"):
        endpoint = f"/v1/incidents/{incident}/runs/{run}" + ending
        api("GET", endpoint, "DEMO_HUMAN_API_KEY")
        api("GET", endpoint, "RESTRICTED_HARNESS_API_KEY", expected=403)
    api("GET", "/v1/audit-events?principal_id=demo-human", "ADMIN_HUMAN_API_KEY")
    before, count = snapshot()
    invoke()
    after, new_count = snapshot()
    assert before == after and new_count >= count
    print("REPEAT: stable principals/credential hashes/grants/incidents; audit retained")
    subprocess.check_call(compose + ["stop", "web"], env=env, stdout=subprocess.DEVNULL)
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", int(config.get("WEB_PORT", "8080"))))
        occupied.listen()
        invoke(1)
    invoke()
    # Stop only the caller-owned fixture, never the real demo or another project.
    fixture = config.get("SRE_618_FIXTURE_CONTAINER")
    assert fixture and fixture.startswith("sre-618-fixture-"), "explicit fixture ownership required"
    subprocess.check_call(["docker", "stop", fixture], env=env, stdout=subprocess.DEVNULL)
    try:
        invoke(1)
    finally:
        subprocess.check_call(["docker", "start", fixture], env=env, stdout=subprocess.DEVNULL)
    invoke()
    subprocess.check_call(command + ["--down"], env=env)
    invoke()
    assert snapshot()[0] == before
    print("CONTROLLED INTEGRATION PASS; OTel signals/AWS/paid LLM/human review NOT EXECUTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
