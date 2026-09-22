"""Explicit safe projections from persistence rows to HT-01 DTOs."""

import json
from collections.abc import Mapping
from functools import partial
from typing import Any

from sre_agent.governance.dto import (
    AuditEvent,
    CredentialReference,
    Grant,
    ModelAlias,
    PolicyDecision,
    Principal,
    Resource,
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


def project_audit_event(row: Mapping[str, Any] | object) -> AuditEvent:
    if isinstance(row, Mapping):
        values = {field: row[field] for field in AuditEvent.model_fields if field in row}
    else:
        values = {
            field: getattr(row, field) for field in AuditEvent.model_fields if hasattr(row, field)
        }
    return AuditEvent.model_validate_json(json.dumps(values, default=str))
