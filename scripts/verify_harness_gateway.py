"""Verify the harness against the governed gateway, from inside the Compose network.

docs/harness-gateway.md runs this in the live-smoke container, with the overlay
compose.harness-verify.yaml supplying the two extra gateway credentials. It uses
the harness's own GatewayClient, never a stand-in, and prints one JSON line per
step: status codes, error codes and request ids. It never prints a credential or
the model's text, and it refuses to run where the provider key is visible.

    check   the permitted request, an alias-only change, a Principal without a
            grant, and a credential issued, used, revoked and used again
    route   replace the route behind one alias through the governed control
            plane, instead of recreating the environment
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any
from uuid import uuid4

import httpx

from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.ports import GatewayError

PROMPT = "Reply with one short health status."
CONTEXT = {
    "incident_id": "inc-harness-check",
    "run_id": "run-harness-check",
    "task_id": "task-harness-check",
}
EXPECTED = {
    "permitted request": {"status": 200, "client": "completed", "alias": "triage-agent"},
    "alias-only change": {"status": 200, "client": "completed", "alias": "remediation-agent"},
    "principal without grant": {
        "status": 403,
        "client": "denied",
        "error": "resource_unavailable",
    },
    "credential issued": {"status": 201},
    "before revocation": {"status": 200, "client": "completed"},
    "credential revoked": {"status": 204},
    "after revocation": {"status": 401, "client": "denied", "error": "authentication_failed"},
}


def gateway_url() -> str:
    return os.environ.get("INVESTIGATOR_GATEWAY_URL", "http://api:8000").rstrip("/")


def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['ADMIN_HUMAN_API_KEY']}"}


def report(step: str, **observed: Any) -> dict[str, Any]:
    print(json.dumps({"step": step, **observed}), flush=True)
    return observed


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("error", {}).get("code")
    except ValueError:
        return None


async def ask(step: str, key: str, alias: str) -> dict[str, Any]:
    """One request through the harness client, recording what the gateway answered."""

    seen: dict[str, Any] = {}

    async def record(response: httpx.Response) -> None:
        await response.aread()
        seen["status"] = response.status_code
        try:
            body = response.json()
        except ValueError:
            return
        seen["request_id"] = body.get("request_id")
        if response.status_code == 200:
            metadata = body.get("metadata", {})
            seen["alias"] = metadata.get("requested_model_alias")
            seen["provider"] = metadata.get("inference_provider")
            seen["consumption"] = (metadata.get("consumption") or {}).get("availability")
        else:
            seen["error"] = body.get("error", {}).get("code")

    settings = GatewaySettings.from_environment(
        {
            "INVESTIGATOR_GATEWAY_URL": gateway_url(),
            "INVESTIGATOR_GATEWAY_API_KEY": key,
            "INVESTIGATOR_MODEL_ALIAS": alias,
        }
    )
    http = httpx.AsyncClient(timeout=125, event_hooks={"response": [record]})
    client = GatewayClient(settings, http)
    try:
        await client.respond(input=PROMPT, **CONTEXT)
        seen["client"] = "completed"
    except GatewayError as error:
        seen["client"] = error.kind
    finally:
        await client.aclose()
    return report(step, **seen)


async def check() -> int:
    harness = os.environ["INCIDENT_HARNESS_API_KEY"]
    results = {
        "permitted request": await ask("permitted request", harness, "triage-agent"),
        "alias-only change": await ask("alias-only change", harness, "remediation-agent"),
        "principal without grant": await ask(
            "principal without grant", os.environ["RESTRICTED_HARNESS_API_KEY"], "triage-agent"
        ),
    }
    # A fresh idempotency key per run: repeating the check issues a new credential
    # instead of replaying one that an earlier run already revoked.
    headers = {**admin_headers(), "Idempotency-Key": f"harness-check-{uuid4().hex}"}
    async with httpx.AsyncClient(base_url=gateway_url(), timeout=30) as http:
        issued = await http.post(
            "/v1/principals/incident-harness/credentials", headers=headers, json={}
        )
        if issued.status_code != 201:
            results["credential issued"] = report(
                "credential issued", status=issued.status_code, error=error_code(issued)
            )
        else:
            results["credential issued"] = report("credential issued", status=201)
            created = issued.json()
            key, credential = created["key"], created["credential"]["credential_id"]
            results["before revocation"] = await ask("before revocation", key, "triage-agent")
            revoked = await http.delete(f"/v1/credentials/{credential}", headers=admin_headers())
            results["credential revoked"] = report("credential revoked", status=revoked.status_code)
            results["after revocation"] = await ask("after revocation", key, "triage-agent")
    differing = [
        step
        for step, wanted in EXPECTED.items()
        if any(results.get(step, {}).get(field) != value for field, value in wanted.items())
    ]
    if differing:
        print("RESULT: differs from the expectation: " + ", ".join(differing), flush=True)
        return 1
    print("RESULT: every step as expected", flush=True)
    return 0


async def route(alias: str, concrete_model: str, provider: str) -> int:
    """Replace the route behind an alias, guarded by the version the gateway returned.

    Recreating the environment would also adopt a new route, but it deletes the
    database and its audit trail. The governed route changes only the assignment,
    and a concurrent change answers 409 instead of being overwritten.
    """

    async with httpx.AsyncClient(base_url=gateway_url(), timeout=30) as http:
        current = await http.get(f"/v1/model-aliases/{alias}", headers=admin_headers())
        if current.status_code != 200:
            report("current route", status=current.status_code, error=error_code(current))
            return 1
        before = current.json()
        report(
            "current route",
            status=200,
            concrete_model=before["concrete_model"],
            inference_provider=before["inference_provider"],
            updated_at=before["updated_at"],
        )
        replaced = await http.put(
            f"/v1/model-aliases/{alias}/assignment",
            headers=admin_headers(),
            json={
                "concrete_model": concrete_model,
                "router": "openrouter",
                "inference_provider": provider,
                "expected_updated_at": before["updated_at"],
            },
        )
        if replaced.status_code != 200:
            report("replaced route", status=replaced.status_code, error=error_code(replaced))
            return 1
        after = replaced.json()
        report(
            "replaced route",
            status=200,
            concrete_model=after["concrete_model"],
            inference_provider=after["inference_provider"],
            updated_at=after["updated_at"],
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    operations = parser.add_subparsers(dest="operation", required=True)
    operations.add_parser("check", help="permitted, alias change, and the two rejections")
    replace = operations.add_parser("route", help="replace the route behind one alias")
    replace.add_argument("alias")
    replace.add_argument("concrete_model")
    replace.add_argument("provider")
    arguments = parser.parse_args()
    if "OPENROUTER_API_KEY" in os.environ:
        print("refusing to run: the provider key is visible to this client", file=sys.stderr)
        return 2
    if arguments.operation == "check":
        return asyncio.run(check())
    return asyncio.run(route(arguments.alias, arguments.concrete_model, arguments.provider))


if __name__ == "__main__":
    raise SystemExit(main())
