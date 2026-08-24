"""Narrow async persistence ports for governance reads and audit appends."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    PolicyDecision,
    Principal,
    Resource,
)
from sre_agent.persistence.models import (
    AuditEventRow,
    CredentialRow,
    GrantRow,
    PrincipalRow,
    ResourceRow,
)
from sre_agent.persistence.projections import (
    project_audit_event,
    project_credential,
    project_grant,
    project_principal,
    project_resource,
)


class PrincipalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, principal_id: str) -> Principal | None:
        row = await self._session.get(PrincipalRow, principal_id)
        return project_principal(row) if row is not None else None


class CredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, credential_id: str) -> CredentialReference | None:
        row = await self._session.get(CredentialRow, credential_id)
        return project_credential(row) if row is not None else None


class ResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, resource_type: str, resource_id: str) -> Resource | None:
        row = await self._session.get(ResourceRow, (resource_type, resource_id))
        return project_resource(row) if row is not None else None


class GrantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active(
        self, principal_id: str, action: str, resource_type: str, resource_id: str
    ) -> Grant | None:
        row = await self._session.scalar(
            select(GrantRow).where(
                GrantRow.principal_id == principal_id,
                GrantRow.action == action,
                GrantRow.resource_type == resource_type,
                GrantRow.resource_id == resource_id,
                GrantRow.effect == "allow",
                GrantRow.status == "active",
            )
        )
        if row is None:
            return None
        return project_grant(
            {
                "grant_id": row.grant_id,
                "principal_id": row.principal_id,
                "action": row.action,
                "resource": {
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                },
                "effect": row.effect,
                "status": row.status,
                "created_at": row.created_at,
            }
        )

    async def decide(
        self, principal_id: str, action: str, resource_type: str, resource_id: str
    ) -> PolicyDecision:
        grant = await self.find_active(principal_id, action, resource_type, resource_id)
        if grant is None:
            return PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None)
        return PolicyDecision(
            decision="allow", reason_code="grant_matched", policy_id=grant.grant_id
        )


class AuditRepository:
    MAX_READ_LIMIT = 100

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: AuditEvent) -> None:
        values = event.model_dump(mode="json")
        values["occurred_at"] = event.occurred_at
        self._session.add(AuditEventRow(**values))
        await self._session.flush()

    async def read_recent(self, *, limit: int) -> list[AuditEvent]:
        if not 1 <= limit <= self.MAX_READ_LIMIT:
            raise ValueError(f"limit must be between 1 and {self.MAX_READ_LIMIT}")
        rows = await self._session.scalars(
            select(AuditEventRow)
            .order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.event_id.desc())
            .limit(limit)
        )
        return [project_audit_event(row) for row in rows]
