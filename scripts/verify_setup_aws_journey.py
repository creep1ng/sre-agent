"""Real AWS/SRE journey. API credentials only; MCP token is never read by this runner.

Requires explicitly authorized producer fail/reset and its expected-account guard.
Checks nonempty traffic, changed/recovered metrics/logs, workflow/denial/audit,
and repeat convergence. No paid inference, resource cleanup or raw log output.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from setup_config import ROOT, load_config


def main():
    path = Path(sys.argv[1]).resolve()
    config = load_config(path)  # AWS path checks token metadata, not its contents.
    assert config["SRE_OTEL_MODE"] == "aws" and config.get("SRE_ENABLE_PAID_LLM", "0") == "0"
    assert os.environ.get("OTEL_DEMO_EXPECTED_ACCOUNT_ID"), "explicit owner guard required"
    base = "http://127.0.0.1:" + config["API_PORT"]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    sensitive = [v for k, v in config.items() if v and ("KEY" in k or "PASSWORD" in k)]

    def api(method, endpoint, key, body=None, expected=200):
        headers = {
            "Authorization": "Bearer " + config[key],
            "Content-Type": "application/json",
            "Idempotency-Key": "aws-journey-" + uuid4().hex,
        }
        request = urllib.request.Request(
            base + endpoint,
            None if body is None else json.dumps(body).encode(),
            headers,
            method=method,
        )
        try:
            with opener.open(request, timeout=90) as response:
                status, payload = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, payload = error.code, {}
            error.close()
        assert status == expected, "governed API returned unexpected status"
        print(method, endpoint.split("?")[0], "HTTP" + str(status), flush=True)
        return payload

    def setup():
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/setup_sre.py"), "--env-file", str(path)],
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert not any(value in result.stdout + result.stderr for value in sensitive), (
            "secret output"
        )
        print(result.stdout + result.stderr, end="", flush=True)
        assert result.returncode == 0, "canonical setup failed"

    def owner(action):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/otel_ec2.py"), action],
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, "owned flag operation failed; inspect owner status"
        print("owner " + action + " completed; no token or command payload printed", flush=True)

    def metric(expr):
        payload = api(
            "POST",
            "/v1/mcp/tools/query_prometheus",
            "INCIDENT_HARNESS_API_KEY",
            {
                "datasource_uid": "webstore-metrics",
                "expr": expr,
                "query_type": "instant",
                "end_time": "now",
            },
        )
        rows = payload["result"]
        assert len(rows) == 1, "real aggregate metric missing"
        return float(rows[0]["value"][1])

    def logs(query):
        return api(
            "POST",
            "/v1/mcp/tools/query_elasticsearch",
            "INCIDENT_HARNESS_API_KEY",
            {
                "datasource_uid": "webstore-logs",
                "index": "otel-logs-*",
                "query": query,
                "start_time": "now-2m",
                "end_time": "now",
                "limit": 100,
            },
        )["documents"]

    def signals(label):
        calls = metric(
            'sum(increase(traces_span_metrics_calls_total{service_name="checkout"}[2m]))'
        )
        errors = metric(
            'sum(increase(traces_span_metrics_calls_total{service_name="checkout",'
            'status_code="STATUS_CODE_ERROR"}[2m])) or vector(0)'
        )
        checkout = logs("resource.service.name:checkout")
        proxy = logs('resource.service.name:"frontend-proxy" AND body:*checkout*')
        bodies = [str(row.get("_source", row).get("body", "")) for row in checkout]
        completed = sum("order placed" in body for body in bodies)
        statuses = [
            match.group(1)
            for row in proxy
            if (
                match := re.search(
                    r'"POST [^"]*checkout[^"]*" (\d{3}) ',
                    str(row.get("_source", row).get("body", "")),
                )
            )
        ]
        print(
            f"{label}: calls={calls:.1f}, errors={errors:.1f}, completed_orders={completed}, "
            f"proxy200={statuses.count('200')}, proxy500={statuses.count('500')}",
            flush=True,
        )
        assert calls > 0 and checkout and statuses, "no real checkout traffic/signal window"
        return errors, completed, statuses

    def snapshot():
        sql = """SELECT json_build_object(
          'principals',(SELECT json_agg(principal_id ORDER BY principal_id) FROM principals),
          'credentials',(SELECT md5(string_agg(row(credential_id,key_hash)::text,','
                           ORDER BY credential_id)) FROM credentials),
          'grants',(SELECT json_agg(row(grant_id,status) ORDER BY grant_id) FROM grants),
          'incidents',(SELECT json_agg(row(incident_id,state) ORDER BY incident_id)
                         FROM incident.incidents),
          'audit_count',(SELECT count(*) FROM audit_events))"""
        value = subprocess.check_output(
            [
                "docker",
                "exec",
                config["SRE_SETUP_PROJECT"] + "-db-1",
                "psql",
                "-U",
                config["POSTGRES_USER"],
                "-d",
                config["POSTGRES_DB"],
                "-Atc",
                sql,
            ],
            text=True,
        )
        data = json.loads(value)
        count = data.pop("audit_count")
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).digest(), count

    setup()
    errors, completed, statuses = signals("baseline")
    assert errors == 0 and completed > 0 and "200" in statuses, "baseline not healthy"
    try:
        owner("fail")
        print("waiting150s: isolate declared failure's two-minute signal window", flush=True)
        time.sleep(150)
        errors, _, statuses = signals("failure")
        assert errors > 0 and "500" in statuses, "declared failure not observed through API"
        alert = "/v1/alerts/al-aws-setup-" + uuid4().hex[:12] + "/triage/commands"
        opened = {"operation": "open_triage", "expected_version": 1}
        api("POST", alert, "RESTRICTED_HARNESS_API_KEY", opened, 403)
        api("POST", alert, "DEMO_HUMAN_API_KEY", opened)
        incident = api(
            "POST",
            alert,
            "DEMO_HUMAN_API_KEY",
            {
                "operation": "triage_declare",
                "expected_version": 1,
                "severity": "sev2",
                "reason": "Reviewer observed declared checkout failure",
                "impact": "Demo checkout errors",
                "alert_context": {
                    "service": "checkout",
                    "summary": "Declared flag failure observed",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "source": "aws-setup-proof",
                    "severity": "sev2",
                },
            },
            201,
        )["incident_id"]
        run = api(
            "POST",
            f"/v1/incidents/{incident}/runs",
            "DEMO_HUMAN_API_KEY",
            {"workflow_version": "1.0.0", "objective": "investigate"},
            201,
        )["run_id"]
        for ending in ("", "/events"):
            endpoint = f"/v1/incidents/{incident}/runs/{run}" + ending
            api("GET", endpoint, "DEMO_HUMAN_API_KEY")
            api("GET", endpoint, "RESTRICTED_HARNESS_API_KEY", expected=403)
        api("GET", "/v1/audit-events?principal_id=demo-human", "ADMIN_HUMAN_API_KEY")
        before, count = snapshot()
        setup()
        after, new_count = snapshot()
        assert before == after and new_count >= count, (
            "repeat changed identities/keys/grants/incidents or lost audit"
        )
        print("REPEAT: domain state/credential digest unchanged; audit retained", flush=True)
    finally:
        owner("reset")
    print("waiting150s: isolate recovery's two-minute signal window", flush=True)
    time.sleep(150)
    errors, completed, statuses = signals("recovery")
    assert errors == 0 and completed > 0 and "200" in statuses, "signal recovery not observed"
    print("REAL AWS JOURNEY PASS; paid inference, independent human/main acceptance NOT verified")


if __name__ == "__main__":
    main()
