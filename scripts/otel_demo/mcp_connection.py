"""Publish a private AWS connection contract. Only SRE API consumes the caller token."""

import json
import os
import re
import stat
import tempfile
import time
import urllib.request

from .common import ROOT, DemoError
from .mcp_channel import docker, local_link, tunnel
from .mcp_install import REMOTE, current, execute


def private(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise DemoError("AWS connection metadata/token must be owned private regular files")


def handoff(controller, state, status, port):
    token = state / "grafana-mcp.env"
    contract = state / "connection.json"
    if token.exists():
        private(token)
        private(contract)
        if json.loads(contract.read_text())["instance_id"] != status["instance_id"]:
            raise DemoError("existing token belongs to another Demo; choose new private state")
        return  # Producer never reads a retained local token; only the API does.
    command = (
        "systemctl is-active --quiet otel-demo-token-handoff.service || "
        "systemd-run --collect --unit=otel-demo-token-handoff "
        "--property=RuntimeMaxSec=120 --property=StandardOutput=null "
        "--property=StandardError=null python3 " + REMOTE + "/mcp_guest.py serve-token"
    )
    execute(controller, command)
    try:
        with tunnel(controller.aws, status["instance_id"], 17900, port):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/token", timeout=20) as response:
                payload = response.read(513)
            if not re.fullmatch(rb"MCP_GRAFANA_SERVER_TOKEN=[0-9a-f]{48}\n", payload):
                raise DemoError("private token handoff returned invalid data; nothing printed")
            descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
    finally:
        execute(controller, "systemctl stop otel-demo-token-handoff.service")


def publish(state, status, network, connected=False):
    target = state / "connection.json"
    if target.exists():
        private(target)
        old = json.loads(target.read_text())
        if old["network"] != network or old["instance_id"] != status["instance_id"]:
            raise DemoError("AWS contract conflict; retain existing configuration and data")
    data = {
        "version": 1,
        "mode": "aws",
        "network": network,
        "endpoint": "http://grafana-mcp:8000/mcp",
        "instance_id": status["instance_id"],
        "expires_at": status["expires_at"],
        "state": "connected" if connected else "disconnected",
    }
    with tempfile.NamedTemporaryFile(
        mode="w", dir=state, prefix=".connection-", delete=False
    ) as stream:
        json.dump(data, stream, sort_keys=True)
        temporary = stream.name
    os.replace(temporary, target)


def probe(network, image):
    # An anonymous check only: this runner mounts/receives no token or provider key.
    code = """import json,sys,urllib.request,urllib.error
body=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'producer','version':'1'}}}).encode()
request=urllib.request.Request('http://grafana-mcp:8000/mcp',body,{
'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=15) as r:
        sys.exit(1)
except urllib.error.HTTPError as e:
    sys.exit(0 if e.code==401 else 1)
"""
    for attempt in range(5):
        try:
            docker(
                "run", "--rm", "--pull", "never", "--network", network, image, "python", "-c", code
            )
            return
        except DemoError:
            if attempt == 4:
                raise DemoError(
                    "AWS MCP link unavailable or anonymous access not denied; "
                    "retry owner connection"
                ) from None
            time.sleep(1)


def connect(controller, state, network, subnet, port):
    if not 1024 <= port <= 65534:
        raise DemoError("MCP local port and its token-handoff companion must be unprivileged")
    if state.is_symlink():
        raise DemoError("AWS connection directory must not be a symlink")
    state = state.resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o077:
        raise DemoError("AWS connection directory must be owned and private")
    status = current(controller)
    publish(state, status, network)
    handoff(controller, state, status, port + 1)
    with tunnel(controller.aws, status["instance_id"], 17800, port) as process:
        with local_link(state, network, subnet, port, status["instance_id"]):
            image = re.search(
                r"(?m)^FROM (python:[^ ]+)", (ROOT / "docker/api.Dockerfile").read_text()
            ).group(1)
            probe(network, image)
            publish(state, status, network, connected=True)
            print(
                "AWS MCP private connection prepared; keep this owner process running", flush=True
            )
            print("private contract: " + str(state / "connection.json"), flush=True)
            print("token API-only; SRE readiness and signal recovery NOT accepted", flush=True)
            try:
                process.wait()
            finally:
                publish(state, status, network)
            raise DemoError(
                "owned MCP tunnel ended; contract retained, reconnect through owner CLI"
            )
