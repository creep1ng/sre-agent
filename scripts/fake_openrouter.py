#!/usr/bin/env python3
"""OpenRouter stand-in for the #758 E2E, answering as the live service did on 2026-10-30.

`GET /api/v1/models/{author}/{slug}/endpoints` returns the recorded z-ai/glm-5.3-flash entry
at Relace (`max_prompt_tokens: null`, no `pricing.request`) plus a synthetic, costlier second
endpoint of the same provider (tag `<provider>/us`, 262,144-token window, no completion cap),
as OpenRouter lists for Fireworks or Wafer. An alias or an escaped slash (`%2F`) gets the live
404 body. Each route requires its own key (management for the catalog, inference for
responses) and answers 401 otherwise.

`POST /api/v1/responses` acts as a strict provider: it answers 400 unless routing pins the
configured provider without fallbacks, and unless `max_output_tokens` fits every endpoint of
that provider, counting the prompt at one token per UTF-8 byte against the context window.
Otherwise it returns a completed response with exact usage; given an investigator state it
proposes a hypothesis citing the incident's evidence, then a mitigation based on it.
`GET /__log` lists each request's path and status, and for responses the prompt's byte count
and the `max_output_tokens` it received.
"""

import json
import os
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

MODEL, PROVIDER = os.environ["FAKE_MODEL"], os.environ["FAKE_PROVIDER"]
KEYS = {"catalog": os.environ["FAKE_MANAGEMENT_KEY"], "responses": os.environ["FAKE_INFERENCE_KEY"]}
PROMPT, COMPLETION = Decimal("0.0000000497"), Decimal("0.0000000701")
ENDPOINTS = [
    {
        "name": f"{PROVIDER} | {MODEL}",
        "model_id": MODEL,
        "provider_name": PROVIDER,
        "tag": PROVIDER,
        "context_length": 1048576,
        "max_prompt_tokens": None,
        "max_completion_tokens": 131072,
        "pricing": {"prompt": str(PROMPT), "completion": str(COMPLETION), "discount": 0},
    },
    {
        "name": f"{PROVIDER} | {MODEL}",
        "model_id": MODEL,
        "provider_name": PROVIDER,
        "tag": f"{PROVIDER}/us",
        "context_length": 262144,
        "max_prompt_tokens": None,
        "max_completion_tokens": None,
        "pricing": {"prompt": "0.0000001", "completion": "0.0000002", "discount": 0},
    },
]
LOG: list[dict] = []
LOCK = threading.Lock()


def next_action(prompt: str) -> str:
    if "State: " not in prompt:
        return "Fake OpenRouter reply."
    incident = json.loads(prompt.split("State: ", 1)[1].split("\n", 1)[0])["incident"]
    if incident["hypotheses"]:
        return json.dumps(
            {
                "action": "propose_mitigation",
                "description": "Turn the paymentFailure feature flag off.",
                "steps": ["The operator sets paymentFailure to off in the flag service."],
                "risk": "low",
                "verification_check": "paymentservice error rate below 1% for ten minutes.",
                "based_on_hypothesis": incident["hypotheses"][0]["hypothesis_id"],
            }
        )
    return json.dumps(
        {
            "action": "propose_hypothesis",
            "statement": "The paymentFailure feature flag makes PaymentService/Charge fail.",
            "confidence": "medium",
            "supporting_evidence": [incident["evidence"][0]["evidence_id"]],
        }
    )


def completed(prompt: str) -> dict:
    text = next_action(prompt)
    tokens_in, tokens_out = len(prompt) // 4 + 1, len(text) // 4 + 1
    attempt = {"provider": PROVIDER, "model": MODEL}
    return {
        "id": f"gen-{uuid4().hex}",
        "model": MODEL,
        "status": "completed",
        "created_at": int(time.time()),
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "cost": float(PROMPT * tokens_in + COMPLETION * tokens_out),
        },
        "openrouter_metadata": {
            "requested": MODEL,
            "strategy": "direct",
            "attempt": 1,
            "endpoints": {"total": 1, "available": [attempt | {"selected": True}]},
            "attempts": [attempt | {"status": 200}],
        },
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def _send(self, status: int, payload: object, **facts: object) -> None:
        if self.path not in {"/health", "/__log"}:
            with LOCK:
                LOG.append({"method": self.command, "path": self.path, "status": status} | facts)
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path in {"/health", "/__log"}:
            with LOCK:
                return self._send(200, list(LOG))
        if self.path == f"/api/v1/models/{MODEL}/endpoints":
            if not self._authorized("catalog"):
                return self._send(401, {"error": {"message": "No auth credentials", "code": 401}})
            return self._send(200, {"data": {"id": MODEL, "endpoints": ENDPOINTS}})
        self._send(404, {"error": {"message": "Not Found", "code": 404}})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if self.path != "/api/v1/responses" or body.get("model") != MODEL:
            return self._send(404, {"error": {"message": "Not Found", "code": 404}})
        if not self._authorized("responses"):
            return self._send(401, {"error": {"message": "No auth credentials", "code": 401}})
        prompt_bytes = len(body["input"].encode("utf-8"))
        cap = body.get("max_output_tokens")
        facts = {"prompt_bytes": prompt_bytes, "max_output_tokens": cap}
        routing = body.get("provider") or {}
        if routing.get("order") != [PROVIDER] or routing.get("allow_fallbacks") is not False:
            return self._send(
                400, {"error": {"message": "Unexpected routing", "code": 400}}, **facts
            )
        for endpoint in ENDPOINTS:
            window = endpoint["context_length"]
            completion = endpoint["max_completion_tokens"] or window
            if cap is not None and (cap > completion or prompt_bytes + cap > window):
                message = "max_output_tokens exceeds the endpoint's limits"
                return self._send(400, {"error": {"message": message, "code": 400}}, **facts)
        self._send(200, completed(body["input"]), **facts)

    def _authorized(self, route: str) -> bool:
        return self.headers.get("Authorization") == f"Bearer {KEYS[route]}"


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
