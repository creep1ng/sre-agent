"""Authorized, bounded PostgreSQL retrieval over BoK owner chunks."""

from collections import Counter
from datetime import UTC, datetime
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Path, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.bok.jev import JEV_MODEL, MAX_JEV_CANDIDATES, JevEvaluator
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
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
    evaluation_mode: Literal["off", "shadow"] = "off"


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
    ) -> bool:
        """Hold exact active authorization facts stable through the content query."""
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
        return bool(
            principal is not None
            and principal.status == "active"
            and credential is not None
            and credential.status == "active"
            and (credential.expires_at is None or credential.expires_at > now)
            and resource is not None
            and resource.status == "active"
            and grant is not None
        )

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


class BoKRetrievalService:
    """Authenticate and authorize exact collection versions before content access."""

    def __init__(
        self,
        sessions: Any,
        audit: AuditStore,
        projector: AuditProjector,
        *,
        jev_enabled: bool = False,
        jev_evaluator: JevEvaluator | None = None,
    ) -> None:
        self.sessions = sessions
        self.audit = audit
        self.projector = projector
        self.jev_enabled = jev_enabled
        self.jev_evaluator = jev_evaluator
        # In-memory non-content instrumentation; keys are exact resource IDs.
        self.content_reads_by_collection: Counter[str] = Counter()

    async def search(
        self,
        collection_id: str,
        version: str,
        body: BoKSearchRequest,
        authorization: str | None,
    ) -> JSONResponse:
        return await self._retrieve(
            collection_id,
            version,
            authorization,
            action="bok.search",
            read_operation=False,
            query=body.query,
            evaluation_mode=body.evaluation_mode,
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
    ) -> JSONResponse:
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
        query: str | None = None,
        evaluation_mode: str = "off",
    ) -> JSONResponse:
        request_id = uuid4()
        started = monotonic()
        resource_id = f"{collection_id}@{version}"
        operation = "bok.read" if read_operation else "bok.search"
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, action, "bok_collection", resource_id
            )
        except AuthenticationFailed:
            return JSONResponse(
                {
                    "error": {"code": "authentication_failed", "message": "Authentication failed."},
                    "request_id": str(request_id),
                    "retryable": False,
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if evaluation.decision.decision != "allow":
            return await self._finish(
                request_id,
                started,
                403,
                "resource_unavailable",
                operation,
                "authorization",
                context,
                evaluation,
                resource_id,
            )

        try:
            async with self.sessions() as session, session.begin():
                repository = BoKOwnerRepository(session)
                if not await repository.lock_current_authority(context, action, resource_id):
                    denied_evaluation = AuthorizationEvaluation(
                        PolicyDecision(
                            decision="deny", reason_code="no_matching_grant", policy_id=None
                        ),
                        AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
                    )
                    return await self._finish(
                        request_id,
                        started,
                        403,
                        "resource_unavailable",
                        operation,
                        "authorization",
                        context,
                        denied_evaluation,
                        resource_id,
                    )
                if not await repository.lock_active_version(collection_id, version):
                    return await self._finish(
                        request_id,
                        started,
                        503,
                        "index_unavailable",
                        operation,
                        "response",
                        context,
                        evaluation,
                        resource_id,
                    )
                # Count content-repository operations (including authorized no-match searches).
                self.content_reads_by_collection[resource_id] += 1
                result = await content_query(repository)
        except SQLAlchemyError:
            return await self._finish(
                request_id,
                started,
                503,
                "storage_unavailable",
                operation,
                "upstream",
                context,
                evaluation,
                resource_id,
            )
        if read_operation and result is None:
            return await self._finish(
                request_id,
                started,
                404,
                "resource_not_found",
                operation,
                "response",
                context,
                evaluation,
                resource_id,
            )
        payload = {"results": result} if not read_operation else result
        if not read_operation and evaluation_mode == "shadow":
            payload["evaluation"] = await self._evaluate_shadow(query or "", result)
        return await self._finish(
            request_id,
            started,
            200,
            None,
            operation,
            "response",
            context,
            evaluation,
            resource_id,
            payload=payload,
        )

    async def _evaluate_shadow(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not self.jev_enabled or self.jev_evaluator is None:
            return {"mode": "shadow", "status": "disabled"}
        if not candidates:
            return {"mode": "shadow", "status": "no_candidates"}
        if any(
            not str(candidate.get("source_ref", "")).startswith("synthetic://")
            for candidate in candidates
        ):
            return {"mode": "shadow", "status": "ineligible_source"}

        evaluated_candidates = candidates[:MAX_JEV_CANDIDATES]
        try:
            result = await self.jev_evaluator.evaluate(query, evaluated_candidates)
            scores = result.scores
            if (
                result.model != JEV_MODEL
                or len(scores) != len(evaluated_candidates)
                or any(
                    isinstance(score, bool)
                    or not isinstance(score, float | int)
                    or not 0 <= score <= 1
                    for score in scores
                )
                or result.input_tokens < 0
                or result.output_tokens < 0
                or result.latency_ms < 0
            ):
                raise ValueError("evaluator result did not match the Jev contract")
        except Exception:
            # Preserve lexical results without propagating provider details or text.
            return {
                "mode": "shadow",
                "status": "fallback",
                "reason": "evaluator_unavailable",
            }
        return {
            "mode": "shadow",
            "status": "evaluated",
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "omitted_candidate_count": len(candidates) - len(evaluated_candidates),
            "scores": [
                {
                    "document_id": candidate["document_id"],
                    "section_id": candidate["section_id"],
                    "chunk_index": candidate["chunk_index"],
                    "score": float(score),
                }
                for candidate, score in zip(evaluated_candidates, scores, strict=True)
            ],
        }

    async def _finish(
        self,
        request_id: UUID,
        started: float,
        status: int,
        reason: str | None,
        operation: str,
        stage: str,
        context: PrincipalContext | None,
        evaluation: AuthorizationEvaluation | None,
        resource_id: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> JSONResponse:
        response = (
            JSONResponse(payload, status_code=status)
            if payload is not None
            else JSONResponse(
                {
                    "error": {
                        "code": reason or "resource_unavailable",
                        "message": (
                            (reason or "resource_unavailable").replace("_", " ").capitalize() + "."
                        ),
                    },
                    "request_id": str(request_id),
                    "retryable": status >= 500,
                },
                status_code=status,
            )
        )
        try:
            event = self.projector.control_event(
                request_id,
                status,
                max(0, int((monotonic() - started) * 1000)),
                stage,
                operation=operation,
                action="read_metadata",
                reason=reason,
                retryable=status >= 500,
                context=context,
                resource_ref=("bok_collection", resource_id),
                decision=evaluation.decision if evaluation else None,
                authorization_denial_cause=evaluation.denial_cause if evaluation else None,
            )
            await self.audit.append(event)
        except Exception:
            return JSONResponse(
                {
                    "error": {"code": "audit_unavailable", "message": "Audit unavailable."},
                    "request_id": str(request_id),
                    "retryable": True,
                },
                status_code=503,
            )
        return response


def bok_router(service: BoKRetrievalService) -> APIRouter:
    router = APIRouter()
    bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")
    collection_id_param = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    version_param = Path(pattern=r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$")

    @router.post(
        "/v1/bok/collections/{collection_id}/versions/{version}/search",
        responses={
            401: {"description": "Authentication failed."},
            403: {"description": "Collection version unavailable."},
            503: {"description": "Collection index or storage unavailable."},
        },
        openapi_extra={
            "x-governed-scope": {
                "action": "bok.search",
                "resource_type": "bok_collection",
                "resource_id": "path.collection_id@version",
            }
        },
    )
    async def search(
        body: Annotated[BoKSearchRequest, Body()],
        bearer_credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
        collection_id: str = collection_id_param,
        version: str = version_param,
    ) -> JSONResponse:
        return await service.search(
            collection_id,
            version,
            body,
            f"Bearer {bearer_credentials.credentials}" if bearer_credentials else None,
        )

    @router.get(
        "/v1/bok/collections/{collection_id}/versions/{version}/chunks/"
        "{document_id}/{section_id}/{chunk_index}",
        responses={
            401: {"description": "Authentication failed."},
            403: {"description": "Collection version unavailable."},
            404: {"description": "Chunk unavailable."},
            503: {"description": "Collection index or storage unavailable."},
        },
        openapi_extra={
            "x-governed-scope": {
                "action": "bok.read",
                "resource_type": "bok_collection",
                "resource_id": "path.collection_id@version",
            }
        },
    )
    async def read_chunk(
        bearer_credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
        collection_id: str = collection_id_param,
        version: str = version_param,
        document_id: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$"),
        section_id: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$"),
        chunk_index: int = Path(ge=0, le=1_000_000),
    ) -> JSONResponse:
        return await service.read_chunk(
            collection_id,
            version,
            document_id,
            section_id,
            chunk_index,
            f"Bearer {bearer_credentials.credentials}" if bearer_credentials else None,
        )

    return router
