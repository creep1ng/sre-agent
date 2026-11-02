#!/usr/bin/env python3
"""Seed the local stand-in of the EC2 instance's flag listener (compose.local-flow-flags.yaml).

The stand-in runs the instance's own `scripts/otel_demo/mcp_guest.py serve-flags` against this
state: the settings `prepare-mcp` installs (from demo/manifest.yaml), a flag file with the three
flags of upstream `src/flagd/demo.flagd.json` (opentelemetry-demo 3.0.0, commit 1755859a) the demo
touches, at their baseline, and the listener's token. The instance's flagd image serves the same
file. Rerunning keeps the token and resets the flags."""

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.otel_demo.mcp_install import manifest_settings  # noqa: E402

STATE = Path(sys.argv[1] if len(sys.argv) > 1 else "/state")
FLAGS = {
    "paymentUnreachable": {"on": True, "off": False},
    "paymentFailure": {
        "100%": 1,
        "90%": 0.95,
        "75%": 0.75,
        "50%": 0.5,
        "25%": 0.25,
        "10%": 0.1,
        "off": 0,
    },
    "loadGeneratorTraffic": {"on": 1, "off": 0},
}


def main():
    (STATE / "flagd").mkdir(parents=True, exist_ok=True)
    settings = manifest_settings()
    (STATE / "settings.json").write_text(json.dumps(settings, sort_keys=True))
    baseline = dict(settings["baseline"])
    fallback = baseline.pop("all_other_flags")
    flags = {
        name: {
            "state": "ENABLED",
            "variants": variants,
            "defaultVariant": baseline.get(name, fallback),
        }
        for name, variants in FLAGS.items()
    }
    # The stand-in (uid 65532) replaced it if it ran: replace it again rather than write into it.
    (STATE / "flagd" / "demo.flagd.json").unlink(missing_ok=True)
    (STATE / "flagd" / "demo.flagd.json").write_text(json.dumps({"flags": flags}, indent=2) + "\n")
    token = STATE / "flag-write.env"
    if not token.exists():
        token.write_text("DEPLOY_EXECUTOR_FLAGS_TOKEN=" + secrets.token_hex(24) + "\n")
    for path in (STATE, STATE / "flagd"):
        path.chmod(0o777)  # a stand-in: its uid 65532 replaces the flag file the API reads
    for path in (STATE / "settings.json", STATE / "flagd" / "demo.flagd.json", token):
        path.chmod(0o644)
    print(
        "stand-in flags at baseline: "
        + ", ".join(f"{n}={f['defaultVariant']}" for n, f in flags.items())
    )


if __name__ == "__main__":
    main()
