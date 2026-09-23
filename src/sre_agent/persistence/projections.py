"""Explicit safe projections from persistence rows to HT-01 DTOs."""

import json
from collections.abc import Mapping
from functools import partial
from typing import Any

from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    MCPServer,
    MCPTool,
    ModelAlias,
    PolicyDecision,
    Principal,
    Resource,
    ResourceCatalogEntry,
)


def _project(model: Any, row: Mapping[str, Any] | object) -> Any:
    if isinstance(row, Mapping):
        values = {field: row[field] for field in model.model_fields if field in row}
    else:
        values = {field: getattr(row, field) for field in model.model_fields if hasattr(row, field)}
    return model.model_validate(values)


project_principal = partial(_project, Principal)
project_credential = partial(_project, CredentialReference)
project_resource = partial(_project, Resource)
project_model_alias = partial(_project, ModelAlias)
project_grant = partial(_project, Grant)
project_policy_decision = partial(_project, PolicyDecision)
project_mcp_server = partial(_project, MCPServer)
project_mcp_tool = partial(_project, MCPTool)


def project_catalog_entry(row: Mapping[str, Any] | object) -> ResourceCatalogEntry:
    """Project a closed catalog entry without routing or secret leakage.

    ModelAlias owns concrete_model/router/provider; the catalog projection
    carries only owner/source/discoverability metadata.
    """
    if isinstance(row, Mapping):
        values = {
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "owner_id": row["owner_id"],
            "status": row["status"],
            "source": row["source"],
            "source_ref": row["source_ref"],
            "discoverability": {
                "display_name": row["display_name"],
                "visibility": row["visibility"],
                "description": row["description"] if row["description"] is not None else "",
                "tags": list(row["tags"]) if row["tags"] is not None else [],
            },
        }
    else:
        # ruff: noqa: B009 - explicit allow-listed projection, not dynamic access
        values = {
            "resource_type": row.resource_type,  # type: ignore[attr-defined]
            "resource_id": row.resource_id,  # type: ignore[attr-defined]
            "owner_id": row.owner_id,  # type: ignore[attr-defined]
            "status": row.status,  # type: ignore[attr-defined]
            "source": row.source,  # type: ignore[attr-defined]
            "source_ref": row.source_ref,  # type: ignore[attr-defined]
            "discoverability": {
                "display_name": row.display_name,  # type: ignore[attr-defined]
                "visibility": row.visibility,  # type: ignore[attr-defined]
                "description": row.description  # type: ignore[attr-defined]
                if row.description is not None  # type: ignore[attr-defined]
                else "",
                "tags": list(row.tags)  # type: ignore[attr-defined]
                if row.tags is not None  # type: ignore[attr-defined]
                else [],
            },
        }
    return ResourceCatalogEntry.model_validate(values)


def project_audit_event(row: Mapping[str, Any] | object) -> AuditEvent:
    if isinstance(row, Mapping):
        values = {field: row[field] for field in AuditEvent.model_fields if field in row}
    else:
        values = {
            field: getattr(row, field) for field in AuditEvent.model_fields if hasattr(row, field)
        }
    return AuditEvent.model_validate_json(json.dumps(values, default=str))
