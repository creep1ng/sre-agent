"""Closed response models and projection for bounded historical request reads."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select


async def read_requests(projection: Any, **selectors: Any) -> dict[str, Any]:
    """Read request snapshots alongside the shared bounded usage evidence."""
    from sre_agent.persistence.models import RequestAttributionRow

    rows, selected_filter, _incident_ref = await projection.select_evidence(**selectors)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["request_id"]), []).append(row)
    reconciled = projection._reconcile_requests(grouped)

    # Execute the table query even for an empty audit selection. An unavailable
    # snapshot store must not be disguised as an empty legacy result.
    async with projection._sessions() as session:
        snapshot_rows = (
            (
                await session.execute(
                    select(
                        RequestAttributionRow.request_id,
                        RequestAttributionRow.audit_event_id,
                        RequestAttributionRow.requested_alias,
                        RequestAttributionRow.requested_model,
                        RequestAttributionRow.requested_provider,
                        RequestAttributionRow.requested_router,
                        RequestAttributionRow.credited_model,
                        RequestAttributionRow.credited_provider,
                    ).where(RequestAttributionRow.request_id.in_(list(grouped)))
                )
            )
            .mappings()
            .all()
        )
    snapshots: dict[str, RequestAttributionEvidence] = {}
    for row in snapshot_rows:
        snapshot = RequestAttributionEvidence.model_validate_json(json.dumps(dict(row)))
        key = str(snapshot.request_id)
        if key in snapshots:
            raise ValueError("multiple persisted request attribution snapshots")
        snapshots[key] = snapshot
    return project_items(selected_filter, rows, reconciled, snapshots)


class RequestAttributionEvidence(BaseModel):
    """Validate raw persisted routing identifiers before exposing them."""

    model_config = ConfigDict(strict=True, extra="forbid")

    request_id: UUID
    audit_event_id: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"),
    ]
    requested_alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$", max_length=64)]
    requested_model: Annotated[
        str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$", max_length=200)
    ]
    requested_provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9._-]{0,63}$", max_length=64)]
    requested_router: Annotated[str, Field(min_length=1, max_length=64)]
    credited_model: (
        Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$", max_length=200)] | None
    )
    credited_provider: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9._-]{0,63}$", max_length=64)] | None
    )


def project_items(
    selected_filter: dict[str, str],
    rows: list[dict[str, Any]],
    reconciled: dict[str, dict[str, Any]],
    snapshots: dict[str, RequestAttributionEvidence],
) -> dict[str, Any]:
    """Build request items from selected audit evidence and immutable snapshots."""
    events_by_request: dict[str, set[str]] = {}
    stages_by_event: dict[str, str] = {}
    stages_by_request: dict[str, set[str]] = {}
    for row in rows:
        request_key = str(row["request_id"])
        event_id, stage = str(row["event_id"]), str(row["stage"])
        events_by_request.setdefault(request_key, set()).add(event_id)
        stages_by_event[event_id] = stage
        stages_by_request.setdefault(request_key, set()).add(stage)

    items: list[dict[str, Any]] = []
    for request_key, evidence in reconciled.items():
        snapshot = snapshots.get(request_key)
        if snapshot is not None:
            linked_stage = stages_by_event.get(snapshot.audit_event_id)
            if snapshot.audit_event_id not in events_by_request[
                request_key
            ] or linked_stage not in {"response", "upstream"}:
                raise ValueError(
                    "persisted attribution is not linked to selected response evidence"
                )
        canonical_at = evidence["canonical_at"]
        consumption = evidence["consumption"] if evidence["consistent"] else None
        if snapshot is None:
            requested = {
                "availability": "unavailable",
                "alias": None,
                "model": None,
                "provider": None,
                "router": None,
            }
            credited_model = {"availability": "unavailable", "value": None}
            credited_provider = {"availability": "unavailable", "value": None}
            stages = stages_by_request[request_key]
            status = (
                "unavailable"
                if stages
                and stages.issubset(
                    {"validation", "authentication", "authorization", "routing", "audit"}
                )
                else "legacy"
            )
        else:
            requested = {
                "availability": "available",
                "alias": snapshot.requested_alias,
                "model": snapshot.requested_model,
                "provider": snapshot.requested_provider,
                "router": snapshot.requested_router,
            }
            credited_model = _credit(snapshot.credited_model)
            credited_provider = _credit(snapshot.credited_provider)
            status = (
                "available"
                if snapshot.credited_model is not None and snapshot.credited_provider is not None
                else "partial"
            )
        items.append(
            {
                "request_id": request_key,
                "month": canonical_at.astimezone(UTC).strftime("%Y-%m"),
                "requested_assignment": requested,
                "credited_model": credited_model,
                "credited_provider": credited_provider,
                "attribution_status": status,
                "consumption": consumption,
                "navigation": {"status": "unsupported"},
            }
        )
    return {"filter": selected_filter, "items": items}


def _credit(value: str | None) -> dict[str, str | None]:
    if value is None:
        return {"availability": "unavailable", "value": None}
    return {"availability": "available", "value": value}
