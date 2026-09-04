# ruff: noqa: E501, I001

from time import monotonic
from typing import Annotated, Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.providers import LLMProvider, ProviderFailure, ProviderRequest
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import AuditEvent
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import AuditRepository, CredentialRepository, GrantRepository, ResourceRepository  # fmt: skip


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    input: Annotated[str, Field(min_length=1, max_length=65_536)]
    incident_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] | None = None
    run_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] | None = None
    task_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] | None = None


class AuditStore(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class PostgresAuditStore:
    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions

    async def append(self, event: AuditEvent) -> None:
        async with self._sessions() as session, session.begin():
            await AuditRepository(session).append(event)


# fmt: off
ERRORS = {
    401: ("authentication_failed", "Authentication failed."), 403: ("resource_unavailable", "Resource unavailable."),
    422: ("contract_validation_failed", "Request validation failed."), 502: ("provider_evidence_invalid", "Provider response was invalid."),
    503: ("upstream_unavailable", "Upstream provider unavailable."), 504: ("upstream_timeout", "Upstream provider timed out."),
}
class ResponsesService:  # noqa: E305
    def __init__(self, sessions: Any, provider: LLMProvider, audit: AuditStore,
                 projector: AuditProjector) -> None:
        self.sessions, self.provider, self.audit, self.projector = sessions, provider, audit, projector

    async def create(self, raw: Any, authorization: str | None) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        try:
            request = ResponsesRequest.model_validate(raw)
        except ValidationError:
            return await self._finish(request_id, started, 422, "validation",
                                      reason="contract_validation_failed")
        context = await self._authenticate(authorization)
        identifiers = {name: value for name in ("incident_id", "run_id", "task_id")
                       if (value := getattr(request, name))}
        if context is None:
            return await self._finish(request_id, started, 401, "authentication",
                                      reason="authentication_failed", identifiers=identifiers)
        async with self.sessions() as session:
            evaluation = await AuthorizationDecisionEngine(
                ResourceRepository(session), GrantRepository(session)
            ).evaluate(context.principal, "invoke", "llm_model", request.model)
        decision = evaluation.decision
        if decision.decision == "deny":
            return await self._finish(request_id, started, 403, "authorization", context=context,
                                      alias=request.model, decision=decision, reason="no_matching_grant",
                                      authorization_denial_cause=evaluation.denial_cause,
                                      identifiers=identifiers)
        async with self.sessions() as session:
            assignment = await ResourceRepository(session).resolve_assignment("llm_model", request.model)
        if assignment is None:
            return await self._finish(request_id, started, 503, "routing", context=context,
                                      alias=request.model, decision=decision,
                                      reason="routing_unavailable", retryable=True,
                                      identifiers=identifiers)
        try:
            result = await self.provider.create(ProviderRequest(input=request.input, model=assignment.concrete_model, provider=assignment.inference_provider))
            payload = {"id": result.response_id, "object": "response", "status": "completed", "model": result.model, "output": [{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": result.text}]}],
                       "request_id": str(request_id), "metadata": {"requested_model_alias": request.model,
                       "router": assignment.router, "inference_provider": result.provider}}
            return await self._finish(request_id, started, 200, "response", payload=payload,
                                      context=context, alias=request.model, decision=decision,
                                      assignment=assignment, identifiers=identifiers)
        except ProviderFailure as failure:
            status, reason, code = {"timeout": (504, "upstream_failed", "upstream_timeout"),
                                    "unavailable": (503, "upstream_unavailable", "upstream_unavailable"),
                                    "evidence_invalid": (502, "upstream_invalid", "provider_evidence_invalid")}.get(
                                        failure.kind, (502, "upstream_invalid", "upstream_invalid_response"))
            return await self._finish(request_id, started, status, "upstream", context=context,
                                      alias=request.model, decision=decision, assignment=assignment,
                                      reason=reason, retryable=status in {503, 504}, identifiers=identifiers,
                                      error_code=code, retry_after=failure.retry_after)

    async def _authenticate(self, authorization: str | None):
        scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
        if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
            return None
        async with self.sessions() as session:
            return await CredentialRepository(session).authenticate(key)

    async def _finish(self, request_id, started, status, stage, *, payload=None,
                      error_code=None, retry_after=None, **facts):
        event = self.projector.event(request_id, status, max(0, int((monotonic() - started) * 1000)),
                                     stage, **facts)
        try:
            await self.audit.append(event)
        except Exception:
            error_code, status, payload = "audit_unavailable", 503, None
        if payload is not None:
            return JSONResponse(payload, status_code=status)
        code, message = error_code or ERRORS[status][0], ERRORS[status][1]
        message = "Audit unavailable." if code == "audit_unavailable" else message
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        return JSONResponse({"error": {"code": code, "message": message},
                             "request_id": str(request_id), "retryable": status in {503, 504}},
                            status, headers=headers)


def responses_router(service: ResponsesService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/responses")
    async def create(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.create(body, request.headers.get("authorization"))

    return router
