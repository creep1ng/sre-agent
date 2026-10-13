"""Closed, immutable routing evidence captured for one provider invocation."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sre_agent.gateway.providers import ConcreteModel, ProviderName
from sre_agent.governance.dto import ModelAlias

AliasName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
RouterName = Annotated[str, Field(min_length=1, max_length=64)]


class RequestAttribution(BaseModel):
    """Only routing identifiers; never request content, credentials, or headers."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    request_id: UUID
    requested_alias: AliasName
    requested_model: ConcreteModel
    requested_provider: ProviderName
    requested_router: RouterName
    credited_model: ConcreteModel | None = None
    credited_provider: ProviderName | None = None

    @classmethod
    def from_assignment(cls, request_id: UUID, assignment: ModelAlias) -> "RequestAttribution":
        """Freeze the assignment already loaded by the response service."""
        return cls.model_validate(
            {
                "request_id": request_id,
                "requested_alias": assignment.alias,
                "requested_model": assignment.concrete_model,
                "requested_provider": assignment.inference_provider,
                "requested_router": assignment.router,
            }
        )

    def with_credit(
        self,
        *,
        model: str | None,
        provider: str | None,
    ) -> "RequestAttribution":
        """Return a newly validated snapshot with explicit adapter evidence."""
        return type(self).model_validate(
            {
                **self.model_dump(mode="python"),
                "credited_model": model,
                "credited_provider": provider,
            }
        )
