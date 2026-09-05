"""OTel demo signal → canonical alert adapter (HT-INC-08, issue #149).

Boundary: incident-resolution-plane ingress. Pure function, no I/O, no DB,
no state machine (HT-INC-02 owns the runtime). Compatible with
incident-state 1.0.0: `alert.origin` only carries the closed allow-list
(signal/condition/detector/observed_at); trace/span/resource travel in a
separate versioned correlation envelope.

Follows the Rootly pattern (normalize at the source layer, built-ins first)
and incident.io (intake ≠ declaration: incident_id is never invented here).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

MAPPING_VERSION = "1.0.0"
CORRELATION_VERSION = "otel-correlation 1.0.0"
DETECTOR = "opentelemetry-demo"
SOURCE = "opentelemetry-demo"

_SEVERITIES = frozenset({"sev1", "sev2", "sev3", "sev4"})
_TRACE_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_RE = re.compile(r"^[0-9a-f]{16}$")
_ALERT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_SENSITIVE_RE = re.compile(r"password|secret|token|authorization|cookie|api_key|set-cookie")
_ALLOWED_RESOURCE_KEYS = ("service.name", "service.namespace", "deployment.environment")


class SignalRejected(Exception):
    """Typed rejection for invalid or incomplete OTel signals."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class AdaptedSignal:
    """One valid signal produces exactly one canonical alert fragment."""

    alert: dict
    correlation: dict
    dropped: list = field(default_factory=list)


def _require(mapping: dict, name: str) -> object:
    value = mapping.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise SignalRejected("missing_field", f"required field '{name}' is absent or empty")
    return value


def _parse_time(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SignalRejected("missing_field", "span timestamp is absent or empty")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise SignalRejected("invalid_format", f"timestamp '{value}' is not RFC 3339") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _slug(service: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "-", service.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-") or "unknown"
    return slug[:48]


def _scan_sensitive(obj: object, path: str, dropped: list) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and _SENSITIVE_RE.search(key.lower()):
                dropped.append(child)
                continue
            _scan_sensitive(value, child, dropped)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _scan_sensitive(value, f"{path}[{index}]", dropped)


def adapt_otel_signal(raw: dict) -> AdaptedSignal:
    """Adapt one raw OTel demo signal to one canonical alert fragment."""
    if not isinstance(raw, dict):
        raise SignalRejected("invalid_format", "signal must be a JSON object")

    dropped: list[str] = []
    _scan_sensitive(raw, "", dropped)

    trace_id = _require(raw, "trace_id")
    span_id = _require(raw, "span_id")
    if not isinstance(trace_id, str) or not _TRACE_RE.match(trace_id):
        raise SignalRejected("invalid_format", "trace_id must be 32 lowercase hex chars")
    if not isinstance(span_id, str) or not _SPAN_RE.match(span_id):
        raise SignalRejected("invalid_format", "span_id must be 16 lowercase hex chars")

    resource = raw.get("resource_attributes") or {}
    if not isinstance(resource, dict):
        raise SignalRejected("invalid_format", "resource_attributes must be an object")
    service = resource.get("service.name")
    if not isinstance(service, str) or not service.strip():
        raise SignalRejected("missing_field", "resource.attributes[service.name] is required")
    if len(service.strip()) > 200:
        raise SignalRejected("invalid_format", "service name exceeds 200 chars")

    span = raw.get("span")
    if not isinstance(span, dict):
        raise SignalRejected("missing_field", "span object is required")
    name = span.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SignalRejected("missing_field", "span.name is required")
    observed_at = _parse_time(span.get("timestamp"))

    severity = raw.get("severity_hint")
    if severity not in _SEVERITIES:
        if severity is None or (isinstance(severity, str) and not severity.strip()):
            raise SignalRejected("missing_field", "severity_hint is required (sev1..sev4)")
        raise SignalRejected("unsupported_severity", f"severity '{severity}' is not sev1..sev4")

    status = span.get("status") or {}
    message = status.get("message") if isinstance(status, dict) else None
    if isinstance(message, str) and message.strip():
        condition = message.strip()
    else:
        condition = "otel span error"

    for key in resource:
        if key not in _ALLOWED_RESOURCE_KEYS and f"resource_attributes.{key}" not in dropped:
            dropped.append(f"resource_attributes.{key}")
    for key in span:
        if (
            key not in {"name", "status", "timestamp", "attributes"}
            and f"span.{key}" not in dropped
        ):
            dropped.append(f"span.{key}")
    for top in raw:
        if (
            top
            not in {
                "trace_id",
                "span_id",
                "resource_attributes",
                "span",
                "severity_hint",
            }
            and top not in dropped
        ):
            dropped.append(top)

    alert_id = f"alt-{_slug(service)}-{trace_id[:8]}"
    if not _ALERT_ID_RE.match(alert_id):
        raise SignalRejected("invalid_format", f"derived alert_id '{alert_id}' violates contract")

    summary = f"{name.strip()} on {service.strip()} (trace {trace_id[:8]})"[:2000]
    alert = {
        "alert_id": alert_id,
        "service": service.strip(),
        "severity": severity,
        "status": "new",
        "observed_at": observed_at,
        "summary": summary,
        "source": SOURCE,
        "origin": {
            "signal": name.strip()[:200],
            "condition": condition[:500],
            "detector": DETECTOR,
            "observed_at": observed_at,
        },
    }
    correlation = {
        "correlation_version": CORRELATION_VERSION,
        "mapping_version": MAPPING_VERSION,
        "trace_id": trace_id,
        "span_id": span_id,
        "resource": {key: resource[key] for key in _ALLOWED_RESOURCE_KEYS if key in resource},
    }
    return AdaptedSignal(alert=alert, correlation=correlation, dropped=sorted(set(dropped)))
