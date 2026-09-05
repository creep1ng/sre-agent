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
    assert adapted.alert["alert_id"] == "alt-paymentservice-b5515c24f983"
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


def _with(**overrides: object) -> dict:
    signal = _signal("otel-payment-failure-signal.json")
    signal.update(overrides)
    return signal


def test_nested_sensitive_values_under_allowed_keys_are_dropped() -> None:
    """P1: an allow-listed key must not smuggle nested secrets into correlation."""
    signal = _signal("otel-payment-failure-signal.json")
    signal["resource_attributes"]["service.namespace"] = {
        "api_key": "SYNTHETIC_SECRET",
        "unexpected": "retained",
    }
    adapted = adapt_otel_signal(signal)
    blob = json.dumps([adapted.alert, adapted.correlation])
    assert "SYNTHETIC_SECRET" not in blob
    assert "retained" not in blob
    assert "service.namespace" not in adapted.correlation["resource"]
    assert "resource_attributes.service.namespace" in adapted.dropped


@pytest.mark.parametrize("bad", [{}, [], 5, "critical"])
def test_mistyped_severity_hint_is_rejected_not_raised(bad: object) -> None:
    """P2: unhashable or invalid severity values must yield SignalRejected."""
    with pytest.raises(SignalRejected) as error:
        adapt_otel_signal(_with(severity_hint=bad))
    assert error.value.code == "unsupported_severity"


def test_valid_severity_hint_is_accepted() -> None:
    assert adapt_otel_signal(_with(severity_hint="sev1")).alert["severity"] == "sev1"


def test_same_trace_prefix_yields_distinct_alert_ids() -> None:
    """P3: identity uses the full identifiers, never the trace_id prefix."""
    first = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    second_raw = _signal("otel-payment-failure-signal.json")
    second_raw["trace_id"] = first.correlation["trace_id"][:8] + "0" * 24
    second = adapt_otel_signal(second_raw)
    assert first.alert["alert_id"] != second.alert["alert_id"]


def test_resending_the_same_signal_is_idempotent() -> None:
    """P3: retries of the exact same signal keep a valid, stable alert_id."""
    validator = build_validator(load_yaml(STATE_SCHEMA_PATH))
    first = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    second = adapt_otel_signal(_signal("otel-payment-failure-signal.json"))
    assert first.alert["alert_id"] == second.alert["alert_id"]
    assert validator.is_valid(_base_state(first.alert))


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-08-24T14:04:30Z", "2026-08-24T14:04:30Z"),
        ("2026-08-24T14:04:30+02:00", "2026-08-24T12:04:30Z"),
    ],
)
def test_full_rfc3339_timestamps_are_normalized(timestamp: str, expected: str) -> None:
    """P4: complete zoned timestamps normalize to UTC without inventing data."""
    signal = _signal("otel-payment-failure-signal.json")
    signal["span"]["timestamp"] = timestamp
    assert adapt_otel_signal(signal).alert["observed_at"] == expected


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-08-24",
        "2026-08-24T14:04:30",
        "definitely-not-a-timestamp",
        "0001-01-01T00:30:00+01:00",
        12345,
    ],
)
def test_incomplete_or_unusable_timestamps_are_rejected(timestamp: object) -> None:
    """P4: date-only, naive, malformed or overflowing timestamps are rejected."""
    signal = _signal("otel-payment-failure-signal.json")
    signal["span"]["timestamp"] = timestamp
    with pytest.raises(SignalRejected) as error:
        adapt_otel_signal(signal)
    assert error.value.code == "invalid_format"
