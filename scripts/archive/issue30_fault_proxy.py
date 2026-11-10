"""In-network, metadata-free failure controls for the Issue 30 real MCP stack."""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx

UPSTREAM = os.getenv("ISSUE30_UPSTREAM_URL", "http://mcp-upstream:8000").rstrip("/")
mode = "pass"
lock = threading.Lock()
forwarded = {}
HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        global mode
        path = urlsplit(self.path).path
        if path == "/__stats/reset":
            with lock:
                forwarded.clear()
            self.reply(200, {"forwarded_methods": {}})
            return
        if path == "/__mode":
            try:
                value = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            except (ValueError, json.JSONDecodeError):
                self.reply(400, {"error": "invalid_mode"})
                return
            if value.get("mode") not in {"pass", "timeout", "unavailable", "invalid"}:
                self.reply(400, {"error": "invalid_mode"})
                return
            with lock:
                mode = value["mode"]
            self.reply(200, {"mode": mode})
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            rpc = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            rpc = {}
        with lock:
            selected = mode
        if isinstance(rpc, dict) and rpc.get("method") == "tools/call":
            if selected == "timeout":
                time.sleep(35)
                self.reply(503, {"diagnostic": "ISSUE30_TIMEOUT_SENTINEL"})
                return
            if selected == "unavailable":
                # Sentinel must be suppressed by the gateway's public error mapper.
                self.reply(503, {"diagnostic": "ISSUE30_UPSTREAM_SENTINEL"})
                return
            if selected == "invalid":
                self.reply(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": "sentinel",
                        "result": {
                            "content": [{"type": "text", "text": "ISSUE30_INVALID_SENTINEL"}]
                        },
                    },
                )
                return
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in HOP | {"host", "content-length"}
        }
        try:
            if isinstance(rpc, dict) and isinstance(rpc.get("method"), str):
                method = rpc["method"]
                method = (
                    method
                    if method in {"initialize", "notifications/initialized", "tools/call"}
                    else "other"
                )
                with lock:
                    forwarded[method] = forwarded.get(method, 0) + 1
            r = httpx.post(
                UPSTREAM + self.path, content=body, headers=headers, timeout=120, trust_env=False
            )
            self.send_response(r.status_code)
            for key, value in r.headers.items():
                if key.lower() not in HOP | {"content-length", "content-encoding"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(r.content)))
            self.end_headers()
            self.wfile.write(r.content)
        except httpx.HTTPError:
            self.reply(502, {"error": "controlled_proxy_unavailable"})

    def do_GET(self):
        if urlsplit(self.path).path == "/__stats":
            with lock:
                snapshot = dict(forwarded)
            self.reply(200, {"forwarded_methods": snapshot})
        else:
            self.reply(404, {"error": "not_found"})


ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
