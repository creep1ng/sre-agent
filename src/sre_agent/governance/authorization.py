"""Single policy authority for direct principal-action-resource grants."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

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
    """Evaluate authorization facts in the sole deterministic precedence order."""

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
        if principal.status != "active":
            return self._deny(AuthorizationDenialCause.PRINCIPAL_INACTIVE)

        resource = await self._resources.authorization_view(resource_type, resource_id)
        if resource is None or (resource.resource_type, resource.resource_id) != (
            resource_type,
            resource_id,
        ):
            return self._deny(AuthorizationDenialCause.RESOURCE_MISSING)
        if resource.status != "active":
            return self._deny(AuthorizationDenialCause.RESOURCE_INACTIVE)

        grant = await self._grants.find_active(
            principal.principal_id, action, resource_type, resource_id
        )
        if grant is None or not self._is_exact_active_grant(
            grant, principal.principal_id, action, resource_type, resource_id
        ):
            return self._deny(AuthorizationDenialCause.GRANT_NOT_APPLICABLE)
        return AuthorizationEvaluation(
            decision=PolicyDecision(
                decision="allow", reason_code="grant_matched", policy_id=grant.grant_id
            ),
            denial_cause=None,
        )

    @staticmethod
    def _is_exact_active_grant(
        grant: Grant,
        principal_id: str,
        action: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> bool:
        return (
            grant.principal_id == principal_id
            and grant.action == action
            and grant.resource.resource_type == resource_type
            and grant.resource.resource_id == resource_id
            and grant.effect == "allow"
            and grant.status == "active"
        )

    @staticmethod
    def _deny(cause: AuthorizationDenialCause) -> AuthorizationEvaluation:
        return AuthorizationEvaluation(
            decision=PolicyDecision(
                decision="deny", reason_code="no_matching_grant", policy_id=None
            ),
            denial_cause=cause,
        )
