#!/usr/bin/env python3
"""Manage one shared, short-lived OpenTelemetry Demo EC2 session."""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.otel_demo.aws import AwsCli
from scripts.otel_demo.cli import _arguments, _duration, main
from scripts.otel_demo.common import (
    AwsApi,
    AwsApiError,
    DemoConfig,
    DemoError,
    SchedulerNotProvisioned,
    _allowed_ports,
    _host_lock,
    _normalize_instance,
    _parse_datetime,
    _schedule_name,
    _tags,
    calculate_extended_deadline,
)
from scripts.otel_demo.controller import DemoController
from scripts.otel_demo.guest import _digest_lock, _manifest_pin, build_user_data

__all__ = [
    "AwsApi",
    "AwsApiError",
    "AwsCli",
    "DemoConfig",
    "DemoController",
    "DemoError",
    "SchedulerNotProvisioned",
    "_allowed_ports",
    "_arguments",
    "_digest_lock",
    "_duration",
    "_host_lock",
    "_manifest_pin",
    "_normalize_instance",
    "_parse_datetime",
    "_schedule_name",
    "_tags",
    "build_user_data",
    "calculate_extended_deadline",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
