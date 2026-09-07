"""Narrow async persistence ports for governance reads and audit appends."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.governance.authorization import ResourceAuthorizationFact
from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    ModelAlias,
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
    IdempotencyRecordRow,
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

    async def create(
        self,
        principal_id: str,
        kind: str,
        display_name: str,
        *,
        now: datetime | None = None,
    ) -> Principal:
        issued_at = now or datetime.now(UTC)
        row = PrincipalRow(
            principal_id=principal_id,
            kind=kind,
            display_name=display_name,
            status="active",
            created_at=issued_at,
            updated_at=issued_at,
        )
        self._session.add(row)
        await self._session.flush()
        return project_principal(row)

    async def list(self, *, limit: int) -> tuple[list[Principal], bool]:
        rows = (
            await self._session.scalars(
                select(PrincipalRow)
                .order_by(PrincipalRow.created_at.asc(), PrincipalRow.principal_id.asc())
                .limit(limit + 1)
            )
        ).all()
        truncated = len(rows) > limit
        return [project_principal(row) for row in rows[:limit]], truncated

    async def replace_status(
        self,
        principal_id: str,
        status: str,
        *,
        expected_updated_at: datetime,
        now: datetime | None = None,
    ) -> Principal | None:
        """Deterministic status replace guarded by optimistic concurrency.

        Returns ``None`` when the principal is absent; raises ``StaleWriteError``
        when ``expected_updated_at`` no longer matches the stored row.
        """
        row = await self._session.get(PrincipalRow, principal_id)
        if row is None:
            return None
        if row.updated_at != expected_updated_at:
            raise StaleWriteError(principal_id)
        row.status = status
        row.updated_at = now or datetime.now(UTC)
        await self._session.flush()
        return project_principal(row)


class StaleWriteError(RuntimeError):
    """An optimistic-concurrency guard rejected a stale status replace."""

    def __init__(self, principal_id: str) -> None:
        super().__init__(f"status_conflict: {principal_id}")
        self.principal_id = principal_id


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
        context = await self.resolve_authorization_context(key, now=now)
        if context is None or context.principal.status != "active":
            return None
        return context

    async def resolve_authorization_context(
        self, key: str, *, now: datetime | None = None
    ) -> PrincipalContext | None:
        """Resolve a valid credential while preserving Principal status for authorization."""
        authenticated_at = now or datetime.now(UTC)
        matches = await self._session.execute(
            select(CredentialRow, PrincipalRow)
            .join(PrincipalRow, PrincipalRow.principal_id == CredentialRow.principal_id)
            .where(CredentialRow.prefix.in_(candidate_prefixes(key)))
        )
        for credential, principal in matches:
            if (
                credential.status == "active"
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

    async def list_for_principal(
        self, principal_id: str, *, limit: int
    ) -> tuple[list[CredentialReference], bool]:
        """Metadata-only credential list ordered by (created_at, id) descending."""
        rows = (
            await self._session.scalars(
                select(CredentialRow)
                .where(CredentialRow.principal_id == principal_id)
                .order_by(CredentialRow.created_at.desc(), CredentialRow.credential_id.desc())
                .limit(limit + 1)
            )
        ).all()
        truncated = len(rows) > limit
        return [project_credential(row) for row in rows[:limit]], truncated

    async def rotate(
        self,
        credential_id: str,
        *,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> IssuedAPIKey | None:
        """Atomically revoke one active credential and issue its replacement.

        Returns ``None`` when the credential is absent; revocation converges
        (a revoked row stays revoked). Any issuance failure rolls the whole
        transaction back, leaving the old credential active.
        """
        row = await self._session.get(CredentialRow, credential_id)
        if row is None:
            return None
        revoked_at = now or datetime.now(UTC)
        if row.status == "active":
            row.status = "revoked"
            row.revoked_at = revoked_at
            await self._session.flush()
        replaced_credential_id: str | None = row.credential_id
        issued = await self.issue(row.principal_id, expires_at=expires_at, now=revoked_at)
        return IssuedAPIKey(
            credential=issued.credential,
            key=issued.key,
            replaced_credential_id=replaced_credential_id,  # type: ignore[typeddict-item]
            secret_revealed=True,
        )


@dataclass(frozen=True, slots=True)
class IdempotencyOutcome:
    response_status: int
    resource_id: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class IdempotencyBinding:
    outcome: IdempotencyOutcome
    replayed: bool


class IdempotencyConflictError(RuntimeError):
    """The retained key binding conflicts with the request payload hash."""

    def __init__(self, scope: str) -> None:
        super().__init__(f"idempotency_conflict: {scope}")
        self.scope = scope


class IdempotencyRepository:
    """Scoped POST bindings: same hash replays, other hash conflicts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_or_replay(
        self,
        *,
        scope: str,
        key_digest: str,
        payload_sha256: str,
        principal_id: str,
        method: str,
        canonical_path: str,
        binding: str,
        outcome: IdempotencyOutcome,
        now: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> IdempotencyBinding:
        created_at = now or datetime.now(UTC)
        row = await self._session.get(IdempotencyRecordRow, (scope, key_digest))
        if row is None:
            self._session.add(
                IdempotencyRecordRow(
                    scope=scope,
                    key_digest=key_digest,
                    payload_sha256=payload_sha256,
                    principal_id=principal_id,
                    method=method,
                    canonical_path=canonical_path,
                    binding=binding,
                    outcome={
                        "response_status": outcome.response_status,
                        "resource_id": outcome.resource_id,
                        "replayed": False,
                    },
                    created_at=created_at,
                    expires_at=expires_at,
                    transition_count=1,
                )
            )
            await self._session.flush()
            return IdempotencyBinding(outcome=outcome, replayed=False)
        if row.payload_sha256 != payload_sha256:
            raise IdempotencyConflictError(scope)
        stored = row.outcome
        return IdempotencyBinding(
            outcome=IdempotencyOutcome(
                response_status=stored["response_status"],
                resource_id=stored["resource_id"],
                replayed=True,
            ),
            replayed=True,
        )


class ResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authorization_view(
        self, resource_type: str, resource_id: str
    ) -> ResourceAuthorizationFact | None:
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
        return ResourceAuthorizationFact(*row)

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
