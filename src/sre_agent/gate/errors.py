"""Typed errors of governed operations and the one envelope they become.

A governed route raises a `GovernedError` that names its status, code and message; the gate
turns it into the common envelope `{error, request_id, retryable}`, with `WWW-Authenticate` on
an authentication failure and the `Retry-After` the error carries.
"""

from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


class GovernedError(Exception):
    """A refusal or failure a governed operation answers with the common envelope."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str | None = None,
        *,
        retryable: bool = False,
        retry_after: str | None = None,
        headers: dict[str, str] | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(code)
        self.status, self.code, self.retryable = status, code, retryable
        self.message = message or code.replace("_", " ").capitalize() + "."
        self.headers = dict(headers or {})
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after
        # The audit stage a route records for this error, when the route audits.
        self.stage = stage

    def with_message(self, message: str) -> "GovernedError":
        """The same error with a message naming what failed (a validation detail)."""
        return GovernedError(
            self.status,
            self.code,
            message,
            retryable=self.retryable,
            headers=self.headers,
            stage=self.stage,
        )


class AuthenticationFailed(GovernedError):
    """Every credential condition, without saying which: missing, malformed, unknown, revoked,
    expired, or the principal inactive."""

    def __init__(self, message: str = "Authentication failed.") -> None:
        super().__init__(
            401,
            "authentication_failed",
            message,
            headers={"WWW-Authenticate": "Bearer"},
            stage="authentication",
        )


class InactivePrincipal(Exception):
    """A valid credential of an inactive principal. The gate answers it as any authentication
    failure; a route that audits records that the principal was refused."""


def refusal(status: int, code: str, message: str, *, retry_after: str = "5") -> GovernedError:
    """An error worded by its status: a 401 challenges with `WWW-Authenticate: Bearer`, a 503 is
    retryable with `Retry-After`; for a status another component reports (the deploy-executor,
    the triage service)."""
    if status == 401:
        return GovernedError(status, code, message, headers={"WWW-Authenticate": "Bearer"})
    if status == 503:
        return GovernedError(status, code, message, retryable=True, retry_after=retry_after)
    return GovernedError(status, code, message)


def error_response(error: GovernedError, request_id: UUID | str) -> JSONResponse:
    """The only place a governed error becomes an HTTP response."""
    return JSONResponse(
        {
            "error": {"code": error.code, "message": error.message},
            "request_id": str(request_id),
            "retryable": error.retryable,
        },
        status_code=error.status,
        headers=error.headers or None,
    )


def request_id_of(request: Request) -> UUID:
    supplied = request.headers.get("x-request-id")
    try:
        return UUID(supplied) if supplied else uuid4()
    except ValueError:
        return uuid4()


async def governed_error_handler(request: Request, error: Exception) -> JSONResponse:
    """The application's handler for a typed error raised outside the gate's pipeline."""
    assert isinstance(error, GovernedError)
    return error_response(error, request_id_of(request))
