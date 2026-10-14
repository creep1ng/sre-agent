#!/usr/bin/env python3
"""Canonical, local-only SRE setup; Docker/Compose own every domain operation."""

import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from setup_config import ROOT, SetupError, load_config


def run(args, env, stage):
    try:
        done = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        raise SetupError(
            stage + ": unavailable/timed out; check Docker and retry this command"
        ) from None
    if done.returncode:
        # Compose expands secrets in config/errors. Never forward captured diagnostics.
        raise SetupError(
            stage + ": failed; inspect project status locally, correct the cause, "
            "then rerun setup; no data or foreign resources were removed"
        )
    return done.stdout


def request(base, path, key=None, body=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None if body is None else json.dumps(body).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(base + path, data, headers), timeout=35
        ) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (OSError, ValueError):
        raise SetupError(
            "readiness destination unavailable/invalid; check the selected project/OTel"
        ) from None


def check_checkout(listing):
    for row in listing:
        labels = row.get("Labels", "")
        if isinstance(labels, str):
            labels = dict(part.split("=", 1) for part in labels.split(",") if "=" in part)
        if labels.get("com.docker.compose.project.working_dir") != str(ROOT):
            raise SetupError("project belongs to another checkout; choose a new SRE_SETUP_PROJECT")


def setup(path, stop=False):
    config = load_config(path, stopping=stop)
    # Ignore ambient Compose/remote-Docker overrides. This entrypoint is Unix local only.
    env = {name: os.environ[name] for name in ("PATH", "HOME", "TMPDIR") if name in os.environ}
    env.update(config, DOCKER_HOST="unix:///var/run/docker.sock")
    version = (
        run(["docker", "compose", "version", "--short"], env, "Compose preflight")
        .strip()
        .lstrip("v")
    )
    try:
        parts = tuple(int(part) for part in version.split(".")[:3])
        if parts < (2, 24, 4):
            raise ValueError
    except ValueError:
        raise SetupError("Docker Compose >=2.24.4 is required") from None
    run(["docker", "info", "--format", "{{.ServerVersion}}"], env, "Docker daemon preflight")
    base = [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--env-file",
        str(path),
        "-p",
        config["SRE_SETUP_PROJECT"],
        "-f",
        str(ROOT / "compose.yaml"),
    ]
    if stop:
        text = run(
            [
                "docker",
                "ps",
                "--all",
                "--filter",
                "label=com.docker.compose.project=" + config["SRE_SETUP_PROJECT"],
                "--format",
                "{{json .}}",
            ],
            env,
            "scoped SRE ownership",
        )
        check_checkout([json.loads(line) for line in text.splitlines() if line.strip()])
        # Base services need no MCP env_file. Orphans are confined to this checked
        # project (e.g. the one-shot MCP seed); no volumes or owner resources go.
        run(base + ["down", "--remove-orphans"], env, "scoped SRE stop")
        print("setup: SRE stopped; data/OTel/foreign projects preserved")
        return
    internal = run(
        [
            "docker",
            "network",
            "inspect",
            config.get("SRE_MCP_NETWORK", "sre-mcp-boundary"),
            "--format",
            "{{.Internal}}",
        ],
        env,
        "prepared MCP network",
    )
    if internal.strip() != "true":
        raise SetupError(
            "MCP boundary must be an existing internal network; prepare selected OTel "
            "through its owner CLI separately"
        )
    layer = {
        "networks": {"mcp-boundary": {"name": config.get("SRE_MCP_NETWORK", "sre-mcp-boundary")}},
        "services": {
            "seed": {
                "volumes": [str(ROOT / "scripts") + ":/setup:ro"],
                "environment": {"AUDIT_HMAC_KEY": "${AUDIT_HMAC_KEY:?required}"},
            },
            "api": {"environment": {"OPENROUTER_API_KEY": "", "OPENROUTER_MANAGEMENT_API_KEY": ""}},
        },
    }
    paid = config.get("SRE_ENABLE_PAID_LLM", "0")
    if paid not in {"0", "1"} or (paid == "1" and not config.get("OPENROUTER_API_KEY")):
        raise SetupError("SRE_ENABLE_PAID_LLM must be 0 or explicitly 1 with an API-owned key")
    if paid == "1":
        layer["services"]["api"]["environment"]["OPENROUTER_API_KEY"] = (
            "${OPENROUTER_API_KEY:?required}"
        )
    for network, setting in (
        ("runtime", "SRE_RUNTIME_SUBNET"),
        ("mcp-consumer", "SRE_CONSUMER_SUBNET"),
    ):
        if config.get(setting):
            import ipaddress

            try:
                subnet = str(ipaddress.IPv4Network(config[setting]))
            except ValueError:
                raise SetupError(
                    setting + " must be an explicit non-overlapping private IPv4 subnet"
                ) from None
            if not ipaddress.IPv4Network(subnet).is_private:
                raise SetupError(setting + " must be private")
            layer.setdefault("networks", {})[network] = {"ipam": {"config": [{"subnet": subnet}]}}
    state = Path(config["DEMO_STATE_DIR"]) / "sre-setup"
    state.mkdir(mode=0o700, exist_ok=True)
    overlay = state / (config["SRE_SETUP_PROJECT"] + ".json")
    serialized = json.dumps(layer, sort_keys=True)
    if overlay.is_symlink():
        raise SetupError("setup overlay must not be a symlink")
    if overlay.exists() and overlay.read_text() != serialized:
        raise SetupError(
            "setup overlay conflict; retain existing state, review config or choose a new project"
        )
    if not overlay.exists():
        with overlay.open("x") as stream:
            stream.write(serialized)
        overlay.chmod(0o600)
    compose = base + [
        "-f",
        str(ROOT / "compose.mcp.yaml"),
        "-f",
        str(overlay),
    ]
    resolved = json.loads(
        run(
            compose + ["--profile", "harness", "config", "--format", "json"],
            env,
            "Compose configuration",
        )
    )
    listing_text = run(compose + ["ps", "--all", "--format", "json"], env, "port preflight")
    try:
        listing = json.loads(listing_text or "[]")
    except json.JSONDecodeError:
        listing = [json.loads(line) for line in listing_text.splitlines() if line.strip()]
    if isinstance(listing, dict):
        listing = [listing]
    check_checkout(listing)
    owned_ports = {
        row["Service"]: {item["PublishedPort"] for item in row.get("Publishers", []) or []}
        for row in listing
        if row.get("State") == "running"
    }
    for service, variable in (("api", "API_PORT"), ("web", "WEB_PORT"), ("db", "POSTGRES_PORT")):
        port = int(config.get(variable, {"api": 8000, "web": 8080, "db": 5432}[service]))
        if port in owned_ports.get(service, set()):
            continue
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
        except OSError:
            raise SetupError(
                variable + " occupied; choose a free port in private config and rerun"
            ) from None
    harness = resolved["services"]["harness"]
    if set(harness["networks"]) != {"mcp-consumer"}:
        raise SetupError("harness isolation conflict; restore the shipped Compose files")
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MANAGEMENT_API_KEY", "MCP_GRAFANA_SERVER_TOKEN"):
        if harness.get("environment", {}).get(name):
            raise SetupError("harness secret boundary conflict; restore the shipped Compose files")
    for stage, args in (
        ("database", ["up", "--wait", "db"]),
        ("migrations", ["run", "--build", "--rm", "migrate"]),
        ("seed", ["run", "--build", "--rm", "seed"]),
        ("MCP registry", ["run", "--build", "--rm", "mcp-seed"]),
        ("demo permissions", ["run", "--rm", "seed", "python", "/setup/provision_demo.py"]),
        ("API/web", ["up", "--build", "--no-deps", "--wait", "api", "web"]),
    ):
        run(compose + args, env, stage)
        print("setup: " + stage + " ready")
    base = "http://127.0.0.1:" + config.get("API_PORT", "8000")
    if request(base, "/health/ready")[0] != 200:
        raise SetupError("schema/API not ready; inspect migrations and rerun")
    for key in ("DEMO_HUMAN_API_KEY", "INCIDENT_HARNESS_API_KEY"):
        status, body = request(base, "/v1/mcp/discovery", config[key])
        if status != 200 or {tool["tool_id"] for tool in body.get("tools", [])} != {
            "query_prometheus",
            "query_elasticsearch",
        }:
            raise SetupError("governed MCP discovery not ready; inspect demo grants/registry")
    for tool, body in (
        (
            "query_prometheus",
            {
                "datasource_uid": "webstore-metrics",
                "expr": "up",
                "query_type": "instant",
                "end_time": "now",
            },
        ),
        (
            "query_elasticsearch",
            {
                "datasource_uid": "webstore-logs",
                "index": "otel-logs-*",
                "query": "*",
                "start_time": "now-5m",
                "end_time": "now",
                "limit": 1,
            },
        ),
    ):
        if (
            request(base, "/v1/mcp/tools/" + tool, config["INCIDENT_HARNESS_API_KEY"], body)[0]
            != 200
        ):
            raise SetupError(
                "OTel/MCP destination not ready; inspect selected OTel owner connection; "
                "no OTel reset was attempted"
            )
    if request(base, "/v1/mcp/discovery", config["RESTRICTED_HARNESS_API_KEY"])[0] != 403:
        raise SetupError("restricted identity unexpectedly allowed; review grants")
    print(
        "setup: " + config["SRE_OTEL_MODE"] + " OTel/MCP governed connectivity ready; "
        "functional acceptance NOT tested"
    )
    print("setup: API " + base + "; web http://127.0.0.1:" + config.get("WEB_PORT", "8080"))
    print("setup: paid LLM " + ("explicitly enabled" if paid == "1" else "disabled"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument(
        "--down", action="store_true", help="stop only SRE; preserve volumes and OTel"
    )
    args = parser.parse_args()
    try:
        setup(args.env_file.absolute(), args.down)
    except SetupError as error:
        print("setup: " + str(error), file=sys.stderr)
        return 1
    except Exception:
        print(
            "setup: invalid configuration/unavailable; correct private inputs and rerun; "
            "no cleanup performed",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
