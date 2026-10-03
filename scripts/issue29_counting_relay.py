#!/usr/bin/env python3
"""Ephemeral, metadata-only HTTP counter for the Issue 29 MCP boundary demo."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Counts:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.epoch = 0
        self.reset_at = utc_now()
        self.requests = 0
        self.attempts = 0
        self.failures = 0
        self.methods: dict[str, int] = {}

    def reset(self) -> None:
        with self.lock:
            self.epoch += 1
            self.reset_at = utc_now()
            self.requests = self.attempts = self.failures = 0
            self.methods.clear()

    def record_request(self, body: bytes) -> None:
        methods: list[str] = []
        try:
            value = json.loads(body)
            messages = value if isinstance(value, list) else [value]
            methods = [
                item["method"]
                if item["method"]
                in {"initialize", "notifications/initialized", "tools/call"}
                else "other"
                for item in messages
                if isinstance(item, dict) and isinstance(item.get("method"), str)
            ]
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        with self.lock:
            self.requests += 1
            self.attempts += 1
            for method in methods:
                self.methods[method] = self.methods.get(method, 0) + 1

    def failure(self) -> None:
        with self.lock:
            self.failures += 1

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "reset_epoch": self.epoch,
                "reset_at_utc": self.reset_at,
                "captured_at_utc": utc_now(),
                "total_http_requests": self.requests,
                "upstream_attempts": self.attempts,
                "upstream_failures": self.failures,
                "mcp_methods": dict(sorted(self.methods.items())),
            }


COUNTS = Counts()
UPSTREAM = os.environ.get("ISSUE29_UPSTREAM_URL", "http://mcp-upstream:8000").rstrip(
    "/"
)
TIMEOUT = float(os.environ.get("ISSUE29_TIMEOUT_SECONDS", "120"))
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Default http.server access logs include paths and potentially sensitive query data.
        return

    def _respond_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self) -> None:
        path = urlsplit(self.path).path
        if path == "/__count" and self.command == "GET":
            self._respond_json(200, COUNTS.snapshot())
            return
        if path == "/__count/reset" and self.command == "POST":
            COUNTS.reset()
            self._respond_json(200, COUNTS.snapshot())
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        COUNTS.record_request(body)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP | {"host", "content-length"}
        }
        target = f"{UPSTREAM}{self.path}"
        try:
            response = httpx.request(
                self.command,
                target,
                content=body,
                headers=headers,
                timeout=TIMEOUT,
                trust_env=False,
            )
        except Exception:
            COUNTS.failure()
            self._respond_json(502, {"error": "upstream_unavailable"})
            return

        self.send_response(response.status_code)
        for key, value in response.headers.items():
            if key.lower() not in HOP_BY_HOP | {"content-length"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response.content)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = _handle


def main() -> None:
    host = os.environ.get("ISSUE29_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("ISSUE29_BIND_PORT", "8000"))
    ThreadingHTTPServer((host, port), RelayHandler).serve_forever()


if __name__ == "__main__":
    main()
