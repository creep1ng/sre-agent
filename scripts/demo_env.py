#!/usr/bin/env python3
"""Operate the pinned OpenTelemetry Demo environment (HT-DEMO-ENV, issue #186).

Usage:
    python scripts/demo_env.py up|fail|verify|reset|down

Every operation is idempotent and bounded to the Compose project declared in
demo/manifest.yaml, removes nothing outside it, and never writes to upstream.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "demo" / "manifest.yaml"
LOCK_PATH = ROOT / "demo" / "digests.lock"
OVERLAY = ROOT / "compose.demo.yaml"
CHECKOUT = ROOT / "otel-demo"
FLAGS_DIR = ROOT / ".demo-state" / "flagd"


def abort(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(args: list[str], capture: bool = False) -> str:
    env = {**os.environ, "DEMO_FLAGS_DIR": str(FLAGS_DIR)}
    done = subprocess.run(args, text=True, capture_output=capture, env=env)
    if done.returncode != 0:
        if capture:
            print(done.stderr, file=sys.stderr, end="")
        abort(f"command failed: {' '.join(args)}")
    return done.stdout if capture else ""


def require_docker() -> None:
    """Fail fast with a readable message instead of hanging on a dead socket."""
    probe = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"], text=True, capture_output=True
    )
    if probe.returncode != 0:
        abort("the Docker daemon is not responding; start Docker and run again")


def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        abort(f"{MANIFEST_PATH} is missing")
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def compose(cfg: dict) -> list[str]:
    args = [
        "docker",
        "compose",
        "-p",
        cfg["compose"]["project_name"],
        # Upstream compose files use paths relative to their own checkout.
        "--project-directory",
        str(CHECKOUT),
        "--env-file",
        str(CHECKOUT / ".env"),
        "--env-file",
        str(ROOT / "demo" / "demo.env"),
    ]
    for layer in cfg["compose"]["layers_included"]:
        args += ["-f", str(CHECKOUT / layer)]
    return args + ["-f", str(OVERLAY)]


def ensure_checkout(cfg: dict) -> None:
    upstream = cfg["upstream"]
    if not CHECKOUT.exists():
        print(f"Cloning {upstream['tag']} into {CHECKOUT.name}/")
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                upstream["tag"],
                upstream["repository"],
                str(CHECKOUT),
            ]
        )
    head = run(["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], capture=True).strip()
    if head != upstream["commit"]:
        abort(
            f"{CHECKOUT.name}/ is at {head[:7]} but the manifest pins "
            f"{upstream['commit'][:7]}; remove the directory and run up again"
        )
    if run(["git", "-C", str(CHECKOUT), "status", "--porcelain"], capture=True).strip():
        abort("the upstream checkout has local modifications; it must stay pristine")


def ensure_flags() -> None:
    if FLAGS_DIR.exists():
        return
    FLAGS_DIR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CHECKOUT / "src" / "flagd", FLAGS_DIR)
    print(f"Flag working copy created at {FLAGS_DIR.relative_to(ROOT)}")


def flags_file() -> Path:
    path = FLAGS_DIR / "demo.flagd.json"
    if not path.exists():
        abort("no flag working copy; run up first")
    return path


def conflicting_containers(cfg: dict) -> list[str]:
    """Names the demo needs that another project already holds.

    The demo fixes container_name per service, and names are global to the daemon.
    """
    project = cfg["compose"]["project_name"]
    wanted = set(run(compose(cfg) + ["config", "--services"], capture=True).split())
    listing = run(
        ["docker", "ps", "-a", "--format", '{{.Names}}\t{{.Label "com.docker.compose.project"}}'],
        capture=True,
    )
    return [
        f"{n} (project: {o or 'none'})"
        for n, _, o in (line.partition("\t") for line in listing.splitlines())
        if n in wanted and o != project
    ]


def set_variants(updates: dict[str, str]) -> None:
    path = flags_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, variant in updates.items():
        flag = data["flags"].get(name)
        if flag is None:
            abort(f"flag {name} is not defined in {path.name}")
        if variant not in flag["variants"]:
            abort(f"flag {name} has no variant {variant}")
        flag["defaultVariant"] = variant
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def baseline(cfg: dict) -> dict[str, str]:
    """The declared baseline, expanded over every flag actually present."""
    declared = dict(cfg["flag_baseline"])
    fallback = declared.pop("all_other_flags", "off")
    data = json.loads(flags_file().read_text(encoding="utf-8"))
    return {
        name: declared.get(name, fallback)
        for name, flag in data["flags"].items()
        if declared.get(name, fallback) in flag["variants"]
    }


def unavailable(cfg: dict) -> list[str]:
    """Every service of the project, a superset of the six CA1 names.

    Approving an environment whose checkout is down would not report real failures.
    """
    expected = set(run(compose(cfg) + ["config", "--services"], capture=True).split())
    states = {}
    for line in run(compose(cfg) + ["ps", "--all", "--format", "json"], capture=True).splitlines():
        if line.strip():
            row = json.loads(line)
            states[row["Service"]] = row.get("Health") or row.get("State")
    problems = []
    for name in sorted(expected):
        state = states.get(name)
        if state is None:
            problems.append(f"{name}: not running")
        elif state not in {"healthy", "running"}:
            problems.append(f"{name}: {state}")
    return problems


def digest_drift(cfg: dict) -> list[str]:
    """Detect an upstream tag repointed to different image content."""
    recorded = {}
    for line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            ref, _, digest = line.partition("\t")
            recorded[ref.strip()] = digest.strip()
    problems = []
    for ref in run(compose(cfg) + ["config", "--images"], capture=True).split():
        if ref not in recorded:
            problems.append(f"{ref}: not recorded in digests.lock")
            continue
        local = run(
            ["docker", "image", "inspect", ref, "--format", '{{join .RepoDigests ","}}'],
            capture=True,
        )
        if recorded[ref] not in local:
            problems.append(f"{ref}: digest differs from the lock")
    return problems


def op_up(cfg: dict) -> None:
    ensure_checkout(cfg)
    conflicts = conflicting_containers(cfg)
    if conflicts:
        abort("another project already holds these container names: " + ", ".join(conflicts))
    ensure_flags()
    # Start from the declared baseline so a previous session cannot leak in.
    set_variants(baseline(cfg))
    run(compose(cfg) + ["up", "-d", "--wait"])
    print("Environment is up at the declared flag baseline.")


def op_verify(cfg: dict) -> None:
    problems = unavailable(cfg) + digest_drift(cfg)
    for line in problems:
        print(f"FAIL {line}")
    if problems:
        raise SystemExit(1)
    print("OK every service is available and image digests match the lock.")


def op_fail(cfg: dict) -> None:
    flag = cfg["failure_injection"]["flag"]
    set_variants({flag: "on"})
    run(compose(cfg) + ["restart", "flagd"])
    print(f"{flag} is on; synthetic traffic keeps running.")


def op_reset(cfg: dict) -> None:
    set_variants(baseline(cfg))
    run(compose(cfg) + ["restart", "flagd"])
    print("Flag baseline restored.")


def op_down(cfg: dict) -> None:
    project = cfg["compose"]["project_name"]
    run(compose(cfg) + ["down"])
    left = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            "{{.Names}}",
        ],
        capture=True,
    ).split()
    if left:
        abort("containers survived down: " + ", ".join(left))
    print("Environment is down; nothing outside the project was touched.")


OPERATIONS = {"up": op_up, "fail": op_fail, "verify": op_verify, "reset": op_reset, "down": op_down}


def main() -> None:
    parser = argparse.ArgumentParser(description="Operate the demo environment.")
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    operation = parser.parse_args().operation
    require_docker()
    OPERATIONS[operation](manifest())


if __name__ == "__main__":
    main()
