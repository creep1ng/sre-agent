#!/usr/bin/env python3
"""OpenRouter and Grafana MCP stand-in for the #719 E2E (compose.provider-retry-e2e.yaml).

`/api/v1/responses` answers the investigator's next action; `POST /__plan` queues the next
answers (`503`, or `"slow"` to outlast OPENROUTER_TIMEOUT_SECONDS). `/mcp` initializes and holds
each tools/call for MCP_DELAY_SECONDS. `GET /__log` lists what was answered.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

MODEL, PROVIDER = os.environ["STANDIN_MODEL"], os.environ["STANDIN_PROVIDER"]
MCP_DELAY = float(os.environ.get("MCP_DELAY_SECONDS", "5"))
LOG: list[dict] = []
PLAN: list[object] = []
LOCK = threading.Lock()


def next_action(prompt: str) -> dict:
    if "State: " not in prompt:  # a direct call, not the investigator
        return {"reply": "Stand-in reply."}
    state = json.loads(prompt.split("State: ", 1)[1].split("\n", 1)[0])
    incident = state["incident"]
    if not incident["evidence"]:
        arguments = {"datasource_uid": "webstore-metrics", "expr": "up"}
        arguments |= {"query_type": "instant", "end_time": "now"}
        return {"action": "use_tool", "tool": "query_prometheus", "arguments": arguments}
    if incident["hypotheses"]:
        return {
            "action": "propose_mitigation",
            "description": "Roll the service back to its previous release.",
            "steps": ["The operator rolls the service back to its previous release."],
            "risk": "low",
            "verification_check": "Error rate below 1% for ten minutes.",
            "based_on_hypothesis": incident["hypotheses"][0]["hypothesis_id"],
        }
    return {
        "action": "propose_hypothesis",
        "statement": "The last release raised the error rate.",
        "confidence": "medium",
        "supporting_evidence": [incident["evidence"][0]["evidence_id"]],
    }


def completed(prompt: str) -> dict:
    text = json.dumps(next_action(prompt))
    attempt = {"provider": PROVIDER, "model": MODEL}
    message = {"type": "message", "role": "assistant", "status": "completed"}
    message["content"] = [{"type": "output_text", "text": text}]
    metadata = {"requested": MODEL, "strategy": "direct", "attempt": 1}
    metadata["endpoints"] = {"total": 1, "available": [attempt | {"selected": True}]}
    metadata["attempts"] = [attempt | {"status": 200}]
    usage = {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20, "cost": 0.000001}
    return {
        "id": f"gen-{uuid4().hex}",
        "model": MODEL,
        "status": "completed",
        "created_at": int(time.time()),
        "output": [message],
        "usage": usage,
        "openrouter_metadata": metadata,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def _send(self, status: int, payload: object, headers: dict | None = None) -> None:
        if self.path not in {"/health", "/__log", "/__plan"}:
            with LOCK:
                LOG.append({"method": self.command, "path": self.path, "status": status})
        encoded = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        with LOCK:
            self._send(200, list(LOG))

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if self.path == "/__plan":
            with LOCK:
                PLAN[:] = body["responses"]
            return self._send(200, {"planned": len(PLAN)})
        if self.path == "/mcp":
            return self._mcp(body)
        if self.path != "/api/v1/responses" or body.get("model") != MODEL:
            return self._send(404, {"error": {"message": "Not Found", "code": 404}})
        with LOCK:
            planned = PLAN.pop(0) if PLAN else 200
        if planned == 503:
            return self._send(503, {"error": {"message": "No endpoints available", "code": 503}})
        if planned == "slow":
            time.sleep(float(os.environ.get("SLOW_SECONDS", "5")))
        self._send(200, completed(body["input"]))

    def _mcp(self, body: dict) -> None:
        method = body.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {}, "serverInfo": {}}
            reply = {"jsonrpc": "2.0", "id": body["id"], "result": result}
            return self._send(200, reply, {"Mcp-Session-Id": "standin"})
        if method == "tools/call":
            time.sleep(MCP_DELAY)
            result = {"content": [{"type": "text", "text": "{}"}]}
            return self._send(200, {"jsonrpc": "2.0", "id": body["id"], "result": result})
        self._send(202, None)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
