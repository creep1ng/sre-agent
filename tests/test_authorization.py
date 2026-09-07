from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import pytest

from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationDenialCause,
    ResourceAuthorizationFact,
)
from sre_agent.governance.dto import Grant, Principal, Resource, ResourceType

NOW = datetime(2026, 9, 3, tzinfo=UTC)
RESOURCE_TYPES: tuple[ResourceType, ...] = (
    "llm_model",
    "mcp_server",
    "mcp_tool",
    "skill",
    "bok_collection",
)


def principal(*, kind: Literal["human", "agent"] = "human", status: str = "active") -> Principal:
    return Principal(
        principal_id=f"{kind}-subject",
        kind=kind,
        display_name="admin role.yaml openai/gpt-4o",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def grant(subject: Principal, resource_type: ResourceType, resource_id: str) -> Grant:
    return Grant(
        grant_id=f"grant-{resource_type}",
        principal_id=subject.principal_id,
        action="invoke",
        resource=Resource(resource_type=resource_type, resource_id=resource_id),
        effect="allow",
        status="active",
        created_at=NOW,
    )


@dataclass
class ResourceFacts:
    fact: ResourceAuthorizationFact | None
    calls: int = 0

    async def authorization_view(
        self, resource_type: ResourceType, resource_id: str
    ) -> ResourceAuthorizationFact | None:
        self.calls += 1
        return self.fact


@dataclass
class GrantFacts:
    result: Grant | None
    calls: int = 0

    async def find_active(
        self, principal_id: str, action: str, resource_type: ResourceType, resource_id: str
    ) -> Grant | None:
        self.calls += 1
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ("human", "agent"))
@pytest.mark.parametrize("resource_type", RESOURCE_TYPES)
async def test_exact_active_grant_allows_every_resource_for_humans_and_agents(
    kind: Literal["human", "agent"], resource_type: ResourceType
) -> None:
    subject = principal(kind=kind)
    resources = ResourceFacts(ResourceAuthorizationFact(resource_type, "resource-id", "active"))
    grants = GrantFacts(grant(subject, resource_type, "resource-id"))

    result = await AuthorizationDecisionEngine(resources, grants).evaluate(
        subject, "invoke", resource_type, "resource-id"
    )

    assert result.decision.model_dump() == {
        "decision": "allow",
        "reason_code": "grant_matched",
        "policy_id": f"grant-{resource_type}",
    }
    assert result.denial_cause is None
    assert (resources.calls, grants.calls) == (1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("grant_status", ("revoked", "mismatched"))
async def test_revoked_or_mismatched_grants_deny_as_not_applicable(grant_status: str) -> None:
    subject = principal()
    resource_type: ResourceType = "mcp_tool"
    resources = ResourceFacts(ResourceAuthorizationFact(resource_type, "resource-id", "active"))
    candidate = grant(subject, resource_type, "resource-id")
    grants = GrantFacts(
        candidate.model_copy(update={"action": "read_metadata"})
        if grant_status == "mismatched"
        else candidate.model_copy(update={"status": "revoked"})
    )

    result = await AuthorizationDecisionEngine(resources, grants).evaluate(
        subject, "invoke", resource_type, "resource-id"
    )

    assert result.decision.model_dump() == {
        "decision": "deny",
        "reason_code": "no_matching_grant",
        "policy_id": None,
    }
    assert result.denial_cause == AuthorizationDenialCause.GRANT_NOT_APPLICABLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subject_status", "resource", "expected_cause", "expected_calls"),
    (
        ("inactive", None, AuthorizationDenialCause.PRINCIPAL_INACTIVE, (0, 0)),
        ("active", None, AuthorizationDenialCause.RESOURCE_MISSING, (1, 0)),
        (
            "active",
            ResourceAuthorizationFact("skill", "resource-id", "inactive"),
            AuthorizationDenialCause.RESOURCE_INACTIVE,
            (1, 0),
        ),
    ),
)
async def test_precedence_short_circuits_later_fact_readers(
    subject_status: str,
    resource: ResourceAuthorizationFact | None,
    expected_cause: AuthorizationDenialCause,
    expected_calls: tuple[int, int],
) -> None:
    subject = principal(status=subject_status)
    resources = ResourceFacts(resource)
    grants = GrantFacts(grant(subject, "skill", "resource-id"))

    result = await AuthorizationDecisionEngine(resources, grants).evaluate(
        subject, "invoke", "skill", "resource-id"
    )

    assert result.decision.reason_code == "no_matching_grant"
    assert result.denial_cause == expected_cause
    assert (resources.calls, grants.calls) == expected_calls


@pytest.mark.asyncio
async def test_role_name_model_and_yaml_cannot_influence_a_direct_grant_decision() -> None:
    subject = principal()
    resources = ResourceFacts(ResourceAuthorizationFact("llm_model", "resource-id", "active"))
    grants = GrantFacts(None)
    engine = AuthorizationDecisionEngine(resources, grants)

    result = await engine.evaluate(subject, "invoke", "llm_model", "resource-id")

    assert result.decision.model_dump() == {
        "decision": "deny",
        "reason_code": "no_matching_grant",
        "policy_id": None,
    }
    with pytest.raises(TypeError):
        await engine.evaluate(  # type: ignore[call-arg]
            subject, "invoke", "llm_model", "resource-id", role="admin", yaml_policy="allow"
        )
