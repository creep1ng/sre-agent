"""Typed interface for the versioned native core boundary."""

from typing import Any, Literal

API_VERSION: Literal[1]

def audit_reference_digest(key: bytes, domain: str, value: str) -> str: ...

type ResourceFact = tuple[str, str, str]
type GrantFact = tuple[str, str, str, str, str, str, str]

def evaluate_authorization(
    principal_status: str,
    principal_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    resource: ResourceFact | None,
    grant: GrantFact | None,
) -> tuple[bool, Literal["grant_matched", "no_matching_grant"], str | None, str | None]: ...
def admit_incident_transition(
    state: object, command: object, transition: object
) -> tuple[
    Literal[
        "accepted",
        "source_mismatch",
        "actor_forbidden",
        "human_reference_missing",
        "actor_reference_invalid",
        "approval_required",
        "outcome_required",
    ],
    object | None,
]: ...
def map_provider_failure(kind: object) -> tuple[int, str, str]: ...
def completed_openrouter_output_text(body: object) -> str | None: ...
def project_openrouter_consumption(
    state: Literal["missing", "invalid", "mapping"],
    nonempty: bool,
    input: tuple[str | None, bool, bool],
    output: tuple[str | None, bool, bool],
    total: tuple[str | None, bool, bool],
    cost: tuple[str | None, bool, bool],
    timestamp_valid: bool,
    failure_context: bool = False,
) -> tuple[str, str | None, str | None, str | None, str | None, bool]: ...
def inspect_provider_response(
    body: object, request_model: str, request_provider: str
) -> tuple[Literal["accept", "reject", "catalog_required"], str | None]: ...
def confirm_provider_catalog(
    body: object, selected_model: str, request_model: str, request_provider: str
) -> bool: ...
def project_responses_audit(
    status: int,
    reason: str | None,
    context: tuple[str, str, str, str] | None,
    alias: str | None,
    decision: tuple[str, str, str | None] | None,
    assignment: tuple[str, str] | None,
    identifiers: list[tuple[str, str]],
) -> dict[str, Any]: ...
def project_control_audit(
    status: int,
    stage: str,
    reason: str | None,
    terminal: bool,
    retryable: bool,
    context: object | None,
    resource: object | None,
    decision: object | None,
    authorization_denial_cause: object | None,
) -> dict[str, Any]: ...
