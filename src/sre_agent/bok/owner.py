"""Owner-authoritative persistence for immutable BoK collection versions."""

import json
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.persistence.models import (
    BoKCollectionVersionRow,
    BoKDocumentRow,
    BoKSectionChunkRow,
    ResourceRow,
)


class BoKVersionCollision(RuntimeError):
    """A collection/version key already owns different immutable content."""


DEMO_BUNDLES: tuple[dict[str, Any], ...] = (
    {
        "collection_id": "demo-incident-response",
        "version": "1.0.0",
        "owner_id": "bok-platform",
        "display_name": "Incident Response Basics",
        "description": "Synthetic guidance for incident triage and response.",
        "visibility": "private",
        "documents": [
            {
                "document_id": "incident-triage",
                "title": "Incident triage",
                "source_ref": "synthetic://incident-response/triage",
                "chunks": [
                    {
                        "section_id": "severity",
                        "chunk_index": 0,
                        "content": "Assign severity from customer impact, scope, and active risk.",
                    }
                ],
            }
        ],
    },
    {
        "collection_id": "demo-platform-operations",
        "version": "1.0.0",
        "owner_id": "bok-platform",
        "display_name": "Platform Operations",
        "description": "Synthetic guidance for safe platform operations.",
        "visibility": "private",
        "documents": [
            {
                "document_id": "deployment-checks",
                "title": "Deployment checks",
                "source_ref": "synthetic://platform-operations/deployment-checks",
                "chunks": [
                    {
                        "section_id": "preflight",
                        "chunk_index": 0,
                        "content": "Verify health checks and rollback readiness before deployment.",
                    }
                ],
            }
        ],
    },
)


def _digest(bundle: dict[str, Any]) -> str:
    encoded = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


async def ingest_bundle(session: AsyncSession, bundle: dict[str, Any]) -> bool:
    """Insert a complete immutable version, or return False for an exact replay."""
    digest = _digest(bundle)
    collection_id = bundle["collection_id"]
    version = bundle["version"]
    existing = await session.get(BoKCollectionVersionRow, (collection_id, version))
    if existing is not None:
        if existing.manifest_sha256 != digest:
            raise BoKVersionCollision("collection_version_collision")
        return False

    documents = bundle["documents"]
    chunks = [chunk for document in documents for chunk in document["chunks"]]
    ready = bool(documents and chunks and all(chunk["content"].strip() for chunk in chunks))
    now = func.now()
    session.add(
        BoKCollectionVersionRow(
            collection_id=collection_id,
            version=version,
            owner_id=bundle["owner_id"],
            status="ready" if ready else "indexing",
            manifest_sha256=digest,
            display_name=bundle["display_name"],
            description=bundle["description"],
            visibility=bundle["visibility"],
            created_at=now,
            updated_at=now,
        )
    )
    for document in documents:
        content = "\n".join(chunk["content"] for chunk in document["chunks"])
        session.add(
            BoKDocumentRow(
                collection_id=collection_id,
                version=version,
                document_id=document["document_id"],
                title=document["title"],
                source_ref=document["source_ref"],
                content_sha256=sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        for chunk in document["chunks"]:
            session.add(
                BoKSectionChunkRow(
                    collection_id=collection_id,
                    version=version,
                    document_id=document["document_id"],
                    section_id=chunk["section_id"],
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                )
            )
    await session.flush()
    return True


async def activate_version(session: AsyncSession, collection_id: str, version: str) -> None:
    """Activate only a ready owner version; catalog status is not consulted."""
    row = await session.get(BoKCollectionVersionRow, (collection_id, version))
    if row is None or row.status not in {"ready", "active"}:
        raise ValueError("bok_version_not_ready")
    chunk_count = await session.scalar(
        select(func.count())
        .select_from(BoKSectionChunkRow)
        .where(
            BoKSectionChunkRow.collection_id == collection_id,
            BoKSectionChunkRow.version == version,
            func.length(func.trim(BoKSectionChunkRow.content)) > 0,
        )
    )
    if not chunk_count:
        raise ValueError("bok_version_not_ready")
    row.status = "active"
    row.updated_at = func.now()
    resource = await session.get(ResourceRow, ("bok_collection", f"{collection_id}@{version}"))
    if resource is not None:
        resource.status = "active"
    await session.flush()


async def seed_bok_demo(session: AsyncSession) -> bool:
    """Converge two deterministic synthetic BoK owner versions and projections."""
    created = False
    for bundle in DEMO_BUNDLES:
        collection_id, version = bundle["collection_id"], bundle["version"]
        created = await ingest_bundle(session, bundle) or created
        await activate_version(session, collection_id, version)
        resource_id = f"{collection_id}@{version}"
        resource = await session.get(ResourceRow, ("bok_collection", resource_id))
        expected = {
            "resource_type": "bok_collection",
            "resource_id": resource_id,
            "status": "active",
            "owner_id": bundle["owner_id"],
            "source": "bok",
            "source_ref": f"{collection_id}@{version}",
            "display_name": bundle["display_name"],
            "visibility": bundle["visibility"],
            "description": bundle["description"],
            "tags": ["demo", "bok"],
        }
        if resource is None:
            session.add(ResourceRow(**expected))
            created = True
        elif any(getattr(resource, key) != value for key, value in expected.items()):
            raise BoKVersionCollision("bok_catalog_projection_conflict")
    await session.flush()
    return created
