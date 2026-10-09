"""Prepare private CA1 Compose inputs without exposing credentials.

Failure cases this utility must reject before publishing a configuration:
* missing required CLI inputs, unsafe project identifiers, or non-private/invalid subnets;
* invalid or duplicate environment variable names/values in the generated seed input;
* missing Compose-required environment values or a missing evidence bind mount;
* a checks database that is not the repository's isolated tmpfs service; and
* non-empty/externally supplied provider keys or an environment file that already exists.

The file is created exclusively with mode 0600. Secrets are neither displayed nor
written to the non-secret Compose override. Run from the repository root.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV = {
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "API_PORT",
    "POSTGRES_PORT",
    "WEB_PORT",
    "ADMIN_HUMAN_API_KEY",
    "DEMO_HUMAN_API_KEY",
    "INCIDENT_HARNESS_API_KEY",
    "RESTRICTED_HARNESS_API_KEY",
    "TRIAGE_AGENT_MODEL",
    "TRIAGE_AGENT_PROVIDER",
    "REMEDIATION_AGENT_MODEL",
    "REMEDIATION_AGENT_PROVIDER",
    "AUDIT_HMAC_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MANAGEMENT_API_KEY",
    "RUN_OPENROUTER_LIVE_SMOKE",
    "SRE_AGENT_BUILD_REVISION",
    "SRE_AGENT_APPLICATION_VERSION",
    "SRE_AGENT_CONTRACT_VERSION",
}


def fail(message: str) -> None:
    raise ValueError(message)


def build_revision(override: str | None) -> str:
    if override is not None:
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", override):
            fail("--build-revision must be a 7–64 character hexadecimal Git revision")
        return override
    try:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        fail("cannot derive Git HEAD; pass --build-revision explicitly")
    revision = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", revision):
        fail("Git HEAD did not return a valid hexadecimal revision")
    return revision


def validate_project(value: str) -> str:
    if len(value) > 63 or not re.fullmatch(r"ca1-[a-z0-9][a-z0-9-]*", value):
        fail("project must be 5–63 lowercase letters/digits/hyphens and start with ca1-")
    return value


def validate_subnet(value: str) -> str:
    try:
        subnet = ipaddress.ip_network(value, strict=True)
    except ValueError:
        fail("subnet must be a strict IPv4 network address in CIDR notation")
    if subnet.version != 4 or not subnet.is_private or subnet.prefixlen != 28:
        fail("subnet must be an unused private IPv4 /28 network")
    return str(subnet)


def validate_port(value: int, name: str) -> int:
    if not 1024 <= value <= 65535:
        fail(f"{name} must be an unprivileged TCP port (1024–65535)")
    return value


def compose_source_is_safe(path: Path) -> None:
    """Fail closed if the repository moves checks off its disposable tmpfs DB."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        fail("repository compose.yaml is unavailable")
    match = re.search(r"(?m)^  python-checks-db:\n(?P<block>(?:^    [^\n]*\n|^\n)*)", text)
    isolated = (
        match
        and "POSTGRES_DB: python_checks" in match["block"]
        and "POSTGRES_USER: python_checks" in match["block"]
        and "tmpfs:" in match["block"]
        and "volumes:" not in match["block"]
    )
    if not isolated:
        fail("compose.yaml must keep python-checks-db on tmpfs with no persistent volumes")
    checks = re.search(r"(?m)^  python-checks:\n(?P<block>(?:^    [^\n]*\n|^\n)*)", text)
    if (
        not checks
        or "python-checks-db" not in checks["block"]
        or "DATABASE_URL: postgresql://python_checks@python-checks-db:5432/python_checks"
        not in checks["block"]
        or "DEMO_DATABASE_URL" not in checks["block"]
    ):
        fail("compose.yaml must keep python-checks isolated and expose DEMO_DATABASE_URL")


def entries(args: argparse.Namespace, revision: str) -> list[tuple[str, str]]:
    values = [
        ("POSTGRES_DB", "ca1_http_restart"),
        ("POSTGRES_USER", "ca1_local"),
        ("POSTGRES_PASSWORD", secrets.token_hex(24)),
        ("API_PORT", str(args.api_port)),
        ("POSTGRES_PORT", str(args.db_port)),
        ("WEB_PORT", "58139"),
        ("TRIAGE_AGENT_MODEL", "controlled/no-model"),
        ("TRIAGE_AGENT_PROVIDER", "controlled"),
        ("REMEDIATION_AGENT_MODEL", "controlled/no-model"),
        ("REMEDIATION_AGENT_PROVIDER", "controlled"),
        ("AUDIT_HMAC_KEY", secrets.token_hex(32)),
        ("OPENROUTER_API_KEY", ""),
        ("OPENROUTER_MANAGEMENT_API_KEY", ""),
        ("RUN_OPENROUTER_LIVE_SMOKE", "0"),
        ("SRE_AGENT_BUILD_REVISION", revision),
        ("SRE_AGENT_APPLICATION_VERSION", "0.1.0"),
        ("SRE_AGENT_CONTRACT_VERSION", "2.7.0"),
    ]
    values.extend(
        (name, "sre_" + secrets.token_hex(24))
        for name in (
            "ADMIN_HUMAN_API_KEY",
            "DEMO_HUMAN_API_KEY",
            "INCIDENT_HARNESS_API_KEY",
            "RESTRICTED_HARNESS_API_KEY",
        )
    )
    password = dict(values)["POSTGRES_PASSWORD"]
    values.append(
        (
            "DATABASE_URL",
            f"postgresql://ca1_local:{password}@db:5432/ca1_http_restart",
        )
    )
    names = [name for name, _ in values]
    if len(names) != len(set(names)):
        fail("generated environment contains duplicate variable names")
    if any(
        not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or "\n" in value or "\r" in value
        for name, value in values
    ):
        fail("generated environment contains an invalid name or value")
    environment = dict(values)
    missing = REQUIRED_ENV - environment.keys()
    empty = REQUIRED_ENV - {
        name
        for name, value in values
        if value or name in {"OPENROUTER_API_KEY", "OPENROUTER_MANAGEMENT_API_KEY"}
    }
    if missing or empty:
        fail("generated environment is missing required Compose inputs")
    if environment["OPENROUTER_API_KEY"] or environment["OPENROUTER_MANAGEMENT_API_KEY"]:
        fail("external provider credentials must remain unset")
    return values


def write_exclusive(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(content)


def compose_override(project: str, subnet: str, private_dir: Path, evidence_dir: Path) -> str:
    env_file = json.dumps(str(private_dir / "local.env"))
    evidence = json.dumps(str(evidence_dir))
    return f"""services:
  migrate:
    image: {project}-api:latest
  seed:
    image: {project}-api:latest
  python-checks:
    volumes:
      - type: bind
        source: {evidence}
        target: /evidence
    env_file:
      - {env_file}
networks:
  runtime:
    internal: true
    ipam:
      config:
        - subnet: {subnet}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", required=True, type=validate_project)
    parser.add_argument("--private-dir", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--subnet", required=True, type=validate_subnet)
    parser.add_argument(
        "--api-port", required=True, type=lambda value: validate_port(int(value), "API port")
    )
    parser.add_argument(
        "--db-port", required=True, type=lambda value: validate_port(int(value), "DB port")
    )
    parser.add_argument("--build-revision", help="Git revision to record (default: current HEAD)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        revision = build_revision(args.build_revision)
        compose_source_is_safe(REPOSITORY_ROOT / "compose.yaml")
        if args.api_port == args.db_port or 58139 in {args.api_port, args.db_port}:
            fail("API, database, and fixed web ports must be distinct")
        private_dir = args.private_dir.expanduser().resolve()
        evidence_dir = args.evidence_dir.expanduser().resolve()
        if private_dir == REPOSITORY_ROOT or REPOSITORY_ROOT in private_dir.parents:
            fail("private configuration must be outside the repository")
        if (
            private_dir == evidence_dir
            or private_dir in evidence_dir.parents
            or evidence_dir in private_dir.parents
        ):
            fail("private configuration and evidence directories must not overlap")
        env_path, override_path = private_dir / "local.env", private_dir / "compose.proof.yaml"
        if env_path.exists() or override_path.exists():
            fail("refusing to replace existing local.env or compose.proof.yaml")
        private_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        values = entries(args, revision)
        env_content = "".join(f"{name}={value}\n" for name, value in values)
        env_created = False
        try:
            write_exclusive(env_path, env_content)
            env_created = True
            if stat.S_IMODE(env_path.stat().st_mode) != 0o600:
                fail("private environment file permissions are not mode 0600")
            override = compose_override(args.project, args.subnet, private_dir, evidence_dir)
            if "env_file:" not in override or "target: /evidence" not in override:
                fail("Compose override must inject local.env and mount the evidence directory")
            write_exclusive(
                override_path,
                override,
            )
        except Exception:
            if env_created:
                env_path.unlink(missing_ok=True)
            raise
    except (OSError, ValueError) as exc:
        print(f"prepare-ca1-config: {exc}", file=sys.stderr)
        return 2
    print("Created private synthetic configuration; secrets not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
