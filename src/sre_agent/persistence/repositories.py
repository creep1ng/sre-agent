"""Narrow async persistence ports for governance reads and audit appends."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    ModelAlias,
    PolicyDecision,
    Principal,
    PrincipalContext,
    Resource,
)
from sre_agent.persistence.api_keys import (
    api_key_prefix,
    candidate_prefixes,
    generate_api_key,
    hash_api_key,
    verify_api_key,
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
    project_model_alias,
    project_principal,
    project_resource,
)


class PrincipalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, principal_id: str) -> Principal | None:
        row = await self._session.get(PrincipalRow, principal_id)
        return project_principal(row) if row is not None else None


@dataclass(frozen=True, slots=True)
class IssuedAPIKey:
    credential: CredentialReference
    key: str = field(repr=False)
    replaced_credential_id: None = None
    secret_revealed: bool = True


class CredentialRepository:
    ISSUANCE_ATTEMPTS = 5

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, credential_id: str) -> CredentialReference | None:
        row = await self._session.get(CredentialRow, credential_id)
        return project_credential(row) if row is not None else None

    async def issue(
        self,
        principal_id: str,
        *,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> IssuedAPIKey:
        issued_at = now or datetime.now(UTC)
        for _attempt in range(self.ISSUANCE_ATTEMPTS):
            key = generate_api_key()
            row = CredentialRow(
                credential_id=f"credential-{uuid4().hex}",
                principal_id=principal_id,
                prefix=api_key_prefix(key),
                key_hash=hash_api_key(key),
                status="active",
                created_at=issued_at,
                expires_at=expires_at,
                revoked_at=None,
            )
            try:
                async with self._session.begin_nested():
                    self._session.add(row)
                    await self._session.flush()
            except IntegrityError as error:
                constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                if constraint == "uq_credentials_prefix":
                    continue
                raise
            return IssuedAPIKey(credential=project_credential(row), key=key)
        raise RuntimeError("credential issuance exhausted after prefix collisions")

    async def authenticate(
        self, key: str, *, now: datetime | None = None
    ) -> PrincipalContext | None:
        authenticated_at = now or datetime.now(UTC)
        matches = await self._session.execute(
            select(CredentialRow, PrincipalRow)
            .join(PrincipalRow, PrincipalRow.principal_id == CredentialRow.principal_id)
            .where(CredentialRow.prefix.in_(candidate_prefixes(key)))
        )
        for credential, principal in matches:
            if (
                credential.status == "active"
                and principal.status == "active"
                and (credential.expires_at is None or credential.expires_at > authenticated_at)
                and verify_api_key(key, credential.key_hash)
            ):
                return PrincipalContext(
                    principal=project_principal(principal),
                    credential_id=credential.credential_id,
                    authenticated_at=authenticated_at,
                )
        return None

    async def revoke(
        self, credential_id: str, *, now: datetime | None = None
    ) -> CredentialReference | None:
        revoked_at = now or datetime.now(UTC)
        await self._session.execute(
            update(CredentialRow)
            .where(
                CredentialRow.credential_id == credential_id,
                CredentialRow.status == "active",
            )
            .values(status="revoked", revoked_at=revoked_at)
        )
        row = await self._session.get(CredentialRow, credential_id)
        return project_credential(row) if row is not None else None


class ResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authorization_view(
        self, resource_type: str, resource_id: str
    ) -> "ResourceAuthorizationView | None":
        row = (
            await self._session.execute(
                select(
                    ResourceRow.resource_type,
                    ResourceRow.resource_id,
                    ResourceRow.status,
                ).where(
                    ResourceRow.resource_type == resource_type,
                    ResourceRow.resource_id == resource_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return ResourceAuthorizationView(*row)

    async def get(self, resource_type: str, resource_id: str) -> Resource | None:
        view = await self.authorization_view(resource_type, resource_id)
        return project_resource(view) if view is not None else None

    async def resolve_assignment(self, resource_type: str, resource_id: str) -> ModelAlias | None:
        row = (
            await self._session.execute(
                select(
                    ResourceRow.model_alias_id,
                    ResourceRow.alias,
                    ResourceRow.concrete_model,
                    ResourceRow.router,
                    ResourceRow.inference_provider,
                    ResourceRow.status,
                ).where(
                    ResourceRow.resource_type == resource_type,
                    ResourceRow.resource_id == resource_id,
                    ResourceRow.resource_type == "llm_model",
                    ResourceRow.status == "active",
                )
            )
        ).one_or_none()
        return project_model_alias(row._mapping) if row is not None else None


@dataclass(frozen=True, slots=True)
class ResourceAuthorizationView:
    resource_type: str
    resource_id: str
    status: str


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
        if event.latency_ms is None:
            raise ValueError("latency_ms is required for persistence")
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
