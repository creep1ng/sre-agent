"""Authorized, bounded PostgreSQL retrieval over BoK owner chunks."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import (
    Admission,
    Gate,
    Refusals,
    Released,
    Scope,
    Terminal,
    declare,
    failing_as,
)
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import AuditStore
from sre_agent.governance.authorization import (
    AuthorizationDenialCause,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import PolicyDecision, PrincipalContext
from sre_agent.persistence.models import (
    BoKCollectionVersionRow,
    BoKDocumentRow,
    BoKSectionChunkRow,
    CredentialRow,
    GrantRow,
    PrincipalRow,
    ResourceRow,
)


class BoKSearchRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=20)


class BoKOwnerRepository:
    """Owner readiness and content queries, deliberately separate in call order."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_active_version(self, collection_id: str, version: str) -> bool:
        row = await self.session.scalar(
            select(BoKCollectionVersionRow)
            .where(
                BoKCollectionVersionRow.collection_id == collection_id,
                BoKCollectionVersionRow.version == version,
            )
            .with_for_update(read=True)
        )
        return row is not None and row.status == "active"

    async def lock_current_authority(
        self, context: PrincipalContext, action: str, resource_id: str
    ) -> AuthorizationDenialCause | None:
        """Hold exact authorization facts stable and report the first denial cause."""
        principal = await self.session.scalar(
            select(PrincipalRow)
            .where(PrincipalRow.principal_id == context.principal.principal_id)
            .with_for_update(read=True)
        )
        credential = await self.session.scalar(
            select(CredentialRow)
            .where(
                CredentialRow.credential_id == context.credential_id,
                CredentialRow.principal_id == context.principal.principal_id,
            )
            .with_for_update(read=True)
        )
        resource = await self.session.scalar(
            select(ResourceRow)
            .where(
                ResourceRow.resource_type == "bok_collection",
                ResourceRow.resource_id == resource_id,
            )
            .with_for_update(read=True)
        )
        grant = await self.session.scalar(
            select(GrantRow)
            .where(
                GrantRow.principal_id == context.principal.principal_id,
                GrantRow.action == action,
                GrantRow.resource_type == "bok_collection",
                GrantRow.resource_id == resource_id,
                GrantRow.effect == "allow",
                GrantRow.status == "active",
            )
            .with_for_update(read=True)
        )
        now = datetime.now(UTC)
        credential_is_current = bool(
            credential is not None
            and credential.status == "active"
            and (credential.expires_at is None or credential.expires_at > now)
        )
        if principal is None or principal.status != "active":
            return AuthorizationDenialCause.PRINCIPAL_INACTIVE
        if resource is None:
            return AuthorizationDenialCause.RESOURCE_MISSING
        if resource.status != "active":
            return AuthorizationDenialCause.RESOURCE_INACTIVE
        # Credentials retain their existing fail-closed behavior without expanding
        # the audit denial taxonomy; only the governed principal/resource/grant facts
        # participate in the shared authorization-cause precedence.
        if not credential_is_current or grant is None:
            return AuthorizationDenialCause.GRANT_NOT_APPLICABLE
        return None

    async def search(self, collection_id: str, version: str, query: str, limit: int):
        vector = func.to_tsvector("english", BoKSectionChunkRow.content)
        parsed_query = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(vector, parsed_query)
        rows = (
            await self.session.execute(
                select(
                    BoKSectionChunkRow.collection_id,
                    BoKSectionChunkRow.version,
                    BoKSectionChunkRow.document_id,
                    BoKSectionChunkRow.section_id,
                    BoKSectionChunkRow.chunk_index,
                    BoKSectionChunkRow.content,
                    BoKDocumentRow.title,
                    BoKDocumentRow.source_ref,
                    rank.label("rank"),
                )
                .join(
                    BoKDocumentRow,
                    (BoKDocumentRow.collection_id == BoKSectionChunkRow.collection_id)
                    & (BoKDocumentRow.version == BoKSectionChunkRow.version)
                    & (BoKDocumentRow.document_id == BoKSectionChunkRow.document_id),
                )
                .where(
                    BoKSectionChunkRow.collection_id == collection_id,
                    BoKSectionChunkRow.version == version,
                    vector.op("@@")(parsed_query),
                )
                .order_by(
                    desc(rank),
                    BoKSectionChunkRow.document_id,
                    BoKSectionChunkRow.section_id,
                    BoKSectionChunkRow.chunk_index,
                )
                .limit(limit)
            )
        ).all()
        return [
            {
                "collection_id": row.collection_id,
                "version": row.version,
                "document_id": row.document_id,
                "section_id": row.section_id,
                "chunk_index": row.chunk_index,
                "title": row.title,
                "source_ref": row.source_ref,
                "content": row.content,
                "score": float(row.rank),
            }
            for row in rows
        ]

    async def read_chunk(
        self,
        collection_id: str,
        version: str,
        document_id: str,
        section_id: str,
        chunk_index: int,
    ) -> dict[str, Any] | None:
        row = await self.session.execute(
            select(
                BoKSectionChunkRow.collection_id,
                BoKSectionChunkRow.version,
                BoKSectionChunkRow.document_id,
                BoKSectionChunkRow.section_id,
                BoKSectionChunkRow.chunk_index,
                BoKSectionChunkRow.content,
                BoKDocumentRow.title,
                BoKDocumentRow.source_ref,
            )
            .join(
                BoKDocumentRow,
                (BoKDocumentRow.collection_id == BoKSectionChunkRow.collection_id)
                & (BoKDocumentRow.version == BoKSectionChunkRow.version)
                & (BoKDocumentRow.document_id == BoKSectionChunkRow.document_id),
            )
            .where(
                BoKSectionChunkRow.collection_id == collection_id,
                BoKSectionChunkRow.version == version,
                BoKSectionChunkRow.document_id == document_id,
                BoKSectionChunkRow.section_id == section_id,
                BoKSectionChunkRow.chunk_index == chunk_index,
            )
        )
        value = row.one_or_none()
        if value is None:
            return None
        return {
            "collection_id": value.collection_id,
            "version": value.version,
            "document_id": value.document_id,
            "section_id": value.section_id,
            "chunk_index": value.chunk_index,
            "title": value.title,
            "source_ref": value.source_ref,
            "content": value.content,
        }


@dataclass(frozen=True)
class Retrieval:
    """One retrieval: its action names the audited operation."""

    action: str
    resource_id: str
    collection_id: str
    version: str

    @property
    def scope(self) -> Scope:
        return Scope(self.action, "bok_collection", self.resource_id)


REFUSALS = Refusals(
    denied=GovernedError(403, "resource_unavailable", stage="authorization"),
    unavailable=GovernedError(503, "storage_unavailable", retryable=True),
    unavailable_on=(SQLAlchemyError,),
    audit_unavailable=GovernedError(503, "audit_unavailable", "Audit unavailable.", retryable=True),
)
INDEX_UNAVAILABLE = GovernedError(503, "index_unavailable", retryable=True)
NOT_FOUND = GovernedError(404, "resource_not_found")


class BoKRetrievalService:
    """Authenticate and authorize exact collection versions before content access."""

    def __init__(
        self,
        sessions: Any,
        audit: AuditStore,
        projector: AuditProjector,
    ) -> None:
        self.sessions = sessions
        self.audit = audit
        self.projector = projector
        # In-memory non-content instrumentation; keys are exact resource IDs.
        self.content_reads_by_collection: Counter[str] = Counter()
        self.gate: Gate[Retrieval] = Gate(sessions, REFUSALS, audit=self._audit)

    async def search(
        self,
        collection_id: str,
        version: str,
        body: BoKSearchRequest,
        authorization: str | None,
    ) -> Response:
        return await self._retrieve(
            collection_id,
            version,
            authorization,
            action="bok.search",
            read_operation=False,
            content_query=lambda repository: repository.search(
                collection_id, version, body.query, body.limit
            ),
        )

    async def read_chunk(
        self,
        collection_id: str,
        version: str,
        document_id: str,
        section_id: str,
        chunk_index: int,
        authorization: str | None,
    ) -> Response:
        return await self._retrieve(
            collection_id,
            version,
            authorization,
            action="bok.read",
            read_operation=True,
            content_query=lambda repository: repository.read_chunk(
                collection_id, version, document_id, section_id, chunk_index
            ),
        )

    async def _retrieve(
        self,
        collection_id: str,
        version: str,
        authorization: str | None,
        *,
        action: str,
        read_operation: bool,
        content_query: Any,
    ) -> Response:
        retrieval = Retrieval(action, f"{collection_id}@{version}", collection_id, version)

        async def retrieve(admission: Admission, retrieval: Retrieval) -> Released:
            with failing_as(REFUSALS.unavailable, (SQLAlchemyError,)):
                async with self.sessions() as session, session.begin():
                    repository = BoKOwnerRepository(session)
                    denial_cause = await repository.lock_current_authority(
                        admission.context, action, retrieval.resource_id
                    )
                    if denial_cause is not None:
                        admission.facts["evaluation"] = AuthorizationEvaluation(
                            PolicyDecision(
                                decision="deny", reason_code="no_matching_grant", policy_id=None
                            ),
                            denial_cause,
                        )
                        raise REFUSALS.denied
                    if not await repository.lock_active_version(collection_id, version):
                        raise INDEX_UNAVAILABLE
                    # Count content-repository operations (including authorized no-match searches).
                    self.content_reads_by_collection[retrieval.resource_id] += 1
                    result = await content_query(repository)
            if read_operation and result is None:
                raise NOT_FOUND
            return Released({"results": result} if not read_operation else result)

        operation = SEARCH if action == "bok.search" else READ
        return await self.gate.run(
            operation, authorization, retrieval.scope, retrieve, validate=lambda: retrieval
        )

    async def _audit(self, terminal: Terminal) -> None:
        if terminal.status == 401 and not terminal.inactive:
            return  # A missing or unknown credential is not audited here; an inactive principal is.
        retrieval: Retrieval = terminal.request
        stage, context = terminal.stage, terminal.context
        evaluation = terminal.facts.get("evaluation", terminal.evaluation)
        if terminal.error is REFUSALS.unavailable:
            # Before an allow there is no subject to record; after it, storage is upstream.
            stage = "upstream" if stage == "response" else "authentication"
            context = context if stage == "upstream" else None
            evaluation = evaluation if stage == "upstream" else None
        event = self.projector.control_event(
            terminal.request_id,
            terminal.status,
            terminal.latency_ms,
            stage,
            operation=retrieval.action,
            action="read_metadata",
            reason=terminal.error.code if terminal.error is not None else None,
            retryable=terminal.status >= 500,
            context=context,
            resource_ref=("bok_collection", retrieval.resource_id) if context is not None else None,
            decision=evaluation.decision if evaluation else None,
            authorization_denial_cause=evaluation.denial_cause if evaluation else None,
        )
        await self.audit.append(event)


VERSION_PATH = "/v1/bok/collections/{collection_id}/versions/{version}"
SEARCH = declare(
    "POST",
    VERSION_PATH + "/search",
    action="bok.search",
    resource_type="bok_collection",
    resource_id="path.collection_id@version",
)
READ = declare(
    "GET",
    VERSION_PATH + "/chunks/{document_id}/{section_id}/{chunk_index}",
    action="bok.read",
    resource_type="bok_collection",
    resource_id="path.collection_id@version",
)


def bok_router(service: BoKRetrievalService) -> APIRouter:
    router = APIRouter()
    bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")
    collection_id_param = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    version_param = Path(pattern=r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$")

    @router.post(
        SEARCH.path,
        responses={
            401: {"description": "Authentication failed."},
            403: {"description": "Collection version unavailable."},
            503: {"description": "Collection index or storage unavailable."},
        },
        openapi_extra=SEARCH.openapi_extra,
    )
    async def search(
        body: Annotated[BoKSearchRequest, Body()],
        bearer_credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
        collection_id: str = collection_id_param,
        version: str = version_param,
    ) -> Response:
        return await service.search(
            collection_id,
            version,
            body,
            f"Bearer {bearer_credentials.credentials}" if bearer_credentials else None,
        )

    @router.get(
        READ.path,
        responses={
            401: {"description": "Authentication failed."},
            403: {"description": "Collection version unavailable."},
            404: {"description": "Chunk unavailable."},
            503: {"description": "Collection index or storage unavailable."},
        },
        openapi_extra=READ.openapi_extra,
    )
    async def read_chunk(
        bearer_credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
        collection_id: str = collection_id_param,
        version: str = version_param,
        document_id: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$"),
        section_id: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$"),
        chunk_index: int = Path(ge=0, le=1_000_000),
    ) -> Response:
        return await service.read_chunk(
            collection_id,
            version,
            document_id,
            section_id,
            chunk_index,
            f"Bearer {bearer_credentials.credentials}" if bearer_credentials else None,
        )

    return router
