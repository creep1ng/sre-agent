"""Reproducible demo for HT-INC-08 (issue #149): one OTel signal → one alert.

Usage:
    python scripts/adapt_otel_signal.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from sre_agent.incident.signals import adapt_otel_signal  # noqa: E402

SIGNAL_PATH = (
    REPOSITORY_ROOT / "agent" / "fixtures" / "signals" / "otel-payment-failure-signal.json"
)


def main() -> int:
    raw = json.loads(SIGNAL_PATH.read_text(encoding="utf-8"))
    adapted = adapt_otel_signal(raw)
    print(
        json.dumps(
            {
                "alert": adapted.alert,
                "correlation": adapted.correlation,
                "dropped": adapted.dropped,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"OK: 1 signal -> 1 alert ({adapted.alert['alert_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
