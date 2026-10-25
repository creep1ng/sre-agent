"""The demo's second enrolled service (#721): a checkout of our own, beside the OTel store.

It serves POST /checkout, generates its own traffic and pushes one cumulative OTLP counter,
checkout.requests by HTTP status code, to the demo's collector every five seconds. The release
is baked into the image, never set on the container: 1.5.0 carries the regression the demo
rolls back, 3 of every 10 orders answer 500. Standard library only, like the executor's probe.
"""

import json
import os
import signal
import socket
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get("CHECKOUT_VERSION", "")
ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
BROKEN = VERSION == "1.5.0"
STARTED = str(time.time_ns())
counts: dict[int, int] = {}
lock = threading.Lock()


def attribute(key: str, value: str | int) -> dict[str, object]:
    return {"key": key, "value": {"intValue" if isinstance(value, int) else "stringValue": value}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        about = {"service": "checkout", "version": VERSION}
        self.reply(200, {"status": "ok"} if self.path == "/health" else about)

    def do_POST(self) -> None:
        if self.path != "/checkout":
            return self.reply(404, {"error": "not found"})
        with lock:
            status = 500 if BROKEN and sum(counts.values()) % 10 < 3 else 200
            counts[status] = counts.get(status, 0) + 1
        self.reply(status, {"order": "accepted"} if status == 200 else {"error": "internal error"})

    def reply(self, status: int, document: dict[str, str]) -> None:
        body = json.dumps(document).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


def traffic() -> None:
    """Five orders a second, so the counter moves whether or not anyone shops."""
    while True:
        try:
            urllib.request.urlopen("http://127.0.0.1:8080/checkout", b"{}", timeout=2).close()
        except OSError:  # a 500 raises HTTPError, an OSError
            pass
        time.sleep(0.2)


def export() -> None:
    resource = {
        "attributes": [
            attribute("service.name", "checkout"),
            attribute("service.namespace", "sre-agent"),
            attribute("service.version", VERSION),
            attribute("service.instance.id", socket.gethostname()),
        ]
    }
    while True:
        time.sleep(5)
        with lock:
            snapshot = sorted(counts.items())
        now = str(time.time_ns())
        points = [
            {
                "attributes": [attribute("http.response.status_code", code)],
                "startTimeUnixNano": STARTED,
                "timeUnixNano": now,
                "asInt": str(total),
            }
            for code, total in snapshot
        ]
        counter = {
            "name": "checkout.requests",
            "unit": "{request}",
            "description": "Checkout orders served, by HTTP status code.",
            "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": points},
        }
        scope = {"scope": {"name": "checkout"}, "metrics": [counter]}
        body = json.dumps({"resourceMetrics": [{"resource": resource, "scopeMetrics": [scope]}]})
        push = urllib.request.Request(
            ENDPOINT + "/v1/metrics", body.encode(), {"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(push, timeout=3).close()
        except OSError as error:
            print(f"checkout: metrics push failed: {error}", flush=True)


if not VERSION:
    raise SystemExit("checkout: CHECKOUT_VERSION is baked in at build time")
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
for worker in (traffic, export):
    threading.Thread(target=worker, daemon=True).start()
print(f"checkout {VERSION} on :8080, pushing metrics to {ENDPOINT}", flush=True)
server.serve_forever()
