"""The gate every governed operation goes through.

The order is fixed and the same on every route (docs/architecture.md): validate the request,
authenticate the bearer credential (an inactive principal is not authenticated), authorize the
declared scope, run the use case, write the terminal audit, respond. A refusal at any step ends
the request there: a denied request never reaches its use case. A route that audits records
every terminal outcome through its auditor before the response is released; when that write
fails, the route answers its `audit_unavailable` error instead.

A route maps a failure to its typed error only inside a `failing_as` block, which catches any
exception unless the route names narrower ones, as the routes' own `except Exception` did before
the gate. Outside those blocks an exception is a defect and escapes as a logged 500.
"""

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from fastapi import Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from sre_agent.gate.authentication import active_principal
from sre_agent.gate.errors import (
    AuthenticationFailed,
    GovernedError,
    InactivePrincipal,
    error_response,
)
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
    ResourceFactReader,
)
from sre_agent.governance.dto import PrincipalContext, ResourceType
from sre_agent.persistence.repositories import GrantRepository, OwnerResourceFactReader

T = TypeVar("T")


@dataclass(frozen=True)
class Scope:
    """What a request asks to do: an action on one resource."""

    action: str
    resource_type: ResourceType
    resource_id: str


@dataclass(frozen=True)
class ScopeDeclaration:
    """An operation registered in the gate, with its scope; `resource_id` may name where the
    request carries it (`body.model`, `path.collection_id@version`). An operation that documents
    the scope uses `openapi_extra` as its `x-governed-scope`; the others do not change their
    OpenAPI entry."""

    method: str
    path: str
    action: str
    resource_type: ResourceType
    resource_id: str

    @property
    def openapi_extra(self) -> dict[str, Any]:
        return {
            "x-governed-scope": {
                "action": self.action,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
            }
        }


_DECLARED: dict[tuple[str, str], ScopeDeclaration] = {}
# The operations `Gate.run` answered in this process: a declared operation that answers by
# hand never appears here.


def declare(
    method: str, path: str, *, action: str, resource_type: ResourceType, resource_id: str
) -> ScopeDeclaration:
    """Register an operation in the gate and return the scope its OpenAPI entry documents."""
    declaration = ScopeDeclaration(method.upper(), path, action, resource_type, resource_id)
    registered = _DECLARED.setdefault((declaration.method, path), declaration)
    if registered != declaration:
        raise ValueError(f"{declaration.method} {path} is declared with two scopes")
    return declaration


def governed_operations() -> Mapping[tuple[str, str], ScopeDeclaration]:
    return dict(_DECLARED)


@contextmanager
def failing_as(
    error: GovernedError, failures: tuple[type[BaseException], ...] = (Exception,)
) -> Iterator[None]:
    """Answer `error` when the block raises one of `failures` (any exception by default), the
    failures a route maps to its typed error; a typed error and anything else pass through."""
    try:
        yield
    except GovernedError:
        raise
    except Exception as failure:
        if not isinstance(failure, failures):
            raise
        raise error from None


@dataclass(frozen=True)
class Refusals:
    """A route's own wording of the gate's refusals. `unavailable` answers the failures
    `unavailable_on` names while authenticating and authorizing (none: they escape)."""

    denied: GovernedError
    unavailable: GovernedError
    unavailable_on: tuple[type[BaseException], ...] = (Exception,)
    unauthenticated: GovernedError = field(default_factory=AuthenticationFailed)
    audit_unavailable: GovernedError = field(
        default_factory=lambda: GovernedError(
            503, "audit_unavailable", "Audit unavailable.", retryable=True, stage="audit"
        )
    )


@dataclass
class Admission:
    """An authenticated, authorized request: what its use case receives."""

    request_id: UUID
    context: PrincipalContext
    evaluation: AuthorizationEvaluation | None
    # Evidence the use case adds for the route's audit.
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Released:
    """A use case's JSON result; the gate releases it once its audit is written."""

    payload: Any
    status: int = 200
    headers: Mapping[str, str] | None = None

    def response(self) -> JSONResponse:
        return JSONResponse(
            jsonable_encoder(self.payload), status_code=self.status, headers=self.headers
        )


@dataclass(frozen=True)
class Terminal:
    """How a request ended, as the route's auditor records it."""

    request_id: UUID
    latency_ms: int
    status: int
    stage: str
    context: PrincipalContext | None
    evaluation: AuthorizationEvaluation | None
    error: GovernedError | None
    facts: Mapping[str, Any]
    # The validated request, or None when validation refused it.
    request: Any = None
    # The scope evaluated, or the declared one when the request ended before evaluation.
    scope: Scope | None = None
    # A valid credential of an inactive principal, refused as unauthenticated.
    inactive: bool = False


Auditor = Callable[[Terminal], Awaitable[None]]
Authenticator = Callable[[str | None], Awaitable[PrincipalContext | None]]
# Authenticates and evaluates one scope in a single call; None as the context is unauthenticated.
Admitter = Callable[
    [str | None, Scope], Awaitable[tuple[PrincipalContext | None, AuthorizationEvaluation | None]]
]
Authorizer = Callable[[Any, PrincipalContext, Scope], Awaitable[AuthorizationEvaluation]]
UseCase = Callable[[Admission, T], Awaitable[Released | Response]]


class Gate(Generic[T]):
    """Validate, authenticate, authorize, run, audit and respond, in that order."""

    def __init__(
        self,
        sessions: Any,
        refusals: Refusals,
        *,
        facts: Callable[[Any], ResourceFactReader] = OwnerResourceFactReader,
        authenticate: Authenticator | None = None,
        authorizer: Authorizer | None = None,
        admit: Admitter | None = None,
        audit: Auditor | None = None,
    ) -> None:
        self.sessions, self.refusals, self._facts = sessions, refusals, facts
        self._authenticate = authenticate or self._principal
        self._authorizer = authorizer or self._evaluate
        self._admit = admit
        self._audit = audit

    async def _principal(self, authorization: str | None) -> PrincipalContext | None:
        return await active_principal(self.sessions, authorization)

    async def _evaluate(
        self, session: Any, context: PrincipalContext, scope: Scope
    ) -> AuthorizationEvaluation:
        engine = AuthorizationDecisionEngine(self._facts(session), GrantRepository(session))
        return await engine.evaluate(
            context.principal, scope.action, scope.resource_type, scope.resource_id
        )

    async def authorize(self, context: PrincipalContext, scope: Scope) -> AuthorizationEvaluation:
        """Evaluate a scope for an authenticated principal; a use case that needs a second scope
        (a pinned dependency, a tool behind a server) calls this too."""
        async with self.sessions() as session:
            return await self._authorizer(session, context, scope)

    async def run(
        self,
        operation: ScopeDeclaration,
        authorization: str | None,
        scope: Scope | Callable[[T], Scope],
        use_case: UseCase[T],
        *,
        validate: Callable[[], T] | None = None,
        request_id: UUID | None = None,
        authenticate: Authenticator | None = None,
    ) -> Response:
        """Answer one request of `operation`. `validate` raises the route's validation error or
        returns what the use case and a scope computed from the request receive. `authenticate`
        replaces the bearer lookup for one request whose caller another record vouches for (a
        linked chat)."""
        request_id, started = request_id or uuid4(), monotonic()
        context: PrincipalContext | None = None
        evaluation: AuthorizationEvaluation | None = None
        facts: dict[str, Any] = {}
        stage, response, error, request = "validation", None, None, None
        resolved = scope if isinstance(scope, Scope) else None
        inactive = False
        try:
            request = validate() if validate is not None else None
            stage = "authentication"
            if callable(scope):
                resolved = scope(request)
            assert resolved is not None
            with failing_as(self.refusals.unavailable, self.refusals.unavailable_on):
                try:
                    if self._admit is not None:
                        context, evaluation = await self._admit(authorization, resolved)
                    else:
                        context = await (authenticate or self._authenticate)(authorization)
                except InactivePrincipal:
                    inactive = True
                if context is None:
                    raise self.refusals.unauthenticated
                stage = "authorization"
                if evaluation is None:
                    evaluation = await self.authorize(context, resolved)
            if evaluation.decision.decision != "allow":
                raise self.refusals.denied
            stage = "response"
            admission = Admission(request_id, context, evaluation, facts)
            result = await use_case(admission, request)
            response = result.response() if isinstance(result, Released) else result
        except GovernedError as refusal:
            # Routes raise shared error constants: drop what the raise attached, or the
            # constant would keep this request's frames, and their database pool, alive.
            refusal.__traceback__ = refusal.__context__ = refusal.__cause__ = None
            error = refusal
        if error is not None:
            stage = error.stage or stage
        else:
            assert response is not None
        if self._audit is not None:
            terminal = Terminal(
                request_id,
                max(0, int((monotonic() - started) * 1000)),
                error.status if error is not None else response.status_code,  # type: ignore[union-attr]
                stage,
                context,
                evaluation,
                error,
                facts,
                request,
                resolved,
                inactive,
            )
            try:
                await self._audit(terminal)
            except Exception:
                return error_response(self._audit_failure(error), request_id)
        return error_response(error, request_id) if error is not None else response

    def _audit_failure(self, error: GovernedError | None) -> GovernedError:
        """The route's `audit_unavailable`, keeping the `Retry-After` of the error it replaces."""
        failure = self.refusals.audit_unavailable
        retry_after = error.headers.get("Retry-After") if error is not None else None
        if retry_after is None or "Retry-After" in failure.headers:
            return failure
        return GovernedError(
            failure.status,
            failure.code,
            failure.message,
            retryable=failure.retryable,
            retry_after=retry_after,
            headers=failure.headers,
            stage=failure.stage,
        )
