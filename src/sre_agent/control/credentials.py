"""Credentials: the API keys a principal authenticates with, issued, listed, revoked and rotated."""

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from sre_agent.control.governed import (
    IDEMPOTENCY_CONFLICT,
    INVALID,
    NOT_FOUND,
    REFUSALS,
    ControlAudit,
    ControlGate,
    canonical_payload,
    idempotency_key,
    key_digest,
    page_limit,
    payload_sha256,
)
from sre_agent.control.operations import CONTROL
from sre_agent.control.routing import (
    authorization_from,
    bearer_credentials,
    errors,
    idempotency_key_parameter,
    raw_json,
    unknown_query,
)

# The response models stay with the rotation route in service.py until it moves too: one class
# each, so openapi.json keeps one schema per name.
from sre_agent.control.service import (
    CredentialIssue,
    CredentialIssueResponse,
    CredentialListResponse,
    CredentialMetadataResponse,
)
from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Released, failing_as
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.repositories import (
    CredentialRepository,
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    PrincipalRepository,
)
from sre_agent.vocabulary import is_identifier

ISSUE = CONTROL[("POST", "/v1/principals/{id}/credentials")]
LIST = CONTROL[("GET", "/v1/principals/{id}/credentials")]
REVOKE = CONTROL[("DELETE", "/v1/credentials/{id}")]
ISSUANCE_FAILED = GovernedError(
    500, "credential_issuance_failed", "Credential issuance could not be completed.", retryable=True
)
# A caller without the read grant cannot tell a principal's credentials exist.
HIDDEN = replace(REFUSALS, denied=NOT_FOUND)


class Credentials:
    """Issue, list and revoke the credentials of principals."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def _claim(
        self, session: Any, caller: PrincipalContext, path: str, key: str, body: Any, target: str
    ) -> Any:
        return await IdempotencyRepository(session).claim_or_replay(
            scope=f"{caller.principal.principal_id}|POST|{path}",
            key_digest=key_digest(key),
            payload_sha256=payload_sha256(body.model_dump(mode="json")),
            principal_id=caller.principal.principal_id,
            method="POST",
            canonical_path=path,
            binding="principal_lifetime",
            outcome=IdempotencyOutcome(response_status=201, resource_id=target, replayed=False),
        )

    async def _remember(
        self, session: Any, caller: PrincipalContext, path: str, key: str, payload: Any
    ) -> None:
        await IdempotencyRepository(session).set_response_payload(
            scope=f"{caller.principal.principal_id}|POST|{path}",
            key_digest=key_digest(key),
            response_payload=payload,
        )

    async def issue(
        self, caller: PrincipalContext, principal_id: str, body: CredentialIssue, key: str
    ) -> dict[str, Any]:
        """A new key, once; a replay answers its metadata without the secret."""
        path = f"/v1/principals/{principal_id}/credentials"
        try:
            async with self.sessions() as session, session.begin():
                if await PrincipalRepository(session).get(principal_id) is None:
                    raise NOT_FOUND
                binding = await self._claim(session, caller, path, key, body, principal_id)
                if binding.replayed:
                    return binding.outcome.response_payload
                with failing_as(ISSUANCE_FAILED):
                    issued = await CredentialRepository(session).issue(
                        principal_id, expires_at=body.expires_at
                    )
                metadata = {
                    "credential": issued.credential.model_dump(mode="json"),
                    "replaced_credential_id": None,
                    "secret_revealed": False,
                }
                await self._remember(session, caller, path, key, metadata)
        except IdempotencyConflictError:
            raise IDEMPOTENCY_CONFLICT from None
        return {**metadata, "key": issued.key, "secret_revealed": True}

    async def list(self, principal_id: str, limit: int) -> dict[str, Any]:
        async with self.sessions() as session:
            if await PrincipalRepository(session).get(principal_id) is None:
                raise NOT_FOUND
            items, truncated = await CredentialRepository(session).list_for_principal(
                principal_id, limit=limit
            )
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "limit": limit,
            "truncated": truncated,
        }

    async def revoke(self, credential_id: str) -> None:
        async with self.sessions() as session, session.begin():
            repository = CredentialRepository(session)
            if await repository.get(credential_id) is None:
                raise NOT_FOUND
            await repository.revoke(credential_id)


class CredentialRoutes:
    """The credential routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.credentials = Credentials(sessions)
        control = ControlAudit(audit, projector)
        self.issuing: ControlGate[tuple[str, CredentialIssue, str]] = ControlGate(
            sessions, control, ISSUE
        )
        self.listing: ControlGate[int] = ControlGate(sessions, control, LIST, refusals=HIDDEN)
        self.revoking: ControlGate[str] = ControlGate(sessions, control, REVOKE)

    @staticmethod
    def _keyed(target: str, raw: Any, key: str | None) -> tuple[str, CredentialIssue, str]:
        valid_key = idempotency_key(key)
        if not is_identifier(target):
            raise INVALID
        try:
            return target, CredentialIssue.model_validate_json(canonical_payload(raw)), valid_key
        except (TypeError, ValidationError):
            raise INVALID from None

    async def issue_credential(
        self, principal_id: str, raw: Any, authorization: str | None, key: str | None
    ) -> Response:
        async def issue(
            admission: Admission, request: tuple[str, CredentialIssue, str]
        ) -> Released:
            return Released(await self.credentials.issue(admission.context, *request), 201)

        return await self.issuing.run(
            authorization, issue, lambda: self._keyed(principal_id, raw, key)
        )

    async def list_credentials(
        self, principal_id: str, authorization: str | None, limit: Any, extra: dict[str, Any]
    ) -> Response:
        def validate() -> int:
            if not is_identifier(principal_id):
                raise INVALID
            return page_limit(limit, extra)

        async def list_(_admission: Admission, valid_limit: int) -> Released:
            return Released(await self.credentials.list(principal_id, valid_limit))

        return await self.listing.run(authorization, list_, validate)

    async def revoke_credential(self, credential_id: str, authorization: str | None) -> Response:
        def validate() -> str:
            if not is_identifier(credential_id):
                raise INVALID
            return credential_id

        async def revoke(_admission: Admission, valid_id: str) -> Response:
            await self.credentials.revoke(valid_id)
            return Response(status_code=204)

        return await self.revoking.run(authorization, revoke, validate)


def credentials_router(routes: CredentialRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

    @router.post(
        ISSUE.route,
        status_code=201,
        response_model=CredentialIssueResponse | CredentialMetadataResponse,
        responses=errors(400, 401, 403, 404, 409, 422, 500, 503),
        openapi_extra={"parameters": [idempotency_key_parameter()]},
    )
    async def issue_credential(
        principal_id: str,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.issue_credential(
            principal_id,
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

    @router.get(
        LIST.route, response_model=CredentialListResponse, responses=errors(401, 404, 422, 503)
    )
    async def list_credentials(
        principal_id: str,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.list_credentials(
            principal_id,
            authorization_from(credentials, request),
            request.query_params.get("limit", "100"),
            unknown_query(request, "limit"),
        )

    @router.delete(REVOKE.route, status_code=204, responses=errors(401, 403, 404, 422, 503))
    async def revoke_credential(
        credential_id: str,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.revoke_credential(
            credential_id, authorization_from(credentials, request)
        )

    return router
