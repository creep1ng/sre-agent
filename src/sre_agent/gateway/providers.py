"""Bounded provider port shared by gateway orchestration and adapters."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ConcreteModel = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")]
ProviderName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9._-]{0,63}$")]


class ProviderDTO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class ProviderRequest(ProviderDTO):
    input: Annotated[str, Field(min_length=1, max_length=65_536)]
    model: ConcreteModel
    provider: ProviderName


class ProviderResult(ProviderDTO):
    response_id: Annotated[str, Field(pattern=r"^resp_[A-Za-z0-9_-]{8,128}$")]
    model: ConcreteModel
    text: Annotated[str, Field(min_length=1, max_length=65_536)]
    provider: ProviderName


ProviderFailureKind = Literal["evidence_invalid", "invalid_response", "unavailable", "timeout"]


class ProviderFailure(Exception):
    def __init__(self, kind: ProviderFailureKind, *, retry_after: int | None = None) -> None:
        super().__init__(f"provider_{kind}")
        self.kind = kind
        self.retry_after = retry_after


class LLMProvider(Protocol):
    async def create(self, request: ProviderRequest) -> ProviderResult: ...
