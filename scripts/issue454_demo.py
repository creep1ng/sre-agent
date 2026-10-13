"""Real HTTP + PostgreSQL proof; run only in isolated python-checks after E2E setup.

Provider evidence is controlled, not a paid or live OpenRouter invocation. Only
closed request attribution and safe SQL routing columns are emitted; never keys,
headers, provider bodies, prompts, outputs, or raw audit references.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
import threading
import time
from pathlib import Path

import httpx
import psycopg
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from issue454_support import (
    ADMIN,
    AUDIT_KEY,
    CONSUMER,
    DATABASE_URL,
    RESTRICTED,
    ControlledProvider,
    auth,
)

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderResult
from sre_agent.settings import Settings


class CreditedControlledProvider(ControlledProvider):
    async def create(self, request):
        result = await super().create(request)
        return ProviderResult(
            response_id=result.response_id,
            model=result.model,
            text=result.text,
            provider=result.provider,
            consumption=result.consumption,
            credited_model=request.model,
            credited_provider=request.provider,
        )


def main() -> None:
    # Refuse arbitrary production/demo databases before any API or SQL mutation.
    runpy.run_path(str(Path(__file__).with_name("assert_test_database_isolated.py")))
    application = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY),
        llm_provider=CreditedControlledProvider(),
    )
    server = uvicorn.Server(
        uvicorn.Config(
            application, host="127.0.0.1", port=8765, log_level="error", access_log=False
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("controlled HTTP server did not start")
        time.sleep(0.05)
    report = {
        "provider": "controlled-test-double; no live/paid provider",
        "transport": "real HTTP over loopback",
        "tested_sha": os.environ.get("TESTED_SHA", "working-tree (not committed)"),
    }
    try:
        with httpx.Client(base_url="http://127.0.0.1:8765", timeout=15) as client:
            original = client.get("/v1/model-aliases/triage-agent", headers=auth(ADMIN))
            replacement = client.get("/v1/model-aliases/remediation-agent", headers=auth(ADMIN))
            original.raise_for_status()
            replacement.raise_for_status()
            original, replacement = original.json(), replacement.json()
            request = client.post(
                "/v1/responses",
                headers=auth(CONSUMER),
                json={"model": "triage-agent", "input": "controlled synthetic demo input"},
            )
            request.raise_for_status()
            request_id = request.json()["request_id"]
            params = {"request_id": request_id}
            before = client.get("/v1/usage/requests", params=params, headers=auth(ADMIN))
            before.raise_for_status()
            try:
                changed = client.put(
                    "/v1/model-aliases/triage-agent/assignment",
                    headers=auth(ADMIN),
                    json={
                        "concrete_model": replacement["concrete_model"],
                        "router": replacement["router"],
                        "inference_provider": replacement["inference_provider"],
                        "expected_updated_at": original["updated_at"],
                    },
                )
                changed.raise_for_status()
                after = client.get("/v1/usage/requests", params=params, headers=auth(ADMIN))
                after.raise_for_status()
                assert before.json() == after.json(), "historical attribution changed"
                report.update(
                    {
                        "request_id": request_id,
                        "before": before.json(),
                        "after": after.json(),
                        "current_alias_model": changed.json()["concrete_model"],
                        "historical_unchanged": True,
                    }
                )
            finally:
                current = client.get("/v1/model-aliases/triage-agent", headers=auth(ADMIN))
                current.raise_for_status()
                restored = client.put(
                    "/v1/model-aliases/triage-agent/assignment",
                    headers=auth(ADMIN),
                    json={
                        "concrete_model": original["concrete_model"],
                        "router": original["router"],
                        "inference_provider": original["inference_provider"],
                        "expected_updated_at": current.json()["updated_at"],
                    },
                )
                restored.raise_for_status()
            negatives = {}
            for name, headers, query, expected in [
                ("unauthenticated", {}, params, 401),
                ("forbidden", auth(RESTRICTED), params, 403),
                ("unbounded", auth(ADMIN), {}, 422),
                ("multiple_selectors", auth(ADMIN), {**params, "month": "2026-10"}, 422),
            ]:
                response = client.get("/v1/usage/requests", headers=headers, params=query)
                assert response.status_code == expected
                body = response.json()
                assert set(body) == {"error", "request_id", "retryable"}, "unexpected envelope"
                assert set(body["error"]) == {"code", "message"}, "partial error metadata"
                negatives[name] = {"status": response.status_code, "body": body}
            report["negatives"] = negatives
            with psycopg.connect(DATABASE_URL) as connection:
                row = connection.execute(
                    "SELECT request_id, requested_alias, requested_model, requested_provider, "
                    "credited_model, credited_provider FROM request_attributions "
                    "WHERE request_id = %s",
                    (request_id,),
                ).fetchone()
                assert (
                    row
                    and row[2] == original["concrete_model"]
                    and row[4] == original["concrete_model"]
                )
                report["postgres_snapshot"] = dict(
                    zip(
                        [
                            "request_id",
                            "requested_alias",
                            "requested_model",
                            "requested_provider",
                            "credited_model",
                            "credited_provider",
                        ],
                        row,
                        strict=True,
                    )
                )
            serialized = json.dumps(report, indent=2, sort_keys=True)
            for forbidden in (
                ADMIN,
                CONSUMER,
                RESTRICTED,
                AUDIT_KEY,
                "controlled synthetic demo input",
                "private attribution acceptance output",
                "hmac",
            ):
                assert forbidden not in serialized, "sensitive evidence suppressed"
            print(serialized)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        assert not thread.is_alive(), "controlled HTTP server did not stop"


if __name__ == "__main__":
    main()
