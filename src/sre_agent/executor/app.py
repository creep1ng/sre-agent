"""HTTP surface of the deploy-executor: catalog reads and the named operations (#720).

Served by ``uvicorn sre_agent.executor.app:app`` from the API image. Every
POST carries the gateway's signature (#743), checked before anything else,
and an ``Idempotency-Key``; the key binds to the operation and the payload
digest when execution starts, so a validation rejection leaves it free and a
replay after an execution returns the stored result.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
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
from starlette.background import BackgroundTask

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


_SALVAGED = re.compile(r'"(binding|payload_digest|execution_id|operation|service)":"([^"\\]*)"')
_SALVAGED_PARAMETERS = re.compile(r'"parameters":\{((?:"\w+":"[^"\\]*",?)*)')
_PAIR = re.compile(r'"(\w+)":"([^"\\]*)"')


class JournalUnwritable(Exception):
    """An append failed (a full disk, a read-only volume) and the file was left as it was."""


class Journal:
    """Append-only intent and result lines, re-read at start so keys outlive a restart.

    A last line cut off mid-write (#762) is replaced, atomically, by a complete ``truncated``
    record keeping the fragment and whatever key it still names, which then answers
    ``execution_unknown``. A damaged line before the last one, or a journal that cannot be
    written, sets ``problem`` instead: the executor starts but refuses every operation until an
    operator repairs the file or the volume.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self.records: dict[str, dict[str, Any]] = {}
        self.results: list[dict[str, Any]] = []
        self.problem: tuple[str, str] | None = None  # (error code, reason)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(path.parent, os.W_OK):
                raise PermissionError(errno.EROFS, f"{path.parent} is not writable")
            if path.exists():
                self._load(path.read_bytes())
        except OSError as error:  # no crash at import, so no restart loop
            reason = f"the journal cannot be written: {error.strerror}"
            self.problem = ("journal_unwritable", reason)
        if self.problem is not None:
            logger.error("deploy-executor journal %s: %s", path, self.problem[1])

    def _load(self, raw: bytes) -> None:
        lines = [(number, line) for number, line in enumerate(raw.split(b"\n"), 1) if line.strip()]
        for position, (number, line) in enumerate(lines):
            try:
                self._index(json.loads(line))
            except ValueError:
                if position == len(lines) - 1:
                    self._recover_tail(raw, line)
                    return
                if self.problem is None:
                    reason = f"line {number} of the journal is not a complete record"
                    self.problem = ("journal_corrupt", reason)
            except (KeyError, TypeError):
                if self.problem is None:
                    reason = f"line {number} of the journal is not a journal record"
                    self.problem = ("journal_corrupt", reason)
        if lines and self.problem is None and not raw.endswith(b"\n"):
            with self._path.open("ab") as stream:  # a complete last record that lost its newline
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())

    def _recover_tail(self, raw: bytes, line: bytes) -> None:
        fragment = line.decode("utf-8", errors="replace")
        found = _SALVAGED_PARAMETERS.search(fragment)
        parameters = dict(_PAIR.findall(found.group(1))) if found else {}
        record = {
            "kind": "truncated",
            **dict(_SALVAGED.findall(fragment)),
            # A rollback's to_tag tells the operator which version it may have rolled to.
            **({"parameters": parameters} if parameters else {}),
            "fragment": fragment,
            "recovered_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
        }
        kept = raw[: raw.rstrip().rfind(b"\n") + 1]
        temporary = self._path.with_name(self._path.name + ".recovering")
        with temporary.open("wb") as stream:
            stream.write(kept + json.dumps(record, separators=(",", ":")).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self._path)
        self._sync_directory()
        logger.warning(
            "deploy-executor journal: the last line was cut off mid-write; kept as a truncated "
            "record for binding %s, which answers execution_unknown",
            record.get("binding", "(not recoverable)"),
        )
        self._index(record)

    def _index(self, record: dict[str, Any]) -> None:
        if record["kind"] == "truncated":
            # The operation may have run: list it as unknown, and bind its key if it is known.
            if "binding" in record:
                self.records[record["binding"]] = record
            names = ("execution_id", "operation", "service", "parameters", "recovered_at")
            self.results.append(
                {
                    "status": 409,
                    "error": {
                        "code": "execution_unknown",
                        "message": "the journal's last line was cut off; this may have run",
                    },
                    **{name: record[name] for name in names if name in record},
                }
            )
            return
        self.records[record["binding"]] = record
        if record["kind"] == "result":
            self.results.append({"status": record["status"], **record["response"]})

    def _sync_directory(self) -> None:
        descriptor = os.open(self._path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def append(self, record: dict[str, Any]) -> None:
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        size = 0
        try:
            descriptor = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
            try:
                size = os.fstat(descriptor).st_size
                written = 0
                while written < len(line):
                    written += os.write(descriptor, line[written:])
                if record["kind"] == "intent":  # on disk before the first Docker call
                    os.fsync(descriptor)
            except OSError:
                # A partial write (a full disk) must not leave a fragment for the next record
                # to glue onto, or the next start would answer journal_corrupt forever.
                os.ftruncate(descriptor, size)
                raise
            finally:
                os.close(descriptor)
            if size == 0:
                self._sync_directory()
        except OSError as error:
            raise JournalUnwritable(error.strerror or str(error)) from error
        self._index(record)


class Executor:
    def __init__(
        self,
        catalog: Mapping[str, EnrolledService],
        operations: Operations,
        journal: Journal,
        signing_key: bytes | None,
        signature_window: float,
        record_change: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._catalog = catalog
        self._record_change = record_change
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
        if self._journal.problem is not None:
            return _error(503, *self._journal.problem)
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
                if record.get("payload_digest", payload_digest) != payload_digest:
                    return _error(
                        409, "idempotency_conflict", "the key was used with another payload"
                    )
                if record["kind"] in ("intent", "truncated"):
                    return _error(409, "execution_unknown", "that attempt recorded no result")
                replay = (
                    {**record["response"], "replayed": True}
                    if record["status"] == 200
                    else record["response"]
                )
                return JSONResponse(replay, status_code=record["status"])
            try:
                return await self._run(operation_name, service, payload, binding, payload_digest)
            except JournalUnwritable as error:
                # No intent on disk means Docker was never called; a lost result leaves the key
                # bound to its intent, which answers execution_unknown.
                message = f"the journal could not be written: {error}"
                return _error(503, "journal_unwritable", message)

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
        response = JSONResponse(body)
        if outcome == "rolled_back" and self._record_change is not None:
            # Sent after the answer (#770): the rollback neither waits for it nor depends on it.
            event = {"source": "deploy-executor", "external_id": execution_id, "kind": "rollback"}
            event |= {"service": service.service, "version": after["image"]}
            response.background = BackgroundTask(self._record_change, event)
        return response


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
    changes_url = settings.get("DEPLOY_EXECUTOR_CHANGES_URL", "").rstrip("/")
    changes_key = settings.get("DEPLOY_EXECUTOR_CHANGES_API_KEY", "")

    async def record_change(event: dict[str, Any]) -> None:
        # Best effort (#770): the rollback already happened, a missing record never fails it.
        try:
            response = await client.post(
                f"{changes_url}/v1/changes",
                json=event,
                headers={"Authorization": f"Bearer {changes_key}"},
                timeout=10,
            )
            response.raise_for_status()
        except Exception as error:  # only the type: a transport message can quote the header
            name = type(error).__name__
            logger.warning("rollback %s not recorded: %s", event["external_id"], name)

    executor = Executor(
        catalog,
        operations,
        journal,
        signing_key,
        float(settings.get("DEPLOY_EXECUTOR_SIGNATURE_WINDOW_SECONDS", "300")),
        record_change if changes_url and changes_key else None,
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
        if journal.problem is not None:  # fail closed without a restart loop (#762)
            body = {"status": "unavailable", "dependency": "journal", "reason": journal.problem[1]}
            return JSONResponse(body, status_code=503)
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
