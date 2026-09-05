"""Acceptance tests for the OTel demo signal adapter (HT-INC-08, issue #149).

Each test maps to one acceptance criterion: one signal → one canonical alert,
correlation preserved outside the closed origin, unknown/sensitive dropped,
incomplete rejected deterministically, result feeds triage (#16/#23).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_incident_contracts import (  # noqa: E402
    STATE_SCHEMA_PATH,
    build_validator,
    load_yaml,
)

from sre_agent.incident.signals import SignalRejected, adapt_otel_signal  # noqa: E402

SIGNALS_ROOT = REPOSITORY_ROOT / "agent" / "fixtures" / "signals"


def _signal(name: str) -> dict:
    return json.loads((SIGNALS_ROOT / name).read_text(encoding="utf-8"))


def _base_state(alert: dict) -> dict:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "detected",
        "alert": alert,
        "updated_at": alert["observed_at"],
    }


def test_valid_demo_signal_yields_exactly_one_canonical_alert() -> None:
    adapted = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    validator = build_validator(load_yaml(STATE_SCHEMA_PATH))
    assert validator.is_valid(_base_state(adapted.alert))
    assert adapted.alert["alert_id"] == "alt-paymentservice-a1b2c3d4"
    assert adapted.alert["status"] == "new"
    assert adapted.alert["source"] == "opentelemetry-demo"


def test_correlation_preserves_trace_span_and_resource_outside_origin() -> None:
    adapted = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    assert adapted.correlation["trace_id"] == "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert adapted.correlation["span_id"] == "1234abcd5678ef90"
    assert adapted.correlation["resource"]["service.name"] == "paymentservice"
    # Closed origin (1.0.0) must not smuggle correlation identifiers.
    assert set(adapted.alert["origin"]) == {"signal", "condition", "detector", "observed_at"}
    assert "trace_id" not in adapted.alert["origin"]


def test_unknown_and_sensitive_fields_never_enter_the_domain() -> None:
    adapted = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    blob = json.dumps([adapted.alert, adapted.correlation])
    assert "must be dropped" not in blob
    assert "must never enter the domain" not in blob
    assert any("extra_unknown_top_level" in item for item in adapted.dropped)
    assert any("api_key" in item for item in adapted.dropped)


def test_adapted_state_feeds_triage_without_inventing_a_session() -> None:
    adapted = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    on_disk = load_yaml(
        REPOSITORY_ROOT
        / "agent"
        / "fixtures"
        / "incidents"
        / "otel-payment-failure"
        / "adapted-signal-state.yaml"
    )
    assert on_disk["state"] == "detected"
    assert on_disk["incident_id"] is None
    assert on_disk["alert"] == adapted.alert
    validator = build_validator(load_yaml(STATE_SCHEMA_PATH))
    assert validator.is_valid(on_disk)


@pytest.mark.parametrize(
    ("fixture", "code"),
    [
        ("negative/missing-service.json", "missing_field"),
        ("negative/invalid-timestamp.json", "invalid_format"),
        ("negative/unsupported-severity.json", "unsupported_severity"),
    ],
)
def test_incomplete_signals_rejected_deterministically(fixture: str, code: str) -> None:
    with pytest.raises(SignalRejected) as error:
        adapt_otel_signal(_signal(fixture))
    assert error.value.code == code
    assert str(error.value).startswith(code)
