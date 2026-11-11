"""Owned AWS Demo operations. Installed by the producer, never by SRE setup."""

import argparse
import base64
import collections
import hmac
import http.server
import json
import os
import secrets
import shutil
import stat
import subprocess
import threading
from pathlib import Path

ROOT = Path("/opt/otel-demo")
STATE = Path("/var/lib/otel-demo-sre")
TOKEN = STATE / "grafana-mcp.env"
FLAGS = STATE / "flagd" / "demo.flagd.json"
OVERLAY = STATE / "compose.json"
# Grafana alert intake (#765): the contact point's secret, Midnight's rules, and the outbox
# that holds Grafana's deliveries until connect-mcp drains them over SSM to the local API.
INTAKE = STATE / "alert-intake.env"
RULES = STATE / "alerting"
OUTBOX = 17801
# The deploy-executor's flag.set (#724): a loopback listener connect-mcp forwards over SSM, with
# its own token, that writes only the manifest's fault flags and only back to their baseline.
FLAG_TOKEN = STATE / "flag-write.env"
FLAG_PORT = 17802
FLAG_WRITE = threading.Lock()
# Upstream flushes span metrics once a minute and tells Grafana so (timeInterval 60s), so the
# Demo Dashboard's $__rate_interval spans 4 min and shows a recovery minutes after the alert
# resolves. Every 5 s, on both sides, shows a fault or a recovery within seconds, so a visitor
# walks the whole loop in about a minute (2026-11-10 expo).
COLLECTOR_EXTRAS = STATE / "otelcol-config-extras.yml"
DATASOURCES = STATE / "datasources"
METRICS_INTERVAL = "5s"


def compose(*args):
    command = ["docker", "compose", "-p", "otel-demo", "--project-directory", str(ROOT)]
    for path in (ROOT / ".env", ROOT / "demo.env", STATE / "demo.env"):
        command += ["--env-file", str(path)]
    for path in (ROOT / "compose.yaml", ROOT / "compose.observability.yaml", OVERLAY):
        command += ["-f", str(path)]
    done = subprocess.run(command + list(args), capture_output=True, timeout=180, check=False)
    if done.returncode:
        raise RuntimeError("owned Demo " + args[0] + " failed; inspect scoped service state")


def settings():
    return json.loads((STATE / "settings.json").read_text())


def variants(failure=False, flag=None):
    config = settings()
    data = json.loads(FLAGS.read_text())
    if failure:
        name = flag or config["failure_flag"]
        updates = {name: config["fault_flags"][name]}
    else:
        baseline = dict(config["baseline"])
        fallback = baseline.pop("all_other_flags")
        updates = {
            name: baseline.get(name, fallback)
            for name, flag in data["flags"].items()
            if baseline.get(name, fallback) in flag["variants"]
        }
    for name, variant in updates.items():
        if variant not in data["flags"][name]["variants"]:
            raise RuntimeError("declared flag/variant unavailable; preserve Demo state")
        data["flags"][name]["defaultVariant"] = variant
    replace_flags(data)


def replace_flags(data):
    """Atomically replace the flag file. flagd (v0.16.0) polls it and reloads within ~1 s, and
    sends `configuration_change` to its streams. A restart would break every client's stream,
    and payment's broken stream fired its own alert (#724)."""
    temporary = FLAGS.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(FLAGS)


def private_secret(path, name):
    if not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(name + "=" + secrets.token_hex(24) + "\n")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RuntimeError("remote token must be a private regular file")


def metrics_interval():
    """Write the collector's extra layer and a copy of upstream's datasources with the faster
    interval. Both are read inside containers by non-root users, hence 0644."""
    COLLECTOR_EXTRAS.write_text(
        f"connectors:\n  span_metrics:\n    metrics_flush_interval: {METRICS_INTERVAL}\n"
    )
    COLLECTOR_EXTRAS.chmod(0o644)
    shutil.rmtree(DATASOURCES, ignore_errors=True)
    shutil.copytree(ROOT / "src" / "grafana" / "provisioning" / "datasources", DATASOURCES)
    source = DATASOURCES / "default.yaml"
    text = source.read_text()
    if text.count('timeInterval: "60s"') != 1:
        raise RuntimeError("upstream Prometheus datasource changed; review its timeInterval")
    source.write_text(text.replace('timeInterval: "60s"', f'timeInterval: "{METRICS_INTERVAL}"'))
    DATASOURCES.chmod(0o755)
    for path in DATASOURCES.iterdir():
        path.chmod(0o644)


def prepare():
    STATE.mkdir(mode=0o700, exist_ok=True)
    if STATE.is_symlink() or STATE.stat().st_mode & 0o077:
        raise RuntimeError("owned remote state directory must be private")
    private_secret(TOKEN, "MCP_GRAFANA_SERVER_TOKEN")
    private_secret(INTAKE, "ALERT_INTAKE_GRAFANA_SECRET")
    private_secret(FLAG_TOKEN, "DEPLOY_EXECUTOR_FLAGS_TOKEN")
    if not FLAGS.exists():
        shutil.copytree(ROOT / "src" / "flagd", FLAGS.parent)
        variants()
    metrics_interval()
    layer = {
        "services": {
            "flagd": {"volumes": [str(FLAGS.parent) + ":/etc/flagd"]},
            "checkout": {"environment": {"FLAGD_CACHE": "disabled"}},
            "otel-collector": {
                "volumes": [f"{COLLECTOR_EXTRAS}:/etc/otelcol-config-extras.yml:ro"]
            },
            # Provisioning outside upstream's bind mount, so nothing is created in its checkout.
            "grafana": {
                # Upstream caps Grafana at 175M; loading the Demo Dashboard peaks near 275M, the
                # kernel kills it, and the proxy answers 503 while alert rules restart their wait.
                "deploy": {"resources": {"limits": {"memory": "1G"}}},
                "environment": {
                    "GF_PATHS_PROVISIONING": "/etc/midnight-provisioning",
                    "ALERT_INTAKE_URL": f"http://host.docker.internal:{OUTBOX}"
                    "/v1/alert-intake/grafana",
                },
                "env_file": [str(INTAKE)],
                "extra_hosts": ["host.docker.internal:host-gateway"],
                "volumes": [
                    f"{ROOT}/src/grafana/provisioning/dashboards:"
                    "/etc/midnight-provisioning/dashboards:ro",
                    f"{DATASOURCES}:/etc/midnight-provisioning/datasources:ro",
                    f"{RULES}:/etc/midnight-provisioning/alerting:ro",
                ],
            },
            "grafana-mcp": {
                "image": settings()["mcp_image"],
                "container_name": "grafana-mcp",
                "command": [
                    "--transport=streamable-http",
                    "--address=0.0.0.0:8000",
                    "--allowed-hosts=grafana-mcp:8000,127.0.0.1:18092,localhost:18092",
                    "--disable-write",
                    "--enabled-tools=prometheus,elasticsearch,datasource",
                ],
                "environment": {
                    "GRAFANA_URL": "http://grafana:3000/grafana",
                    "GRAFANA_ORG_ID": "1",
                },
                "env_file": [str(TOKEN)],
                "ports": ["127.0.0.1:17800:8000"],
                "networks": ["default", "mcp-boundary"],
                "restart": "unless-stopped",
            },
        },
        "networks": {"mcp-boundary": {"name": "otel-demo-sre-mcp", "internal": True}},
    }
    serialized = json.dumps(layer, sort_keys=True)
    if OVERLAY.exists() and OVERLAY.read_text() != serialized:
        raise RuntimeError("owned overlay conflict; review before changing existing state")
    OVERLAY.write_text(serialized)
    OVERLAY.chmod(0o600)
    for unit, action in (
        ("otel-demo-alert-outbox", "serve-outbox"),
        ("otel-demo-flag-write", "serve-flags"),
    ):
        if subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode:
            subprocess.run(
                ["systemd-run", "--unit=" + unit, "--property=Restart=on-failure"]
                + ["python3", str(Path(__file__).resolve()), action],
                capture_output=True,
                timeout=30,
                check=True,
            )
    compose("pull", "--policy", "missing", "grafana-mcp")
    compose(
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "--wait",
        "flagd",
        "checkout",
        "grafana-mcp",
        "load-generator",
        "otel-collector",
        "grafana",
    )
    print("owned AWS MCP prepared; token retained, upstream source untouched")


class TokenTransfer(http.server.BaseHTTPRequestHandler):
    """Only the authorized SSM port-forwarding channel can reach this loopback listener."""

    def log_message(self, *_args):
        pass

    def do_GET(self):
        files = {"/token": TOKEN, "/intake": INTAKE, "/flags": FLAG_TOKEN}
        if self.path not in files:
            self.send_error(404)
            return
        body = files[self.path].read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


DELIVERIES = collections.deque(maxlen=200)


class OutboxReceive(http.server.BaseHTTPRequestHandler):
    """Grafana's contact point, on the Docker bridge gateway; the delivery is kept opaque."""

    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if self.path != "/v1/alert-intake/grafana" or not 0 < length <= 512 * 1024:
            self.send_error(404 if self.path != "/v1/alert-intake/grafana" else 413)
            return
        body = self.rfile.read(length)
        authorization = self.headers.get("Authorization", "")
        DELIVERIES.append({"authorization": authorization, "body": base64.b64encode(body).decode()})
        self.send_response(202)
        self.end_headers()


class OutboxDrain(http.server.BaseHTTPRequestHandler):
    """Loopback only: connect-mcp takes one delivery at a time over SSM port forwarding."""

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/next":
            self.send_error(404)
            return
        try:
            body = json.dumps(DELIVERIES.popleft()).encode()
        except IndexError:
            self.send_response(204)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def writable_flags():
    """Fault flag -> the only variant it may be written to: its baseline."""
    config = settings()
    baseline = dict(config["baseline"])
    fallback = baseline.pop("all_other_flags")
    return {name: baseline.get(name, fallback) for name in config["fault_flags"]}


class FlagWrite(http.server.BaseHTTPRequestHandler):
    """GET /flags reads the fault flags; PUT /flags/<name> {"variant"} turns one back off."""

    def log_message(self, *_args):
        pass

    def answer(self, status, body=None):
        data = json.dumps(body or {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        expected = "Bearer " + FLAG_TOKEN.read_text().strip().partition("=")[2]
        return hmac.compare_digest(self.headers.get("Authorization", ""), expected)

    def do_GET(self):
        if self.path != "/flags":
            return self.answer(404)
        if not self.authorized():
            return self.answer(401)
        data = json.loads(FLAGS.read_text())["flags"]
        flags = {name: data[name]["defaultVariant"] for name in writable_flags() if name in data}
        return self.answer(200, {"flags": flags})

    def do_PUT(self):
        name = self.path.removeprefix("/flags/")
        if not self.path.startswith("/flags/"):
            return self.answer(404)
        if not self.authorized():
            return self.answer(401)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            variant = json.loads(self.rfile.read(min(length, 1024)))["variant"]
        except (ValueError, KeyError, TypeError):
            return self.answer(422)
        if writable_flags().get(name) != variant:
            return self.answer(403)  # not a fault flag, or not back to its baseline
        with FLAG_WRITE:
            data = json.loads(FLAGS.read_text())
            if variant not in data["flags"].get(name, {}).get("variants", {}):
                return self.answer(409)  # the demo's flag file does not offer it
            before = data["flags"][name]["defaultVariant"]
            if before != variant:
                data["flags"][name]["defaultVariant"] = variant
                replace_flags(data)
        return self.answer(200, {"flag": name, "before": before, "variant": variant})


def serve_outbox():
    gateway = subprocess.run(
        ["docker", "network", "inspect", "bridge"]
        + ["--format", "{{(index .IPAM.Config 0).Gateway}}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    receive = http.server.ThreadingHTTPServer((gateway, OUTBOX), OutboxReceive)
    threading.Thread(target=receive.serve_forever, daemon=True).start()
    http.server.ThreadingHTTPServer(("127.0.0.1", OUTBOX), OutboxDrain).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = ("prepare", "fail", "reset", "serve-token", "serve-outbox", "serve-flags")
    parser.add_argument("action", choices=actions)
    parser.add_argument("--flag", help="fail: one of the manifest's fault_flags")
    arguments = parser.parse_args()
    action = arguments.action
    if action == "prepare":
        prepare()
    elif action == "serve-outbox":
        serve_outbox()
    elif action == "serve-flags":
        # Loopback on the instance; the local stand-in of the E2E listens on its own network.
        listen = os.environ.get("OTEL_FLAGS_LISTEN", "127.0.0.1")
        http.server.ThreadingHTTPServer((listen, FLAG_PORT), FlagWrite).serve_forever()
    elif action == "serve-token":
        http.server.HTTPServer(("127.0.0.1", 17900), TokenTransfer).serve_forever()
    else:
        variants(failure=action == "fail", flag=arguments.flag)
        print("owned AWS flag " + action + " applied; flagd reloads it; synthetic traffic retained")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit(
            "owned AWS operation failed; preserve resources and inspect scoped status"
        ) from None
