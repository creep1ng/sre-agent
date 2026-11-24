"""Body of Knowledge versions: immutable collections of runbook chunks an agent may search."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from pydantic.json_schema import WithJsonSchema
from sqlalchemy.exc import IntegrityError

from sre_agent.bok.owner import BoKVersionCollision
from sre_agent.bok.publication import (
    BOK_SLUG_PATTERN,
    SEMVER_PATTERN,
    BoKAuthorRefused,
    BoKPublishRequest,
    BoKVersionRecord,
    BoKVersionSummary,
    publish_bok_version,
    read_bok_version,
)
from sre_agent.control.governed import (
    IDEMPOTENCY_CONFLICT,
    INVALID,
    NOT_FOUND,
    STATUS_CONFLICT,
    UNAVAILABLE,
    ControlAudit,
    ControlGate,
    Record,
    idempotency_key,
    key_digest,
    payload_sha256,
)
from sre_agent.control.operations import CONTROL
from sre_agent.control.routing import (
    authorization_from,
    bearer_credentials,
    errors,
    idempotency_key_parameter,
    raw_json,
    request_body,
)
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.repositories import (
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
)

PUBLISH = CONTROL[("POST", "/v1/bok/collections/versions")]
READ = CONTROL[("GET", "/v1/bok/collections/{collection_id}/versions/{version}")]


class BoK:
    """Publish BoK versions from the console and read them."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def publish(
        self, caller: PrincipalContext, body: BoKPublishRequest, key: str, record: Record
    ) -> tuple[dict[str, Any], int]:
        """The published version (201, or 200 when the same content was already published), or
        a replay's stored answer (200); every answer is audited in the transaction."""
        path = PUBLISH.path
        scope = f"{caller.principal.principal_id}|POST|{path}"
        try:
            async with self.sessions() as session, session.begin():
                idempotency = IdempotencyRepository(session)
                binding = await idempotency.claim_or_replay(
                    scope=scope,
                    key_digest=key_digest(key),
                    payload_sha256=payload_sha256(body.model_dump(mode="json")),
                    principal_id=caller.principal.principal_id,
                    method="POST",
                    canonical_path=path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201,
                        resource_id=f"{body.collection_id}@{body.version}",
                        replayed=False,
                    ),
                )
                if binding.replayed:
                    status, payload = 200, binding.outcome.response_payload
                else:
                    summary, created = await publish_bok_version(
                        session, body, author=caller.principal, origin="console"
                    )
                    status, payload = (201 if created else 200), summary.model_dump(mode="json")
                    await idempotency.set_response_payload(
                        scope=scope, key_digest=key_digest(key), response_payload=payload
                    )
                await record(session, status)
        except IdempotencyConflictError:
            raise IDEMPOTENCY_CONFLICT from None
        except BoKAuthorRefused:
            raise UNAVAILABLE from None
        except (BoKVersionCollision, IntegrityError):
            raise STATUS_CONFLICT from None
        return payload, status

    async def read(self, collection_id: str, version: str) -> dict[str, Any]:
        async with self.sessions() as session:
            found = await read_bok_version(session, collection_id, version)
        if found is None:
            raise NOT_FOUND
        return found.model_dump(mode="json")


class BoKRoutes:
    """The BoK routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.bok = BoK(sessions)
        control = ControlAudit(audit, projector)
        self.publishing: ControlGate[tuple[BoKPublishRequest, str]] = ControlGate(
            sessions, control, PUBLISH, reason="grant_matched"
        )
        self.reading: ControlGate[None] = ControlGate(
            sessions, control, READ, reason="grant_matched"
        )

    async def publish_bok_version(
        self, raw: Any, authorization: str | None, key: str | None
    ) -> Response:
        def validate() -> tuple[BoKPublishRequest, str]:
            valid_key = idempotency_key(key)
            try:
                return BoKPublishRequest.model_validate(raw), valid_key
            except ValidationError:
                raise INVALID from None

        async def publish(admission: Admission, request: tuple[BoKPublishRequest, str]) -> Released:
            record = self.publishing.record(admission)
            payload, status = await self.bok.publish(admission.context, *request, record)
            return Released(payload, status)

        return await self.publishing.run(authorization, publish, validate)

    async def get_bok_version(
        self, collection_id: str, version: str, authorization: str | None
    ) -> Response:
        def validate() -> None:
            if (
                re.fullmatch(BOK_SLUG_PATTERN, collection_id) is None
                or re.fullmatch(SEMVER_PATTERN, version) is None
                or len(version) > 32
            ):
                raise INVALID

        async def read(_admission: Admission, _request: None) -> Released:
            return Released(await self.bok.read(collection_id, version))

        return await self.reading.run(authorization, read, validate)


def bok_router(routes: BoKRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

    @router.post(
        PUBLISH.route,
        status_code=201,
        response_model=BoKVersionSummary,
        responses={200: {"model": BoKVersionSummary}, **errors(400, 401, 403, 409, 422, 503)},
        openapi_extra={
            "parameters": [idempotency_key_parameter()],
            **request_body(BoKPublishRequest),
            **PUBLISH.openapi_extra,
        },
    )
    async def publish_bok_version(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.publish_bok_version(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

    @router.get(
        READ.route,
        response_model=BoKVersionRecord,
        responses=errors(401, 403, 404, 422, 503),
        openapi_extra=READ.openapi_extra,
    )
    async def get_bok_version(
        collection_id: Annotated[
            str, WithJsonSchema({"type": "string", "pattern": BOK_SLUG_PATTERN})
        ],
        version: Annotated[
            str,
            WithJsonSchema({"type": "string", "maxLength": 32, "pattern": SEMVER_PATTERN}),
        ],
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.get_bok_version(
            collection_id, version, authorization_from(credentials, request)
        )

    return router
