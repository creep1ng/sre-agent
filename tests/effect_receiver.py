"""Controlled external gateway with a real durable counter, not a local receipt."""

import asyncio
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from test_incident_investigator_http import HARNESS_KEY

from sre_agent.gateway.mcp import MCPDiscoveryResponse
from sre_agent.gateway.responses import _empty_consumption


def serve(port: int, directory: str, mode: str) -> None:
    ledger = Path(directory) / "receiver.sqlite"
    with sqlite3.connect(ledger) as connection:
        connection.executescript(
            "CREATE TABLE operations (sequence INTEGER PRIMARY KEY, request_id TEXT, "
            "incident_id TEXT, run_id TEXT, task_id TEXT, status TEXT);"
            "CREATE TABLE counter (value INTEGER NOT NULL); INSERT INTO counter VALUES (0);"
        )
    application = FastAPI()
    release = asyncio.Event()
    checkpoint = {"held": False, "stage": None}
    discovery_calls = 0

    async def hold(stage: str) -> None:
        checkpoint.update(held=True, stage=stage)
        await release.wait()
        checkpoint["held"] = False

    @application.get("/observations")
    def observations() -> dict:
        with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            operations = [
                dict(row)
                for row in connection.execute("SELECT * FROM operations ORDER BY sequence")
            ]
            counter = connection.execute("SELECT value FROM counter").fetchone()[0]
        return {"counter": counter, "operations": operations, "discovery_calls": discovery_calls}

    @application.get("/checkpoint")
    def boundary() -> dict:
        return checkpoint

    @application.post("/release")
    async def release_boundary() -> dict:
        release.set()
        return {"released": True}

    @application.get("/v1/mcp/discovery")
    async def discovery(request: Request) -> JSONResponse:
        nonlocal discovery_calls
        assert request.headers.get("Authorization") == f"Bearer {HARNESS_KEY}"
        discovery_calls += 1
        if mode == "before_dispatch":
            await hold("intent_before_dispatch")
        payload = {
            "request_id": str(uuid4()),
            "tools": [],
            "contract_version": "1.0.0",
            "server": {
                "resource_type": "mcp_server",
                "server_id": "controlled-counter",
                "display_name": "Controlled counter",
                "description": "Synthetic fixture",
                "visibility": "private",
                "tags": [],
            },
        }
        MCPDiscoveryResponse.model_validate(payload)
        return JSONResponse(payload)

    @application.post("/v1/responses")
    async def operate(request: Request) -> Response:
        assert request.headers.get("Authorization") == f"Bearer {HARNESS_KEY}"
        body = await request.json()
        request_id = str(uuid4())
        with sqlite3.connect(ledger) as connection:
            sequence = connection.execute(
                "INSERT INTO operations(request_id,incident_id,run_id,task_id,status) "
                "VALUES (?,?,?,?,?) RETURNING sequence",
                (request_id, body["incident_id"], body["run_id"], body["task_id"], "received"),
            ).fetchone()[0]
        if mode == "reject":
            with sqlite3.connect(ledger) as connection:
                connection.execute(
                    "UPDATE operations SET status='rejected' WHERE sequence=?", (sequence,)
                )
            return JSONResponse(
                {
                    "request_id": request_id,
                    "error": {
                        "code": "controlled_operation_rejected",
                        "message": "Controlled receiver rejected this sent operation.",
                    },
                    "retryable": False,
                },
                status_code=403,
            )
        if mode == "before_effect":
            await hold("dispatch_before_effect")
        if mode == "timeout":
            await asyncio.sleep(2)
        with sqlite3.connect(ledger) as connection:
            connection.execute("UPDATE counter SET value=value+1")
            connection.execute(
                "UPDATE operations SET status='applied' WHERE sequence=?", (sequence,)
            )
        if mode in {"after_effect", "before_commit", "concurrent"}:
            await hold("effect_before_response")
        if mode == "5xx":
            return JSONResponse(
                {
                    "request_id": request_id,
                    "error": {
                        "code": "controlled_response_failure",
                        "message": "Controlled response failed after effect commit.",
                    },
                    "retryable": True,
                },
                status_code=503,
            )
        if mode == "loss":
            # Send incomplete HTTP framing after the effect commits. The client
            # observes a real transport error, not an injected port exception.
            return Response(content=b"", headers={"Content-Length": "100"})
        action = json.dumps({"action": "conclude", "summary": "Synthetic counter applied."})
        return JSONResponse(
            {
                "request_id": request_id,
                "id": f"resp_controlled_{request_id.replace('-', '')}",
                "object": "response",
                "model": "controlled/counter",
                "metadata": {
                    "requested_model_alias": body["model"],
                    "router": "controlled",
                    "inference_provider": "controlled",
                    "consumption": _empty_consumption("absent").model_dump(mode="json"),
                },
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": action}],
                    }
                ],
            }
        )

    uvicorn.run(application, host="127.0.0.1", port=port, log_level="critical", access_log=False)
