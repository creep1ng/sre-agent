"""Owned AWS Demo operations. Installed by the producer, never by SRE setup."""

import argparse
import http.server
import json
import os
import secrets
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path("/opt/otel-demo")
STATE = Path("/var/lib/otel-demo-sre")
TOKEN = STATE / "grafana-mcp.env"
FLAGS = STATE / "flagd" / "demo.flagd.json"
OVERLAY = STATE / "compose.json"


def compose(*args):
    command = ["docker", "compose", "-p", "otel-demo", "--project-directory", str(ROOT)]
    for path in (ROOT / ".env", ROOT / "demo.env"):
        command += ["--env-file", str(path)]
    for path in (ROOT / "compose.yaml", ROOT / "compose.observability.yaml", OVERLAY):
        command += ["-f", str(path)]
    done = subprocess.run(command + list(args), capture_output=True, timeout=180, check=False)
    if done.returncode:
        raise RuntimeError("owned Demo " + args[0] + " failed; inspect scoped service state")


def settings():
    return json.loads((STATE / "settings.json").read_text())


def variants(failure=False):
    config = settings()
    data = json.loads(FLAGS.read_text())
    if failure:
        updates = {config["failure_flag"]: "on"}
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
    temporary = FLAGS.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(FLAGS)


def prepare():
    STATE.mkdir(mode=0o700, exist_ok=True)
    if STATE.is_symlink() or STATE.stat().st_mode & 0o077:
        raise RuntimeError("owned remote state directory must be private")
    if not TOKEN.exists():
        descriptor = os.open(TOKEN, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write("MCP_GRAFANA_SERVER_TOKEN=" + secrets.token_hex(24) + "\n")
    info = TOKEN.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RuntimeError("remote token must be a private regular file")
    if not FLAGS.exists():
        shutil.copytree(ROOT / "src" / "flagd", FLAGS.parent)
        variants()
    layer = {
        "services": {
            "flagd": {"volumes": [str(FLAGS.parent) + ":/etc/flagd"]},
            "checkout": {"environment": {"FLAGD_CACHE": "disabled"}},
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
    )
    print("owned AWS MCP prepared; token retained, upstream source untouched")


class TokenTransfer(http.server.BaseHTTPRequestHandler):
    """Only the authorized SSM port-forwarding channel can reach this loopback listener."""

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/token":
            self.send_error(404)
            return
        body = TOKEN.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "fail", "reset", "serve-token"))
    action = parser.parse_args().action
    if action == "prepare":
        prepare()
    elif action == "serve-token":
        http.server.HTTPServer(("127.0.0.1", 17900), TokenTransfer).serve_forever()
    else:
        variants(failure=action == "fail")
        compose("restart", "flagd")
        print("owned AWS flag " + action + " applied; synthetic traffic retained")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit(
            "owned AWS operation failed; preserve resources and inspect scoped status"
        ) from None
