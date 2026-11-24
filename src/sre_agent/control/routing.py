"""What every control router shares: its bearer scheme, error responses and request readers."""

from typing import Any

from fastapi import Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sre_agent.control.service import ErrorEnvelope


def bearer_credentials() -> Any:
    """The OpenAPI `HTTPBearer` scheme of the control routes; the header is read by hand."""
    return Security(HTTPBearer(auto_error=False, description="Administrative bearer credential"))


DESCRIPTIONS = {
    400: "Invalid idempotency key",
    401: "Authentication failed",
    403: "Resource unavailable",
    404: "Resource not found",
    409: "Idempotency conflict",
    422: "Validation error",
    503: "Audit unavailable",
}


def errors(*statuses: int, described: bool = False) -> dict[int | str, dict[str, Any]]:
    """The error envelope as the response of each status, with its description if asked."""
    return {
        status: {"model": ErrorEnvelope}
        | ({"description": DESCRIPTIONS[status]} if described else {})
        for status in statuses
    }


LIMIT_PARAMETER = {
    "name": "limit",
    "in": "query",
    "required": False,
    "schema": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
}


def authorization_from(
    credentials: HTTPAuthorizationCredentials | None, request: Request
) -> str | None:
    if credentials is not None:
        return f"{credentials.scheme} {credentials.credentials}"
    return request.headers.get("authorization")


def unknown_query(request: Request, *known: str) -> dict[str, str]:
    """The query parameters a route does not take; the use case refuses any."""
    return {key: value for key, value in request.query_params.items() if key not in known}
