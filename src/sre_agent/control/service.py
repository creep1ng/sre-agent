"""The control plane's error envelope.

`openapi.json` names these schemas after this module (`sre_agent__control__service__ErrorEnvelope`,
`...__ErrorDetail`), because `sre_agent.gateway.responses` declares models of the same names: they
stay here so the published contract stays identical. The control routes are in one module per
resource (`principals`, `credentials`, `grants`, `aliases`, `catalog`, `skills`, `bok`,
`consumption_limits`), composed by `control.plane`.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SAFE_ERROR_MESSAGE_PATTERN = r"^(?!.*(?:Authorization|Bearer\s|sk-[A-Za-z0-9])).*$"


class ErrorFieldDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Annotated[str, Field(min_length=1, max_length=100)]
    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            json_schema_extra={"pattern": SAFE_ERROR_MESSAGE_PATTERN},
        ),
    ]


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=300,
            json_schema_extra={"pattern": SAFE_ERROR_MESSAGE_PATTERN},
        ),
    ]
    details: Annotated[list[ErrorFieldDetail], Field(max_length=16)] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorDetail
    request_id: UUID
    retryable: bool
