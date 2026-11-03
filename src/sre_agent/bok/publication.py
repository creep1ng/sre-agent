"""Publish and read BoK collection versions on behalf of a human author.

The administrative route and any later caller (a person accepting a proposed entry) share this
path. Callers own the transaction, the authorization and the audit event; this module owns the
closed body, the author rule and the owner/catalog writes.
"""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.bok.owner import publish_bundle
from sre_agent.governance.dto import Principal
from sre_agent.persistence.models import (
    BoKCollectionVersionRow,
    BoKDocumentRow,
    BoKSectionChunkRow,
)

BOK_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,99}$"
SEMVER_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
ORIGIN_PATTERN = r"^[a-z][a-z0-9-]{1,31}(:[A-Za-z0-9._-]{1,64})?$"
BOK_OWNER_ID = "bok-platform"
MAX_DOCUMENTS, MAX_CHUNKS = 20, 50


class BoKAuthorRefused(PermissionError):
    """Only an active human publishes; an agent proposes and a person accepts."""


class BoKChunkPublish(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    section_id: Annotated[str, Field(pattern=BOK_SLUG_PATTERN)]
    chunk_index: Annotated[int, Field(ge=0, le=MAX_CHUNKS - 1)]
    content: Annotated[str, Field(min_length=1, max_length=4000)]


class BoKDocumentPublish(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    document_id: Annotated[str, Field(pattern=BOK_SLUG_PATTERN)]
    title: Annotated[str, Field(min_length=1, max_length=300)]
    source_ref: Annotated[str, Field(min_length=1, max_length=500)]
    chunks: Annotated[list[BoKChunkPublish], Field(min_length=1, max_length=MAX_CHUNKS)]


class BoKPublishRequest(BaseModel):
    """Closed body for one immutable version; the owner and visibility are server-side."""

    model_config = ConfigDict(strict=True, extra="forbid")
    collection_id: Annotated[str, Field(pattern=BOK_SLUG_PATTERN)]
    version: Annotated[str, Field(max_length=32, pattern=SEMVER_PATTERN)]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=500)]
    documents: Annotated[list[BoKDocumentPublish], Field(min_length=1, max_length=MAX_DOCUMENTS)]

    @model_validator(mode="after")
    def version_is_complete(self) -> "BoKPublishRequest":
        # Duplicate keys would surface as a storage conflict and blank chunks leave the
        # version unready; both are invalid bodies.
        documents = [document.document_id for document in self.documents]
        if len(set(documents)) != len(documents):
            raise ValueError("Document IDs must be unique")
        for document in self.documents:
            chunks = [(chunk.section_id, chunk.chunk_index) for chunk in document.chunks]
            if len(set(chunks)) != len(chunks):
                raise ValueError("Chunk keys must be unique within a document")
            if any(not chunk.content.strip() for chunk in document.chunks):
                raise ValueError("Chunk content must not be blank")
        return self


class BoKVersionSummary(BaseModel):
    resource_id: str
    collection_id: str
    version: str
    owner_id: str
    display_name: str
    description: str
    visibility: str
    status: str
    document_count: int
    chunk_count: int


class BoKVersionRecord(BoKVersionSummary):
    documents: list[BoKDocumentPublish]


async def publish_bok_version(
    session: AsyncSession, request: BoKPublishRequest, *, author: Principal, origin: str
) -> tuple[BoKVersionSummary, bool]:
    """Ingest, activate and project one version inside the caller's transaction.

    Returns the summary and whether anything was written. Raises BoKAuthorRefused for an agent
    or inactive author, ValueError for a malformed origin (``console``, ``proposal:<id>``) and
    BoKVersionCollision when the version or its catalog entry already holds different content.
    """
    if author.kind != "human" or author.status != "active":
        raise BoKAuthorRefused("bok_author_not_active_human")
    if re.fullmatch(ORIGIN_PATTERN, origin) is None:
        raise ValueError("bok_origin_invalid")
    bundle = {**request.model_dump(mode="json"), "owner_id": BOK_OWNER_ID, "visibility": "private"}
    created = await publish_bundle(session, bundle, ["bok"])
    summary = BoKVersionSummary(
        resource_id=f"{request.collection_id}@{request.version}",
        collection_id=request.collection_id,
        version=request.version,
        owner_id=BOK_OWNER_ID,
        display_name=request.display_name,
        description=request.description,
        visibility="private",
        status="active",
        document_count=len(request.documents),
        chunk_count=sum(len(document.chunks) for document in request.documents),
    )
    return summary, created


async def read_bok_version(
    session: AsyncSession, collection_id: str, version: str
) -> BoKVersionRecord | None:
    """Return the owner's view of one version, bounded by the publication limits."""
    row = await session.get(BoKCollectionVersionRow, (collection_id, version))
    if row is None:
        return None
    in_version = {"collection_id": collection_id, "version": version}
    documents = (
        await session.scalars(
            select(BoKDocumentRow)
            .filter_by(**in_version)
            .order_by(BoKDocumentRow.document_id)
            .limit(MAX_DOCUMENTS)
        )
    ).all()
    chunks = (
        await session.scalars(
            select(BoKSectionChunkRow)
            .filter_by(**in_version)
            .order_by(
                BoKSectionChunkRow.document_id,
                BoKSectionChunkRow.section_id,
                BoKSectionChunkRow.chunk_index,
            )
            .limit(MAX_DOCUMENTS * MAX_CHUNKS)
        )
    ).all()
    published = [
        BoKDocumentPublish.model_construct(
            document_id=document.document_id,
            title=document.title,
            source_ref=document.source_ref,
            chunks=[
                BoKChunkPublish.model_construct(
                    section_id=chunk.section_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                )
                for chunk in chunks
                if chunk.document_id == document.document_id
            ][:MAX_CHUNKS],
        )
        for document in documents
    ]
    return BoKVersionRecord(
        resource_id=f"{collection_id}@{version}",
        collection_id=collection_id,
        version=version,
        owner_id=row.owner_id,
        display_name=row.display_name,
        description=row.description,
        visibility=row.visibility,
        status=row.status,
        document_count=len(published),
        chunk_count=sum(len(document.chunks) for document in published),
        documents=published,
    )
