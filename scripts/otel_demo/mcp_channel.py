"""Local producer transport: native SSM -> private Unix socket -> internal Docker link."""

import ipaddress
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .common import ROOT, DemoError
from .mcp_pipe import Pipe, UnixPipe


def docker(*args):
    env = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    done = subprocess.run(["docker", *args], capture_output=True, text=True, env=env, timeout=120)
    if done.returncode:
        raise DemoError("owned local MCP link failed; inspect its project, image, ports or subnet")
    return done.stdout


@contextmanager
def tunnel(aws, instance, remote, local):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", local))
        except OSError:
            raise DemoError(
                "local SSM port occupied; choose a free port or retain existing link"
            ) from None
    command = [
        "aws",
        "--profile",
        aws.profile,
        "--region",
        aws.region,
        "--no-cli-pager",
        "ssm",
        "start-session",
        "--target",
        instance,
        "--document-name",
        "AWS-StartPortForwardingSession",
        "--parameters",
        json.dumps({"portNumber": [str(remote)], "localPortNumber": [str(local)]}),
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise DemoError("owned SSM forwarding failed; verify plugin and prepared Demo")
            try:
                with socket.create_connection(("127.0.0.1", local), timeout=1):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise DemoError("owned SSM forwarding unavailable within bounded wait")
        yield process
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def free_subnet():
    """A private /24 no local Docker network uses: Docker's own pools can be exhausted, and a
    stale network can hold the subnet an earlier connection picked."""
    names = docker("network", "ls", "--format", "{{.ID}}").split()
    used = [
        ipaddress.ip_network(item["Subnet"])
        for info in json.loads(docker("network", "inspect", *names) if names else "[]")
        for item in (info.get("IPAM") or {}).get("Config") or ()
        if item.get("Subnet")
    ]
    for third in range(256):
        candidate = ipaddress.IPv4Network(f"10.231.{third}.0/24")
        if not any(candidate.overlaps(net) for net in used if net.version == 4):
            return str(candidate)
    raise DemoError("no free private /24 in 10.231.0.0/16; pass an explicit --subnet")


def image(name):
    """The pinned relay image, pulled once if missing: the link then runs with --pull never."""
    try:
        docker("image", "inspect", "--format", "{{.Id}}", name)
    except DemoError:
        docker("pull", "--quiet", name)
    return name


@contextmanager
def local_link(state, network, subnet, port, instance, alias="grafana-mcp"):
    if not re.fullmatch(r"sre-[a-z0-9_-]{3,55}", network):
        raise DemoError("AWS MCP network must use a dedicated sre- name")
    if subnet and not ipaddress.IPv4Network(subnet).is_private:
        raise DemoError("explicit MCP subnet must be private")
    networks = json.loads(
        docker("network", "ls", "--filter", "name=^" + network + "$", "--format", "json") or "null"
    )
    if networks:
        info = json.loads(docker("network", "inspect", network))[0]
        if not info["Internal"] or info["Labels"].get("sre.otel.owner") != "aws-ssm":
            raise DemoError("network conflict; preserve foreign resources and choose another name")
        if subnet and subnet not in {item["Subnet"] for item in info["IPAM"]["Config"]}:
            raise DemoError("existing MCP network subnet differs; preserve it")
    else:
        args = ["network", "create", "--internal", "--label", "sre.otel.owner=aws-ssm"]
        docker(*args, "--subnet", subnet or free_subnet(), network)
    transport = state / "transport"
    transport.mkdir(mode=0o700, exist_ok=True)
    if transport.is_symlink() or transport.stat().st_mode & 0o077:
        raise DemoError("transport directory must be private and owned")
    path = transport / (alias + ".sock")
    if path.exists():
        raise DemoError("transport socket exists; retain active link or review stale owned state")
    name = network + "-link"
    relay = image(
        re.search(r"(?m)^FROM (python:[^ ]+)", (ROOT / "docker/api.Dockerfile").read_text()).group(
            1
        )
    )
    with UnixPipe(str(path), Pipe) as server:
        path.chmod(0o600)
        server.port = port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        created = False
        try:
            docker(
                "run",
                "-d",
                "--pull",
                "never",
                "--name",
                name,
                "--network",
                network,
                "--network-alias",
                alias,
                "--label",
                "sre.otel.owner=aws-ssm",
                "--label",
                "sre.otel.instance=" + instance,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                str(transport) + ":/transport:ro",
                "-v",
                str(Path(__file__).with_name("mcp_pipe.py")) + ":/pipe.py:ro",
                relay,
                "python",
                "/pipe.py",
                "--socket",
                "/transport/" + path.name,
            )
            created = True
            yield
        finally:
            if created:
                docker("rm", "-f", name)
            server.shutdown()
            worker.join(timeout=5)
            path.unlink(missing_ok=True)
