"""The demo publishes only the declared host ports, and only on the loopback interface."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
OVERLAY = (ROOT / "compose.demo.yaml").read_text(encoding="utf-8")
MANIFEST = yaml.safe_load((ROOT / "demo/manifest.yaml").read_text(encoding="utf-8"))


def published(monkeypatch: pytest.MonkeyPatch, listing: str) -> list[str]:
    """Run the port check of the operator script against a container listing."""

    spec = importlib.util.spec_from_file_location("demo_env", ROOT / "scripts" / "demo_env.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: listing)
    problems: list[str] = module.undeclared_ports(MANIFEST)
    return problems


def test_the_declared_ports_are_published_on_loopback_only() -> None:
    assert '- "127.0.0.1:${ENVOY_PORT}:${ENVOY_PORT}"' in OVERLAY
    assert '- "127.0.0.1:${PROMETHEUS_PORT}:${PROMETHEUS_PORT}"' in OVERLAY
    assert [(entry["port"], entry["bind"]) for entry in MANIFEST["host_ports"]] == [
        (8090, "127.0.0.1"),
        (9090, "127.0.0.1"),
    ]


def test_the_envoy_admin_interface_is_not_published() -> None:
    assert "10000" not in OVERLAY
    assert 10000 not in {entry["port"] for entry in MANIFEST["host_ports"]}


def test_every_other_upstream_publication_stays_reset() -> None:
    for service in ("grafana", "opensearch", "flagd-ui", "jaeger", "frontend"):
        assert f"{service}: {{ports: !reset []}}" in OVERLAY


def test_verify_accepts_the_declared_publications(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = "\n".join(
        [
            "otel-demo-frontend-proxy-1\t127.0.0.1:8090->8090/tcp",
            "otel-demo-prometheus-1\t127.0.0.1:9090->9090/tcp",
            "grafana-mcp\t",
        ]
    )

    assert published(monkeypatch, listing) == []


def test_verify_rejects_a_declared_port_on_another_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = "otel-demo-frontend-proxy-1\t0.0.0.0:8090->8090/tcp, [::]:8090->8090/tcp"

    assert published(monkeypatch, listing) == [
        "otel-demo-frontend-proxy-1: publishes host port 8090 on 0.0.0.0, not on 127.0.0.1",
        "otel-demo-frontend-proxy-1: publishes host port 8090 on [::], not on 127.0.0.1",
    ]


def test_verify_rejects_the_envoy_admin_port(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = "otel-demo-frontend-proxy-1\t127.0.0.1:10000->10000/tcp"

    assert published(monkeypatch, listing) == [
        "otel-demo-frontend-proxy-1: publishes undeclared host port 10000"
    ]
