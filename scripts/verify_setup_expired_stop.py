"""Real scoped stop with an expired producer; no MCP token/owner credentials read."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from setup_config import ROOT, literal_env


def main():
    path = Path(sys.argv[1]).resolve()
    config = literal_env(path)
    project = config["SRE_SETUP_PROJECT"]
    assert project == "sre-618-aws", "explicit old owned project only"
    state = Path(config["DEMO_STATE_DIR"])
    connection = json.loads((state / "connection.json").read_text())
    assert datetime.fromisoformat(connection["expires_at"]) < datetime.now(UTC)
    docker = ["docker", "--host", "unix:///var/run/docker.sock"]

    def rows(selected):
        result = subprocess.check_output(
            docker
            + [
                "ps",
                "--all",
                "--filter",
                "label=com.docker.compose.project=" + selected,
                "--format",
                "{{.ID}} {{.State}}",
            ],
            text=True,
        )
        return sorted(result.splitlines())

    protected = rows("sre-618-aws-container")
    assert protected and rows(project), "owned fixtures must exist before stop"
    volumes = subprocess.check_output(
        docker
        + [
            "volume",
            "ls",
            "--filter",
            "label=com.docker.compose.project=" + project,
            "--format",
            "{{.Name}}",
        ],
        text=True,
    )
    assert volumes.strip(), "persistent owned volume must exist"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/setup_sre.py"), "--env-file", str(path), "--down"],
        capture_output=True,
        text=True,
        timeout=120,
        env={k: v for k, v in os.environ.items() if not k.startswith("AWS_")},
    )
    secrets = [v for k, v in config.items() if v and ("KEY" in k or "PASSWORD" in k)]
    assert not any(v in result.stdout + result.stderr for v in secrets), "secret output"
    print(result.stdout + result.stderr, end="", flush=True)
    print("selected stop exit=" + str(result.returncode), flush=True)
    assert result.returncode == 0, "expired producer must not block SRE-only stop"
    assert not rows(project), "selected SRE containers still present"
    assert rows("sre-618-aws-container") == protected, "protected project changed"
    for volume in volumes.splitlines():
        subprocess.run(docker + ["volume", "inspect", volume], capture_output=True, check=True)
    print("EXPIRED STOP PASS: selected containers absent; volumes/protected project retained")


if __name__ == "__main__":
    main()
