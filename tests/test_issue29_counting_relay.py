"""Functional failure scenarios for the isolated Issue 29 HTTP relay.

Written before the instrument. These checks guard against lost request/response
semantics, secret or payload leakage, control endpoints contaminating counts, and
conflating discovery handshake methods with tools/call. They exercise the real
subprocess over HTTP against a local stub, not the relay handler in isolation.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

RELAY = Path(__file__).parents[1] / "scripts" / "issue29_counting_relay.py"


class StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen: list[tuple[str, bytes]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).seen.append((self.headers.get("X-Issue29-Probe", ""), body))
        reply = b'{"stub":"response"}'
        self.send_response(207)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.send_header("X-Upstream-Probe", "preserved")
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_relay(upstream: str) -> tuple[subprocess.Popen[str], int]:
    port = _port()
    env = os.environ.copy()
    env.update(
        ISSUE29_BIND_HOST="127.0.0.1",
        ISSUE29_BIND_PORT=str(port),
        ISSUE29_UPSTREAM_URL=upstream,
    )
    process = subprocess.Popen(
        [sys.executable, str(RELAY)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.communicate()[0]
            raise AssertionError(f"relay exited before ready ({process.returncode}): {output}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/__count", timeout=0.2).status_code == 200:
                return process, port
        except httpx.HTTPError:
            time.sleep(0.05)
    process.terminate()
    output = process.communicate(timeout=2)[0]
    raise AssertionError(f"relay did not become ready: {output}")


def _stop(process: subprocess.Popen[str]) -> str:
    process.terminate()
    try:
        return process.communicate(timeout=3)[0]
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate()[0]


def _snapshot(port: int) -> dict[str, Any]:
    response = httpx.get(f"http://127.0.0.1:{port}/__count", timeout=2)
    assert response.status_code == 200
    return response.json()


def test_forward_preserves_http_contract_and_classifies_mcp_methods() -> None:
    StubHandler.seen = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    process, port = _start_relay(f"http://127.0.0.1:{upstream.server_port}")
    secret = "DO_NOT_LOG_ISSUE29_SECRET"
    try:
        reset = httpx.post(f"http://127.0.0.1:{port}/__count/reset", timeout=2)
        assert reset.status_code == 200
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": secret, "params": {}},
        ]
        for message in messages:
            response = httpx.post(
                f"http://127.0.0.1:{port}/mcp?probe=1",
                content=json.dumps(message),
                headers={
                    "Content-Type": "application/json",
                    "X-Issue29-Probe": "forwarded",
                    "Authorization": f"Bearer {secret}",
                },
                timeout=2,
            )
            assert response.status_code == 207
            assert response.content == b'{"stub":"response"}'
            assert response.headers["X-Upstream-Probe"] == "preserved"
        assert [body for _, body in StubHandler.seen] == [
            json.dumps(message).encode() for message in messages
        ]
        assert all(probe == "forwarded" for probe, _ in StubHandler.seen)
        snapshot = _snapshot(port)
        assert snapshot["total_http_requests"] == 4
        assert snapshot["upstream_attempts"] == 4
        assert snapshot["upstream_failures"] == 0
        assert snapshot["mcp_methods"] == {
            "initialize": 1,
            "notifications/initialized": 1,
            "tools/call": 1,
            "other": 1,
        }
        # GET capture and control POSTs are operational reads, not MCP traffic.
        assert _snapshot(port)["total_http_requests"] == 4
        assert secret not in json.dumps(snapshot)
    finally:
        output = _stop(process)
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=2)
    assert secret not in output


def test_forwarding_error_is_counted_and_returns_safe_502() -> None:
    # A refused upstream is a forwarded attempt, not a successful tool result.
    process, port = _start_relay("http://127.0.0.1:1")
    secret = "DO_NOT_LOG_UPSTREAM_SECRET"
    try:
        response = httpx.post(
            f"http://127.0.0.1:{port}/mcp",
            content='{"jsonrpc":"2.0","id":7,"method":"tools/call"}',
            headers={"Authorization": f"Bearer {secret}"},
            timeout=3,
        )
        assert response.status_code == 502
        assert response.json() == {"error": "upstream_unavailable"}
        assert secret not in response.text
        snapshot = _snapshot(port)
        assert snapshot["total_http_requests"] == 1
        assert snapshot["upstream_attempts"] == 1
        assert snapshot["upstream_failures"] == 1
        assert snapshot["mcp_methods"] == {"tools/call": 1}
    finally:
        output = _stop(process)
    assert secret not in output


def test_count_reset_and_capture_controls_do_not_increment_requests() -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    process, port = _start_relay(f"http://127.0.0.1:{upstream.server_port}")
    try:
        initial = _snapshot(port)
        assert initial["total_http_requests"] == 0
        assert initial["reset_at_utc"]
        assert initial["captured_at_utc"]
        reset = httpx.post(f"http://127.0.0.1:{port}/__count/reset", timeout=2)
        assert reset.status_code == 200
        after_reset = _snapshot(port)
        assert after_reset["total_http_requests"] == 0
        assert after_reset["upstream_attempts"] == 0
        assert after_reset["upstream_failures"] == 0
    finally:
        _stop(process)
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=2)
