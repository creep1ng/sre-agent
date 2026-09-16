# ruff: noqa: E501, I001

from time import monotonic
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.exceptions import HTTPException

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.gateway.providers import LLMProvider, ProviderFailure, ProviderRequest
from sre_agent.governance.dto import AuditEvent, Consumption
from sre_agent.persistence.repositories import AuditRepository, ResourceRepository


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "model": "triage-agent",
                    "input": "Summarize the current incident status.",
                    "incident_id": "inc_example",
                }
            ]
        },
    )
    model: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    input: Annotated[str, Field(min_length=1, max_length=65_536)]
    incident_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] = None  # type: ignore[assignment]
    run_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] = None  # type: ignore[assignment]
    task_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] = None  # type: ignore[assignment]


class ResponseContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["output_text"]
    text: Annotated[str, Field(min_length=1, max_length=65_536)]


class ResponseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["message"]
    role: Literal["assistant"]
    content: Annotated[list[ResponseContent], Field(min_length=1)]


class ResponseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_model_alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    router: Annotated[str, Field(min_length=1, max_length=100)]
    inference_provider: Annotated[str, Field(min_length=1, max_length=100)]
    consumption: Consumption


class ResponsesResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "resp_example01",
                    "object": "response",
                    "status": "completed",
                    "model": "openai/gpt-4o-mini",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "No active incidents."}],
                        }
                    ],
                    "request_id": "00000000-0000-4000-8000-000000000001",
                    "metadata": {
                        "requested_model_alias": "triage-agent",
                        "router": "openrouter",
                        "inference_provider": "openai",
                        "consumption": {
                            "availability": "absent",
                            "source": "openrouter",
                            "input_tokens": None,
                            "output_tokens": None,
                            "total_tokens": None,
                            "billed_usd": None,
                            "currency": None,
                            "precision": None,
                            "pricing_context": None,
                        },
                    },
                }
            ]
        },
    )
    id: Annotated[str, Field(pattern=r"^resp_[A-Za-z0-9_-]{8,}$")]
    object: Literal["response"]
    status: Literal["completed"]
    model: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")]
    output: Annotated[list[ResponseOutput], Field(min_length=1)]
    request_id: UUID
    metadata: ResponseMetadata


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Annotated[str, Field(min_length=1, max_length=100)]
    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            json_schema_extra={"pattern": r"^(?!.*(?:Authorization|Bearer\s|sk-[A-Za-z0-9])).*$"},
        ),
    ]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=300,
            json_schema_extra={"pattern": r"^(?!.*(?:Authorization|Bearer\s|sk-[A-Za-z0-9])).*$"},
        ),
    ]
    details: Annotated[list[ErrorDetail], Field(max_length=16)] = None  # type: ignore[assignment]


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "contract_validation_failed",
                        "message": "Request validation failed.",
                    },
                    "request_id": "00000000-0000-4000-8000-000000000001",
                    "retryable": False,
                }
            ]
        },
    )
    error: ErrorBody
    request_id: UUID
    retryable: bool


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
ERROR_MESSAGES = {
    "audit_unavailable": "Audit unavailable.",
}


def _empty_consumption(availability: Literal["absent", "unavailable"]) -> Consumption:
    return Consumption(
        availability=availability,
        source="openrouter",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        billed_usd=None,
        currency=None,
        precision=None,
        pricing_context=None,
    )


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
        identifiers = {name: value for name in ("incident_id", "run_id", "task_id")
                       if (value := getattr(request, name))}
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, "invoke", "llm_model", request.model
            )
            decision = evaluation.decision
            if decision.decision == "deny":
                return await self._finish(request_id, started, 403, "authorization", context=context,
                                          alias=request.model, decision=decision, reason="no_matching_grant",
                                          authorization_denial_cause=evaluation.denial_cause,
                                          identifiers=identifiers)
            async with self.sessions() as session:
                assignment = await ResourceRepository(session).resolve_assignment("llm_model", request.model)
        except AuthenticationFailed:
            return await self._finish(request_id, started, 401, "authentication",
                                      reason="authentication_failed", identifiers=identifiers)
        except Exception:
            return await self._finish(request_id, started, 503, "audit",
                                      reason="audit_unavailable", retryable=True,
                                      identifiers=identifiers,
                                      error_code="audit_unavailable")
        if assignment is None:
            return await self._finish(request_id, started, 503, "routing", context=context,
                                      alias=request.model, decision=decision,
                                      reason="routing_unavailable", retryable=True,
                                      identifiers=identifiers)
        try:
            provider_request = ProviderRequest(
                input=request.input,
                model=assignment.concrete_model,
                provider=assignment.inference_provider,
            )
        except ValidationError:
            # Persisted routing data can outlive provider identifier rules. Do
            # not let that configuration fault escape as an unaudited ASGI 500.
            return await self._finish(request_id, started, 503, "routing", context=context,
                                      alias=request.model, decision=decision,
                                      reason="routing_unavailable", retryable=True,
                                      identifiers=identifiers)
        try:
            result = await self.provider.create(provider_request)
            consumption = result.consumption or _empty_consumption("absent")
            payload = {"id": result.response_id, "object": "response", "status": "completed", "model": result.model, "output": [{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": result.text}]}],
                       "request_id": str(request_id), "metadata": {"requested_model_alias": request.model,
                       "router": assignment.router, "inference_provider": result.provider,
                       "consumption": consumption.model_dump(mode="json")}}
            return await self._finish(request_id, started, 200, "response", payload=payload,
                                      context=context, alias=request.model, decision=decision,
                                      assignment=assignment, identifiers=identifiers,
                                      consumption=consumption)
        except ProviderFailure as failure:
            status, reason, code = {"timeout": (504, "upstream_failed", "upstream_timeout"),
                                    "unavailable": (503, "upstream_unavailable", "upstream_unavailable"),
                                    "evidence_invalid": (502, "upstream_invalid", "provider_evidence_invalid")}.get(
                                        failure.kind, (502, "upstream_invalid", "upstream_invalid_response"))
            return await self._finish(request_id, started, status, "upstream", context=context,
                                      alias=request.model, decision=decision, assignment=assignment,
                                      reason=reason, retryable=status in {503, 504}, identifiers=identifiers,
                                      error_code=code, retry_after=failure.retry_after,
                                      consumption=failure.consumption or _empty_consumption("unavailable"))

    async def _finish(self, request_id, started, status, stage, *, payload=None,
                      error_code=None, retry_after=None, consumption: Consumption | None = None,
                      **facts):
        event = self.projector.event(request_id, status, max(0, int((monotonic() - started) * 1000)),
                                     stage, consumption=consumption, **facts)
        try:
            await self.audit.append(event)
        except Exception:
            error_code, status, payload = "audit_unavailable", 503, None
        if payload is not None:
            return JSONResponse(payload, status_code=status)
        code, message = error_code or ERRORS[status][0], ERRORS[status][1]
        message = ERROR_MESSAGES.get(code, message)
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        return JSONResponse({"error": {"code": code, "message": message},
                             "request_id": str(request_id), "retryable": status in {503, 504}},
                            status, headers=headers)


def responses_router(service: ResponsesService) -> APIRouter:
    class ResponsesRoute(APIRoute):
        def get_route_handler(self):
            route_handler = super().get_route_handler()

            async def validation_preserving_handler(request: Request):
                try:
                    return await route_handler(request)
                except RequestValidationError:
                    return await service.create(None, request.headers.get("authorization"))
                except HTTPException as failure:
                    if failure.status_code != 400:
                        raise
                    return await service.create(None, request.headers.get("authorization"))

            return validation_preserving_handler

    router = APIRouter(route_class=ResponsesRoute)
    bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")

    def documented_error(status: int, description: str, *, headers=None):
        code, message = ERRORS[status]
        example = {
            "error": {"code": code, "message": message},
            "request_id": "00000000-0000-4000-8000-000000000001",
            "retryable": status in {503, 504},
        }
        response = {
            "model": ErrorEnvelope,
            "description": description,
            "content": {"application/json": {"example": example}},
        }
        if headers:
            response["headers"] = headers
        return response

    error_responses = {
        401: documented_error(
            401,
            "Authentication failed.",
            headers={"WWW-Authenticate": {"schema": {"type": "string", "const": "Bearer"}}},
        ),
        403: documented_error(
            403, "The requested model alias is unavailable without enumeration."
        ),
        422: documented_error(422, "Contract validation failed before authentication."),
        502: documented_error(502, "Upstream output could not be safely adapted."),
        503: documented_error(
            503,
            "Routing, audit, or the upstream provider is temporarily unavailable.",
            headers={"Retry-After": {"schema": {"type": "string"}}},
        ),
        504: documented_error(
            504,
            "The upstream provider timed out.",
            headers={"Retry-After": {"schema": {"type": "string"}}},
        ),
    }

    @router.post(
        "/v1/responses",
        response_model=ResponsesResponse,
        responses=error_responses,
        summary="Create a completed textual response",
        operation_id="createResponse",
        description=(
            "Validation precedes authentication and alias authorization; routing occurs only after "
            "authorization."
        ),
        response_description="Completed textual response",
        tags=["Responses"],
        openapi_extra={
            "x-governed-scope": {
                "action": "invoke",
                "resource_type": "llm_model",
                "resource_id": "body.model",
            }
        },
    )
    async def create(
        request: Request,
        body: Annotated[
            ResponsesRequest,
            Body(description="Bounded textual, non-streaming response request."),
        ],
        _bearer: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(bearer),
        ] = None,
    ) -> JSONResponse:
        return await service.create(body, request.headers.get("authorization"))

    return router
