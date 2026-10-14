"""Black-box CLI negatives, authored before the setup/config entrypoints.

Requires Python stdlib only. Never invokes Docker successfully: bad config must
stop before mutation. Fixtures are synthetic, private, and discarded. Failure
modes: missing key, duplicated identity prefixes, malformed route, injected env,
non-private token, project/mode/port conflicts, unsupported AWS accepted as ready.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="sre618-preflight-") as tmp:
        directory = Path(tmp)
        token = directory / "grafana-mcp.env"
        token.write_text("MCP_GRAFANA_SERVER_TOKEN=synthetic-mcp-token-for-tests\n")
        token.chmod(0o600)
        defaults = "\n".join(
            line
            for line in (ROOT / ".env.example").read_text().splitlines()
            if not line.startswith(("SRE_", "DEMO_STATE_DIR="))
        )
        import re

        replacements = {
            "ADMIN_HUMAN_API_KEY": "sre_admin" + "a" * 40,
            "DEMO_HUMAN_API_KEY": "sre_human" + "b" * 40,
            "INCIDENT_HARNESS_API_KEY": "sre_agent" + "c" * 40,
            "RESTRICTED_HARNESS_API_KEY": "sre_deny0" + "d" * 40,
            "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
            "TRIAGE_AGENT_PROVIDER": "openai",
            "REMEDIATION_AGENT_MODEL": "openai/gpt-4o-mini",
            "REMEDIATION_AGENT_PROVIDER": "openai",
            "AUDIT_HMAC_KEY": "e" * 64,
        }
        for key, value in replacements.items():
            defaults = re.sub(r"^" + key + r"=.*$", key + "=" + value, defaults, flags=re.M)
        defaults += f"\nSRE_SETUP_PROJECT=sre-618-negative\nDEMO_STATE_DIR={directory}\n"
        cases = {
            "missing-key": defaults.replace(replacements["DEMO_HUMAN_API_KEY"], ""),
            "duplicate-prefix": defaults.replace(
                replacements["DEMO_HUMAN_API_KEY"], replacements["ADMIN_HUMAN_API_KEY"]
            ),
            "route": defaults.replace("openai/gpt-4o-mini", "<lab/model>"),
            "injection": defaults + "\nUNTRUSTED=$(touch /tmp/sre618-must-not-exist)\n",
            "project": defaults.replace("sre-618-negative", "otel-demo"),
            "mode": defaults + "\nSRE_OTEL_MODE=invalid\n",
            "aws-blocked": defaults + "\nSRE_OTEL_MODE=aws\n",
            "port": defaults.replace("API_PORT=8000", "API_PORT=0"),
        }
        expected = {
            "missing-key": "DEMO_HUMAN_API_KEY",
            "duplicate-prefix": "prefixes",
            "route": "TRIAGE_AGENT_MODEL",
            "injection": "interpolation",
            "project": "SRE_SETUP_PROJECT",
            "mode": "SRE_OTEL_MODE",
            "aws-blocked": "AWS blocked",
            "port": "ports must be distinct",
        }
        for name, content in cases.items():
            config = directory / (name + ".env")
            config.write_text(content)
            config.chmod(0o600)
            done = subprocess.run(
                [sys.executable, str(ROOT / "scripts/setup_sre.py"), "--env-file", str(config)],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "COMPOSE_FILE": "/no/ambient/compose.yaml"},
            )
            assert done.returncode != 0, name
            assert "setup:" in done.stderr and expected[name] in done.stderr, (name, done.stderr)
            assert not any(value in done.stdout + done.stderr for value in replacements.values()), (
                name
            )
            assert not Path("/tmp/sre618-must-not-exist").exists()
            print(name + ": rejected before Docker mutation; sanitized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
