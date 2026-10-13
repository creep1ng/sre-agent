"""Private, literal configuration contract for the local SRE setup entrypoint."""

import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
KEYS = (
    "ADMIN_HUMAN_API_KEY",
    "DEMO_HUMAN_API_KEY",
    "INCIDENT_HARNESS_API_KEY",
    "RESTRICTED_HARNESS_API_KEY",
)


class SetupError(RuntimeError):
    """Only deliberately sanitized diagnostics may leave the setup process."""


def private_file(path):
    try:
        info = path.lstat()
    except OSError:
        raise SetupError("private configuration/token missing; prepare it before setup") from None
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise SetupError("configuration/token must be an owned regular file with mode 0600")


def literal_env(path):
    private_file(path)
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise SetupError("configuration uses KEY=value lines only")
        if name.startswith(("COMPOSE_", "DOCKER_")):
            raise SetupError("COMPOSE_/DOCKER_ overrides are unsupported; use the setup contract")
        if name in values or any(c in value for c in ("$", "`", "\x00", "\r")):
            raise SetupError("duplicate keys/interpolation are unsupported; use literal values")
        if value.startswith(("'", '"')):
            raise SetupError("use unquoted literal values; no shell syntax")
        values[name] = value
    return values


def load_config(path):
    values = literal_env(path)
    mode = values.get("SRE_OTEL_MODE", "local")
    if mode == "aws":
        raise SetupError(
            "AWS blocked: #494 producer/connection interface is not integrated; "
            "no resources were launched. Select local or wait for #494"
        )
    if mode != "local":
        raise SetupError("SRE_OTEL_MODE must be local or aws")
    project = values.get("SRE_SETUP_PROJECT", "sre-demo")
    if not re.fullmatch(r"sre-[a-z0-9][a-z0-9_-]{0,40}", project):
        raise SetupError(
            "SRE_SETUP_PROJECT must start with sre-; never use an OTel/foreign project"
        )
    for name in KEYS:
        if not re.fullmatch(r"sre_[A-Za-z0-9_-]{28,128}", values.get(name, "")):
            raise SetupError(name + " missing/invalid; provide a private unique demo credential")
    if len({values[name][:8] for name in KEYS}) != 4:
        raise SetupError("API key first-eight-character prefixes must be unique")
    audit = values.get("AUDIT_HMAC_KEY", "")
    if len(audit) < 32 or any(c in audit for c in "<>"):
        raise SetupError(
            "AUDIT_HMAC_KEY requires a non-placeholder secret of at least 32 characters"
        )
    for prefix in ("TRIAGE_AGENT", "REMEDIATION_AGENT"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+", values.get(prefix + "_MODEL", "")):
            raise SetupError(prefix + "_MODEL must use a valid lab/model assignment")
        provider = values.get(prefix + "_PROVIDER", "")
        if not 1 <= len(provider) <= 100 or any(c in provider for c in "<>"):
            raise SetupError(prefix + "_PROVIDER must be a non-placeholder provider assignment")
    try:
        ports = [
            int(values.get(name, str(default)))
            for name, default in (("API_PORT", 8000), ("WEB_PORT", 8080), ("POSTGRES_PORT", 5432))
        ]
        timeout = float(values.get("OPENROUTER_TIMEOUT_SECONDS", "30"))
    except ValueError:
        raise SetupError("ports/timeout must be numeric") from None
    if len(set(ports)) != 3 or any(not 1024 <= port <= 65535 for port in ports):
        raise SetupError("API/WEB/POSTGRES ports must be distinct, within 1024..65535")
    if not 0 < timeout <= 120:
        raise SetupError("OPENROUTER_TIMEOUT_SECONDS must be within (0,120]")
    db = urlsplit(values.get("DATABASE_URL", ""))
    if db.scheme != "postgresql" or db.hostname != "db" or db.port != 5432:
        raise SetupError("DATABASE_URL must target this Compose project's db:5432")
    if (
        db.username != values.get("POSTGRES_USER")
        or db.password != values.get("POSTGRES_PASSWORD")
        or db.path != "/" + values.get("POSTGRES_DB", "")
    ):
        raise SetupError("DATABASE_URL must agree with POSTGRES_*; do not target another database")
    state = Path(values.get("DEMO_STATE_DIR", str(ROOT / ".demo-state"))).resolve()
    token = literal_env(state / "grafana-mcp.env")
    if set(token) != {"MCP_GRAFANA_SERVER_TOKEN"} or len(token["MCP_GRAFANA_SERVER_TOKEN"]) < 24:
        raise SetupError("MCP token file must contain only a valid MCP_GRAFANA_SERVER_TOKEN")
    network = values.get("SRE_MCP_NETWORK", "sre-mcp-boundary")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", network):
        raise SetupError("SRE_MCP_NETWORK must identify the prepared private MCP boundary")
    values.update(SRE_OTEL_MODE=mode, SRE_SETUP_PROJECT=project, DEMO_STATE_DIR=str(state))
    return values
