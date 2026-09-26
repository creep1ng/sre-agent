"""Single policy authority for direct principal-action-resource grants."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from sre_agent import _core
from sre_agent.governance.dto import Grant, PolicyDecision, Principal, ResourceType


class AuthorizationDenialCause(StrEnum):
    """Audit-only causes for the closed authorization-denial taxonomy."""

    PRINCIPAL_INACTIVE = "principal_inactive"
    RESOURCE_MISSING = "resource_missing"
    RESOURCE_INACTIVE = "resource_inactive"
    GRANT_NOT_APPLICABLE = "grant_not_applicable"


@dataclass(frozen=True, slots=True)
class ResourceAuthorizationFact:
    """The routing-safe resource state required for authorization."""

    resource_type: ResourceType
    resource_id: str
    status: Literal["active", "inactive"]


class ResourceFactReader(Protocol):
    """Returns only generic resource authorization facts."""

    async def authorization_view(
        self, resource_type: ResourceType, resource_id: str
    ) -> ResourceAuthorizationFact | None: ...


class GrantFactReader(Protocol):
    """Returns the one exact active direct grant, when it exists."""

    async def find_active(
        self, principal_id: str, action: str, resource_type: ResourceType, resource_id: str
    ) -> Grant | None: ...


@dataclass(frozen=True, slots=True)
class AuthorizationEvaluation:
    """A public decision paired with its audit-only denial cause."""

    decision: PolicyDecision
    denial_cause: AuthorizationDenialCause | None

    def __post_init__(self) -> None:
        if self.decision.decision == "allow" and self.denial_cause is not None:
            raise ValueError("allowed evaluations cannot carry a denial cause")
        if self.decision.decision == "deny" and self.denial_cause is None:
            raise ValueError("denied evaluations require a denial cause")


class AuthorizationDecisionEngine:
    """Gather staged facts and translate the Rust policy result."""

    def __init__(self, resources: ResourceFactReader, grants: GrantFactReader) -> None:
        self._resources = resources
        self._grants = grants

    async def evaluate(
        self,
        principal: Principal,
        action: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> AuthorizationEvaluation:
        # Reading is staged to preserve the existing I/O boundary; Rust still
        # evaluates every supplied fact and is the only decision authority.
        resource = None
        grant = None
        if principal.status == "active":
            resource = await self._resources.authorization_view(resource_type, resource_id)
            if (
                resource is not None
                and (resource.resource_type, resource.resource_id) == (resource_type, resource_id)
                and resource.status == "active"
            ):
                grant = await self._grants.find_active(
                    principal.principal_id, action, resource_type, resource_id
                )

        allowed, reason_code, policy_id, cause = _core.evaluate_authorization(
            principal.status,
            principal.principal_id,
            action,
            resource_type,
            resource_id,
            (resource.resource_type, resource.resource_id, resource.status) if resource else None,
            (
                grant.grant_id,
                grant.principal_id,
                grant.action,
                grant.resource.resource_type,
                grant.resource.resource_id,
                grant.effect,
                grant.status,
            )
            if grant
            else None,
        )
        return AuthorizationEvaluation(
            decision=PolicyDecision(
                decision="allow" if allowed else "deny",
                reason_code=reason_code,
                policy_id=policy_id,
            ),
            denial_cause=AuthorizationDenialCause(cause) if cause else None,
        )
