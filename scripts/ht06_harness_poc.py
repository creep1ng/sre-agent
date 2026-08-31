"""HT-06 proof of concept (issue #12): can a harness consume the gateway?

The spike asks one question:

    Which harness lets an agentic client consume the gateway using only a base URL
    and a gateway credential, and leaves a reasonable path towards tools/MCP and
    Skills without us building a generalist harness?

This script answers the decisive half of that question empirically. It starts a mock
gateway that validates every request against the *real* frozen contract shipped in
`schemas/releases/<latest>`, then fires four probes that correspond to what a candidate
harness would actually put on the wire.

Run it with no arguments to exercise the mock:

    python scripts/ht06_harness_poc.py

Point it at a live gateway once HT-05 lands:

    python scripts/ht06_harness_poc.py --base-url http://127.0.0.1:8000 --api-key sre_...

Probe 1 is what a minimal client sends and it must succeed. Probes 2 and 3 are what
every mainstream agent framework sends as soon as tool calling is enabled, and the
frozen contract rejects both. Probe 4 shows a governed denial. The exit code is 0
when observed behaviour matches the contract, whatever that behaviour is: the script
reports evidence, it does not assert that the contract should be different.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASES_ROOT = REPOSITORY_ROOT / "schemas" / "releases"


def latest_release() -> str:
    """Resolve the newest contract release so the probe never tests a stale version."""
    releases = [path.name for path in RELEASES_ROOT.iterdir() if path.is_dir()]
    return max(releases, key=lambda name: tuple(int(part) for part in name.split(".")))


CONTRACT_RELEASE = latest_release()
REQUEST_SCHEMA_PATH = (
    RELEASES_ROOT / CONTRACT_RELEASE / "json-schema" / "http" / "responses-request.schema.json"
)

AUTHORIZED_KEY = "sre_poc_0000000000000000000000000000"
AUTHORIZED_ALIAS = "triage-agent"
DENIED_ALIAS = "restricted-agent"


@dataclass(frozen=True)
class Probe:
    """One request a candidate harness would realistically put on the wire."""

    name: str
    payload: dict[str, Any]
    api_key: str
    expected_status: int
    why_it_matters: str


@dataclass
class ProbeResult:
    probe: Probe
    observed_status: int
    detail: str

    @property
    def matches_contract(self) -> bool:
        return self.observed_status == self.probe.expected_status


def load_request_validator() -> Draft202012Validator:
    """Validate against the contract that is actually frozen in the repository."""
    schema = json.loads(REQUEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


class MockGatewayHandler(BaseHTTPRequestHandler):
    """Mock faithful to the HT-01 ordering: validate, authenticate, authorize, route."""

    validator: Draft202012Validator

    def log_message(self, *args: Any) -> None:  # noqa: D102 - silence stdlib logging
        return

    def _reply(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if self.path != "/v1/responses":
            self._reply(404, {"error": {"code": "not_found"}})
            return

        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._reply(422, {"error": {"code": "invalid_request"}})
            return

        # 1. Contract validation precedes authentication (ADR-001 ordering).
        problems = sorted(self.validator.iter_errors(payload), key=lambda item: item.path)
        if problems:
            first = problems[0]
            location = "/".join(str(part) for part in first.path) or "<root>"
            self._reply(
                422,
                {"error": {"code": "invalid_request", "at": location, "detail": first.message}},
            )
            return

        # 2. Authentication precedes authorization.
        authorization = self.headers.get("Authorization", "")
        if authorization != f"Bearer {AUTHORIZED_KEY}":
            self._reply(401, {"error": {"code": "authentication_failed"}})
            return

        # 3. Authorization precedes alias resolution, and denial never enumerates.
        if payload["model"] != AUTHORIZED_ALIAS:
            self._reply(403, {"error": {"code": "resource_unavailable"}})
            return

        # 4. Only after allow does the alias resolve to a concrete model.
        self._reply(
            200,
            {
                "id": "resp_poc00001",
                "object": "response",
                "status": "completed",
                "model": "openai/gpt-4o-mini",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": '{"action":"conclude"}'}],
                    }
                ],
                "request_id": "00000000-0000-4000-8000-000000000001",
                "metadata": {
                    "requested_model_alias": AUTHORIZED_ALIAS,
                    "router": "openrouter",
                    "inference_provider": "openai",
                },
            },
        )


def build_probes() -> list[Probe]:
    return [
        Probe(
            name="minimal-client",
            payload={
                "model": AUTHORIZED_ALIAS,
                "input": "Summarise the payment failure alert.",
                "incident_id": "inc-otel-payment-failure",
                "run_id": "run-001",
                "task_id": "step-000",
            },
            api_key=AUTHORIZED_KEY,
            expected_status=200,
            why_it_matters=(
                "What a minimal harness sends. Base URL plus gateway credential plus "
                "logical alias, no provider secret anywhere."
            ),
        ),
        Probe(
            name="framework-tool-calling",
            payload={
                "model": AUTHORIZED_ALIAS,
                "input": "Investigate the payment failure.",
                "tools": [
                    {
                        "type": "function",
                        "name": "query_prometheus",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
            api_key=AUTHORIZED_KEY,
            expected_status=422,
            why_it_matters=(
                "What LangChain, LangGraph, PydanticAI and the OpenAI Agents SDK send "
                "the moment a tool is registered. The frozen contract has no `tools` "
                "property and forbids extra properties."
            ),
        ),
        Probe(
            name="framework-message-history",
            payload={
                "model": AUTHORIZED_ALIAS,
                "input": [
                    {"role": "system", "content": "You are an SRE investigator."},
                    {"role": "user", "content": "What failed?"},
                ],
            },
            api_key=AUTHORIZED_KEY,
            expected_status=422,
            why_it_matters=(
                "Every conversational framework sends a message array. The contract "
                "types `input` as a single string, so multi-turn state cannot be "
                "delegated to the provider."
            ),
        ),
        Probe(
            name="governed-denial",
            payload={"model": DENIED_ALIAS, "input": "Investigate the payment failure."},
            api_key=AUTHORIZED_KEY,
            expected_status=403,
            why_it_matters=(
                "A denial the harness must treat as a business decision, not an "
                "exception. No upstream call happens and no alias is enumerated."
            ),
        ),
    ]


def run_probe(base_url: str, probe: Probe) -> ProbeResult:
    """Send one probe using only a base URL and a bearer credential."""
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/v1/responses",
        data=json.dumps(probe.payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {probe.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read())
            detail = body.get("metadata", {}).get("requested_model_alias", "")
            return ProbeResult(probe, response.status, f"alias={detail}")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read())
            detail = body.get("error", {}).get("code", "")
        except (json.JSONDecodeError, ValueError):
            detail = ""
        return ProbeResult(probe, error.code, detail)
    except urllib.error.URLError as error:
        return ProbeResult(probe, 0, f"unreachable: {error.reason}")


def start_mock_gateway() -> tuple[HTTPServer, str]:
    MockGatewayHandler.validator = load_request_validator()
    server = HTTPServer(("127.0.0.1", 0), MockGatewayHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


def report(results: list[ProbeResult]) -> int:
    print("\nHT-06 proof of concept — gateway consumption probes")
    print("=" * 78)
    for result in results:
        verdict = "OK " if result.matches_contract else "DIFF"
        print(
            f"[{verdict}] {result.probe.name:<26} "
            f"expected={result.probe.expected_status} observed={result.observed_status} "
            f"{result.detail}"
        )
        print(f"        {result.probe.why_it_matters}")
    print("=" * 78)

    divergent = [result for result in results if not result.matches_contract]
    if divergent:
        print(f"{len(divergent)} probe(s) diverged from the contract.\n")
        return 1

    print(
        "Finding: a harness reaches the gateway with a base URL, a gateway credential\n"
        "and a logical alias, and never sees a provider secret. Tool calling and\n"
        "message history are rejected by the frozen contract, so the tool loop must\n"
        "live inside the harness for as long as the frozen contract stands.\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="HT-06 harness consumption probes")
    parser.add_argument("--base-url", help="Live gateway base URL. Omit to use the mock.")
    parser.add_argument("--api-key", help="Gateway credential for the live run.")
    arguments = parser.parse_args()

    server: HTTPServer | None = None
    if arguments.base_url:
        base_url = arguments.base_url
        if not arguments.api_key:
            print("--api-key is required with --base-url", file=sys.stderr)
            return 2
        probes = [
            Probe(
                probe.name,
                probe.payload,
                arguments.api_key,
                probe.expected_status,
                probe.why_it_matters,
            )
            for probe in build_probes()
        ]
    else:
        server, base_url = start_mock_gateway()
        print(f"Mock gateway on {base_url}, validating against contract {CONTRACT_RELEASE}.")
        probes = build_probes()

    try:
        results = [run_probe(base_url, probe) for probe in probes]
        return report(results)
    finally:
        if server is not None:
            server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
