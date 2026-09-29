"""Evidence-only adapter for a fresh, dedicated local Docker daemon; never AWS."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HEAD = "aa29c08971f7a69575b2d544af1dd4195395ad20"
PROJECT = "audit-runtime370-demo"
ROOT = Path.cwd()
MARKER = ROOT / ".demo-state" / "audit-runtime370-owner.json"
IDENTITY = {"head": HEAD, "project": PROJECT}


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, timeout=240).strip()


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"up", "verify", "down"}:
        fail("usage: demo-audit.py up|verify|down")
    operation = sys.argv[1]
    if command("git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD") != HEAD:
        fail("Refusing a source checkout other than the audited PR370 head.")
    if command("git", "-c", f"safe.directory={ROOT}", "diff", "HEAD", "--", "scripts/demo_env.py", "demo", "compose.demo.yaml"):
        fail("Refusing locally modified demo inputs.")
    if os.environ.get("AUDIT_DEDICATED_DAEMON") != "yes":
        fail("Use a fresh dedicated local Docker daemon; acknowledge with AUDIT_DEDICATED_DAEMON=yes.")
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location("demo_env", ROOT / "scripts/demo_env.py")
    assert spec and spec.loader
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    demo.require_docker()
    cfg = demo.manifest()
    # Environment-only project selection. Tracked source and port policy stay intact.
    cfg["compose"]["project_name"] = PROJECT
    if operation == "up":
        if MARKER.exists():
            fail("This directory already owns an attempt: use verify or down; do not overwrite it.")
        containers = command("docker", "ps", "-a", "--format", '{{.ID}}\t{{.Label "audit.runtime370.runner"}}').splitlines()
        if any(not row.endswith("\ttrue") for row in containers):
            fail("Daemon has non-runner containers; use a fresh dedicated host.")
        if command("docker", "volume", "ls", "-q"):
            fail("Daemon has existing volumes; refusing to reuse or delete them.")
        networks = set(command("docker", "network", "ls", "--format", "{{.Name}}").splitlines())
        if networks - {"bridge", "host", "none"}:
            fail("Daemon has non-default networks; use a fresh dedicated host.")
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(json.dumps(IDENTITY) + "\n")
        demo.ensure_mcp_token()
        demo.MCP_ENV.chmod(0o600)
        # Pull content-addressed images before Compose; never refresh floating tags.
        for line in (ROOT / "demo/digests.lock").read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            ref, digest = line.split()
            immutable = f"{ref}@{digest}"
            subprocess.run(["docker", "pull", immutable], check=True, timeout=240)
            subprocess.run(["docker", "tag", immutable, ref], check=True, timeout=30)
    elif not MARKER.exists() or json.loads(MARKER.read_text()) != IDENTITY:
        fail("No matching local ownership marker: refusing verification or cleanup.")
    demo.OPERATIONS[operation](cfg)
    if operation != "down":
        print(command("docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Names}}\t{{.Ports}}"))


if __name__ == "__main__":
    main()
