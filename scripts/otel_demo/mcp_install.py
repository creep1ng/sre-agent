"""Producer-owned SSM preparation; payload contains code/configuration, never secrets."""

import base64
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from .common import DEMO_ENV, DIGESTS, MANIFEST, ROOT, DemoError, _parse_datetime
from .guest import _digest_lock, _manifest_pin

REMOTE = "/var/lib/otel-demo-sre"


def manifest_settings():
    text = MANIFEST.read_text()
    try:
        section = text.split("grafana_mcp:", 1)[1].split("\nfailure_injection:", 1)[0]
        image = re.search(r'^\s+image:\s*["\']?([^"\'\s]+)', section, re.MULTILINE).group(1)
        failure = re.search(r"(?m)^  flag: ([A-Za-z0-9_]+)$", text).group(1)
        block = text.split("flag_baseline:\n", 1)[1].split("\nhost_requirements:", 1)[0]
        baseline = dict(
            re.findall(r'^  ([A-Za-z0-9_]+):\s*["\']?([A-Za-z0-9_]+)', block, re.MULTILINE)
        )
        digest = dict(line.split("\t") for line in _digest_lock(DIGESTS).splitlines())[image]
        if "all_other_flags" not in baseline:
            raise ValueError
    except (IndexError, AttributeError, KeyError, ValueError):
        raise DemoError(
            "manifest must declare locked MCP image, failure flag and baseline"
        ) from None
    return {
        "mcp_image": image.rsplit(":", 1)[0] + "@" + digest,
        "failure_flag": failure,
        "baseline": baseline,
    }


def install_command():
    _, pin = _manifest_pin(MANIFEST)
    source = base64.b64encode(Path(__file__).with_name("mcp_guest.py").read_bytes()).decode()
    config = base64.b64encode(json.dumps(manifest_settings(), sort_keys=True).encode()).decode()
    environment = base64.b64encode(DEMO_ENV.read_bytes()).decode()
    rules = base64.b64encode((ROOT / "demo/grafana/alerting/midnight.yaml").read_bytes()).decode()
    return f"""set -eu
test \"$(git -C /opt/otel-demo rev-parse HEAD)\" = '{pin}'
test ! -L {REMOTE}
install -d -m 0700 {REMOTE}
printf '%s' '{config}' | base64 -d >{REMOTE}/settings.candidate
if test -f {REMOTE}/settings.json; then
  cmp -s {REMOTE}/settings.json {REMOTE}/settings.candidate || exit 2
fi
install -m 0600 {REMOTE}/settings.candidate {REMOTE}/settings.json
printf '%s' '{environment}' | base64 -d >{REMOTE}/demo.candidate
if test -f {REMOTE}/demo.env; then
  cmp -s {REMOTE}/demo.env {REMOTE}/demo.candidate || exit 2
fi
install -m 0600 {REMOTE}/demo.candidate {REMOTE}/demo.env
printf '%s' '{source}' | base64 -d >{REMOTE}/guest.candidate
install -m 0600 {REMOTE}/guest.candidate {REMOTE}/mcp_guest.py
install -d -m 0755 {REMOTE}/alerting
printf '%s' '{rules}' | base64 -d >{REMOTE}/rules.candidate
install -m 0644 {REMOTE}/rules.candidate {REMOTE}/alerting/midnight.yaml
python3 {REMOTE}/mcp_guest.py prepare
"""


def current(controller):
    status = controller._current()
    if status["state"] != "running":
        raise DemoError("prepared MCP requires the owned Demo instance running")
    deadline = controller.aws.termination_deadline(instance_id=status["instance_id"])
    if deadline <= datetime.now(UTC) or _parse_datetime(status["expires_at"]) <= datetime.now(UTC):
        raise DemoError("owned Demo deadline expired; do not connect or change flags")
    return status


def execute(controller, command):
    status = current(controller)
    instance = status["instance_id"]
    controller.aws.wait_for_ssm(instance_id=instance)
    result = controller.aws.send_command(
        instance_id=instance,
        document_name="AWS-RunShellScript",
        parameters={"commands": [command]},
    )
    command_id = result.get("CommandId")
    if not command_id:
        raise DemoError("owned SSM operation returned no command identifier")
    until = time.monotonic() + 180
    while time.monotonic() < until:
        try:
            result = controller.aws.call(
                "ssm",
                "get-command-invocation",
                "--command-id",
                command_id,
                "--instance-id",
                instance,
            )
        except DemoError as error:
            if getattr(error, "code", None) != "InvocationDoesNotExist":
                raise
            time.sleep(2)
            continue
        state = result.get("Status")
        if state == "Success":
            return
        if state not in {"Pending", "InProgress", "Delayed"}:
            raise DemoError("owned SSM operation failed; preserve Demo and inspect scoped status")
        time.sleep(2)
    raise DemoError("owned SSM operation timed out; recheck status, never restart blindly")


def prepare(controller):
    execute(controller, install_command())
    return {"mcp": "prepared", "token": "private; not exported", "signals": "not accepted"}


def flags(controller, action):
    if action not in {"fail", "reset"}:
        raise DemoError("only the declared owner fail/reset operations are admitted")
    execute(controller, f"python3 {REMOTE}/mcp_guest.py {action}")
    return {"flags": action, "signals": "verification still required"}
