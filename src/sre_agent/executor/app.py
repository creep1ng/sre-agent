"""HTTP surface of the deploy-executor: catalog reads and the named operations (#720).

Served by ``uvicorn sre_agent.executor.app:app`` from the API image. Every
POST carries the gateway's signature (#743), checked before anything else,
and an ``Idempotency-Key``; the key binds to the operation and the payload
digest when execution starts, so a validation rejection leaves it free and a
replay after an execution returns the stored result.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from os import environ
from pathlib import Path
from secrets import token_hex
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from sre_agent.executor.catalog import OPERATIONS, EnrolledService, load_catalog
from sre_agent.executor.docker import DockerClient, DockerInvalid, DockerTimeout, DockerUnavailable
from sre_agent.executor.operations import ExecutionError, Operations, container_view
from sre_agent.executor.signature import SIGNATURE_HEADER, TIMESTAMP_HEADER, usable_key, verify

CONTRACT_VERSION = "1.0.0"
logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    body = {"error": {"code": code, "message": message}, "request_id": str(uuid4())}
    headers = {"Retry-After": "15"} if retryable else {}
    return JSONResponse({**body, "retryable": retryable}, status_code=status, headers=headers)


_SIGNATURE_MESSAGES = {
    "signature_missing": "X-Executor-Timestamp and X-Executor-Signature are required",
    "signature_expired": "the signature timestamp is outside the accepted window",
    "signature_invalid": "the signature does not cover this method, path, key and body",
}


def _docker_error(error: Exception) -> JSONResponse:
    if isinstance(error, ExecutionError):
        return _error(error.status, error.code, error.message, error.retryable)
    if isinstance(error, DockerTimeout):
        return _error(504, "docker_timeout", "the Docker Engine did not answer in time", True)
    if isinstance(error, DockerUnavailable):
        return _error(
            503, "docker_unavailable", "the socket proxy or the daemon is unavailable", True
        )
    return _error(502, "docker_invalid", f"unexpected Docker Engine answer: {error}")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Journal:
    """Append-only intent and result lines, re-read at start so keys outlive a restart."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.records: dict[str, dict[str, Any]] = {}
        self.results: list[dict[str, Any]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                self._index(json.loads(line))

    def _index(self, record: dict[str, Any]) -> None:
        self.records[record["binding"]] = record
        if record["kind"] == "result":
            self.results.append({"status": record["status"], **record["response"]})

    def append(self, record: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._index(record)


class Executor:
    def __init__(
        self,
        catalog: Mapping[str, EnrolledService],
        operations: Operations,
        journal: Journal,
        signing_key: bytes | None,
        signature_window: float,
    ) -> None:
        self._catalog = catalog
        self._operations = operations
        self._journal = journal
        self._signing_key = signing_key
        self._signature_window = signature_window
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._service_locks: dict[str, asyncio.Lock] = {}

    async def execute(self, operation_name: str, request: Request) -> JSONResponse:
        if self._signing_key is None:
            return _error(
                503,
                "signing_key_unconfigured",
                "DEPLOY_EXECUTOR_SIGNING_KEY is unset or a placeholder",
            )
        # The signature comes first: an unsigned caller learns nothing, not even the operation.
        rejection = verify(
            self._signing_key,
            self._signature_window,
            request.method,
            request.url.path,
            request.headers.get("idempotency-key") or "",
            await request.body(),
            request.headers.get(TIMESTAMP_HEADER) or "",
            request.headers.get(SIGNATURE_HEADER) or "",
        )
        if rejection is not None:
            return _error(401, rejection, _SIGNATURE_MESSAGES[rejection])
        operation = OPERATIONS.get(operation_name)
        if operation is None:
            return _error(404, "operation_not_enrolled", f"'{operation_name}' is not an operation")
        key = request.headers.get("idempotency-key") or ""
        if not (16 <= len(key) <= 128 and key.isascii() and key.isprintable()):
            return _error(400, "invalid_idempotency_key", "Idempotency-Key must be 16-128 ASCII")
        try:
            parameters = operation.input_model.model_validate(await request.json())
        except ValidationError as error:
            detail = "; ".join(
                ".".join(str(part) for part in item["loc"]) + ": " + item["msg"]
                for item in error.errors()
            )
            return _error(422, "contract_validation_failed", detail or "invalid body")
        except ValueError:
            return _error(422, "contract_validation_failed", "the body must be a JSON object")
        service = self._catalog.get(parameters.service)
        if service is None:
            return _error(404, "service_not_enrolled", f"'{parameters.service}' is not enrolled")
        if operation_name not in service.operations:
            return _error(
                404, "operation_not_enrolled", f"'{service.service}' offers no {operation_name}"
            )
        payload = parameters.model_dump()
        payload_digest = _digest(json.dumps(payload, sort_keys=True))
        binding = f"{operation_name}:{_digest(key)}"
        # One request per key at a time: a double submission waits, then replays.
        async with self._key_locks.setdefault(binding, asyncio.Lock()):
            record = self._journal.records.get(binding)
            if record is not None:
                if record["payload_digest"] != payload_digest:
                    return _error(
                        409, "idempotency_conflict", "the key was used with another payload"
                    )
                if record["kind"] == "intent":
                    return _error(409, "execution_unknown", "that attempt recorded no result")
                replay = (
                    {**record["response"], "replayed": True}
                    if record["status"] == 200
                    else record["response"]
                )
                return JSONResponse(replay, status_code=record["status"])
            return await self._run(operation_name, service, payload, binding, payload_digest)

    async def _run(
        self,
        operation_name: str,
        service: EnrolledService,
        payload: dict[str, Any],
        binding: str,
        payload_digest: str,
    ) -> JSONResponse:
        execution_id = f"exe_{token_hex(8)}"
        started = monotonic()
        executed_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        base = {
            "binding": binding,
            "payload_digest": payload_digest,
            "execution_id": execution_id,
            "operation": operation_name,
            "service": service.service,
            "parameters": {name: value for name, value in payload.items() if name != "service"},
        }

        async def intent() -> None:
            self._journal.append({"kind": "intent", **base, "requested_at": executed_at})

        try:
            async with self._service_locks.setdefault(service.service, asyncio.Lock()):
                if operation_name == "deployment.rollback":
                    outcome, before, after = await self._operations.rollback(
                        service, payload["to_tag"], execution_id, intent
                    )
                else:
                    outcome, before, after = await self._operations.restart(service, intent)
        except (ExecutionError, DockerTimeout, DockerUnavailable, DockerInvalid) as error:
            response = _docker_error(error)
            if self._journal.records.get(binding, {}).get("kind") == "intent":
                # The key is bound: keep the definitive failure so a replay never re-executes.
                self._journal.append(
                    {
                        "kind": "result",
                        **base,
                        "status": response.status_code,
                        "response": json.loads(response.body),
                    }
                )
            return response
        body = {
            "execution_id": execution_id,
            "operation": operation_name,
            "service": service.service,
            "parameters": base["parameters"],
            "outcome": outcome,
            "replayed": False,
            "before": before,
            "after": after,
            "executed_at": executed_at,
            "duration_ms": int((monotonic() - started) * 1000),
        }
        self._journal.append({"kind": "result", **base, "status": 200, "response": body})
        return JSONResponse(body)


def create_executor_application(settings: Mapping[str, str] = environ) -> FastAPI:
    catalog = load_catalog(
        settings.get("DEPLOY_EXECUTOR_CATALOG", "/app/agent/executor/catalog.v1.yaml")
    )
    journal = Journal(
        Path(settings.get("DEPLOY_EXECUTOR_JOURNAL", "/var/lib/deploy-executor/executions.jsonl"))
    )
    client = httpx.AsyncClient()
    docker = DockerClient(client, settings.get("DOCKER_API_URL", "http://docker-socket-proxy:2375"))
    operations = Operations(
        docker,
        settings.get("HOSTNAME"),
        float(settings.get("DEPLOY_EXECUTOR_SETTLE_SECONDS", "30")),
    )
    signing_key = usable_key(settings.get("DEPLOY_EXECUTOR_SIGNING_KEY"))
    executor = Executor(
        catalog,
        operations,
        journal,
        signing_key,
        float(settings.get("DEPLOY_EXECUTOR_SIGNATURE_WINDOW_SECONDS", "300")),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(title="deploy-executor", version=CONTRACT_VERSION, lifespan=lifespan)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        if signing_key is None:  # fail closed: unready until the key is configured
            return JSONResponse(
                {"status": "unavailable", "dependency": "signing_key"}, status_code=503
            )
        try:
            await docker.ping()
        except Exception:  # the answer names the dependency, never the transport error
            return JSONResponse({"status": "unavailable", "dependency": "docker"}, status_code=503)
        return JSONResponse({"status": "ok", "dependency": "docker"})

    @app.get("/v1/catalog")
    async def read_catalog() -> dict[str, Any]:
        services = [service.describe() for service in catalog.values()]
        return {"contract_version": CONTRACT_VERSION, "services": services}

    @app.get("/v1/services/{service}")
    async def read_service(service: str) -> JSONResponse:
        enrolled = catalog.get(service)
        if enrolled is None:
            return _error(404, "service_not_enrolled", f"'{service}' is not enrolled")
        try:
            inspect = await operations.find(enrolled)
            tags = await operations.available_tags(enrolled)
        except (ExecutionError, DockerTimeout, DockerUnavailable, DockerInvalid) as error:
            return _docker_error(error)
        view = {**enrolled.describe(), "container": container_view(inspect), "available_tags": tags}
        return JSONResponse(view)

    @app.get("/v1/executions")
    async def read_executions() -> dict[str, Any]:
        return {"executions": journal.results}

    @app.post("/v1/operations/{operation}")
    async def execute(operation: str, request: Request) -> JSONResponse:
        return await executor.execute(operation, request)

    return app


app = create_executor_application()
