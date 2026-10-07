"""Write private, synthetic Compose inputs without printing or sourcing them."""

import argparse
import os
import re
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        parser.error("--source-sha must be a full lowercase Git SHA")
    password = secrets.token_urlsafe(24)
    lines = [
        "POSTGRES_DB=sre_agent",
        "POSTGRES_USER=sre_agent",
        f"POSTGRES_PASSWORD={password}",
        f"DATABASE_URL=postgresql://sre_agent:{password}@db:5432/sre_agent",
        *(
            f"{name}=sre_{secrets.token_urlsafe(32)}"
            for name in (
                "ADMIN_HUMAN_API_KEY",
                "DEMO_HUMAN_API_KEY",
                "INCIDENT_HARNESS_API_KEY",
                "RESTRICTED_HARNESS_API_KEY",
            )
        ),
        "TRIAGE_AGENT_MODEL=openai/gpt-4o-mini",
        "TRIAGE_AGENT_PROVIDER=openai",
        "REMEDIATION_AGENT_MODEL=anthropic/claude-3.5-haiku",
        "REMEDIATION_AGENT_PROVIDER=anthropic",
        f"AUDIT_HMAC_KEY={secrets.token_hex(32)}",
        "SRE_AGENT_APPLICATION_VERSION=0.0.0",
        "SRE_AGENT_CONTRACT_VERSION=2.0.0",
        f"SRE_AGENT_BUILD_REVISION={args.source_sha}",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")
    print("Created private synthetic Compose configuration.")


if __name__ == "__main__":
    main()
