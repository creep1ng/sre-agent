"""The resource types the grants name, what each one means, and the catalog's vocabulary.

Every other copy derives from here: the grant and catalog tables below, the catalog module, the
catalog repository and the database CHECKs; the release schemas publish the same values.
"""

from typing import TYPE_CHECKING, Literal, NamedTuple, get_args

ResourceType = Literal[
    "llm_model",
    "mcp_server",
    "mcp_tool",
    "skill",
    "bok_collection",
    "administrative_control",
    # Approved extension (agent/api/authorization.v1.yaml): the incident workflow
    # is the stable grantable resource for run-scoped incident actions. Grants over
    # this type are contracted but not seeded; evaluation denies by default.
    "incident_workflow",
    # What mitigation.execute grants are over (#722): `{service}:{operation}` of an operation
    # the deploy-executor enrols (schemas/executor/1.0.0/deploy-executor.yaml, `governance`).
    "service_operation",
]


class ResourceKind(NamedTuple):
    """What a resource type means: the grant actions admitted over it and, for a type of the
    catalog, the source that owns its entries and the states an entry of it may be in."""

    actions: frozenset[str]
    source: str | None = None
    states: tuple[str, ...] = ()


# The one table of the resource types. `ResourceType` names them once more, because the type
# checker and the published enum need a static `Literal`; `_require_same` below keeps both equal.
# The catalog's vocabulary (types, owning sources, states) and the database CHECKs derive from it;
# the release schemas publish the same values.
#
# Admitted grant actions per resource contract (#423 CA3). Exact membership in
# the per-type sets below: the resource-catalog owner/state/action matrix
# (schemas/releases/*/conformance/resource-catalog-matrix.yaml) plus the
# vocabularies the runtime actually evaluates: bare "invoke" on skill
# (gateway/skills.py) alongside skill.invoke, admin.read/admin.write over
# administrative_control (CONTROL_SCOPES), and the run.*, alert.*,
# incident.declare and change.* (#770) actions over incident_workflow
# (agent/api/authorization.v1.yaml and agent/api/triage.openapi.yaml). Dotted refinements such
# as "invoke.delete" or "run.start.unpublished" are absent from those closed contracts and the
# engine matches grant.action exactly, so they are rejected without mutation.
# This is a pure lookup: it never touches a repository, so a denied caller
# still receives 403 before any target access.
# mitigation.execute over service_operation comes from the `governance` block of
# schemas/executor/1.0.0/deploy-executor.yaml (#722).
RESOURCE_KINDS: dict[str, ResourceKind] = {
    "llm_model": ResourceKind(
        frozenset({"admin.read", "admin.write", "invoke"}), "model_alias", ("active", "inactive")
    ),
    "mcp_server": ResourceKind(
        frozenset({"admin.write", "mcp.discovery", "mcp.invoke"}),
        "mcp",
        ("registered", "active", "inactive", "revoked"),
    ),
    "mcp_tool": ResourceKind(
        frozenset({"admin.write", "mcp.discovery", "mcp.invoke"}),
        "mcp",
        ("registered", "active", "inactive", "revoked"),
    ),
    "skill": ResourceKind(
        frozenset({"admin.write", "skill.discovery", "skill.read", "skill.invoke", "invoke"}),
        "skill",
        ("draft", "published", "active", "inactive", "revoked"),
    ),
    "bok_collection": ResourceKind(
        frozenset({"admin.write", "bok.discovery", "bok.search", "bok.read"}),
        "bok",
        ("draft", "indexing", "active", "inactive", "revoked"),
    ),
    "administrative_control": ResourceKind(frozenset({"admin.read", "admin.write"})),
    "incident_workflow": ResourceKind(
        frozenset(
            {
                "run.start",
                "run.read",
                "run.command",
                "run.approve",
                "run.read_context",
                "alert.read",
                "alert.triage",
                "alert.dismiss",
                "alert.associate",
                "incident.declare",
                "change.read",
                "change.write",
            }
        ),
        "incident_workflow",
        ("active", "inactive"),
    ),
    "service_operation": ResourceKind(
        frozenset({"mitigation.execute"}), "deploy_executor", ("active", "inactive")
    ),
}


def _require_same(
    name: str, declared: tuple[str, ...], derived: tuple[str, ...], *, ordered: bool = False
) -> None:
    """Fail at import, naming what differs, when a static `Literal` and `RESOURCE_KINDS` drift
    apart; `ordered` also requires the same order, which the CHECK texts and enums follow."""
    missing, extra = set(derived) - set(declared), set(declared) - set(derived)
    if missing or extra:
        raise RuntimeError(
            f"{name} differs from RESOURCE_KINDS: it lacks {sorted(missing)} "
            f"and adds {sorted(extra)}"
        )
    if ordered and declared != derived:
        raise RuntimeError(
            f"{name} lists the RESOURCE_KINDS values in another order: {declared} against {derived}"
        )


_require_same("ResourceType", get_args(ResourceType), tuple(RESOURCE_KINDS), ordered=True)
GRANT_ADMITTED_ACTIONS: dict[str, frozenset[str]] = {
    kind: facts.actions for kind, facts in RESOURCE_KINDS.items()
}

# The sources and states `RESOURCE_KINDS` gives the catalog types, spelled again as the static
# `Literal`s the type checker reads; the published enums and the CHECKs keep this order, which
# the table's per-type tuples do not give for the states. `_require_same` ties both to the table.
CatalogSource = Literal[
    "model_alias", "mcp", "skill", "bok", "incident_workflow", "deploy_executor"
]
CatalogStatus = Literal[
    "registered", "draft", "published", "indexing", "active", "inactive", "revoked"
]
CatalogVisibility = Literal["public", "private", "hidden"]
# The catalog's vocabulary: the resource types that have a catalog source, the source that owns
# each and the states an entry of it may be in, all from `RESOURCE_KINDS`.
CATALOG_SOURCE: dict[str, str] = {
    kind: facts.source for kind, facts in RESOURCE_KINDS.items() if facts.source is not None
}
CATALOG_TYPES: tuple[str, ...] = tuple(CATALOG_SOURCE)
CATALOG_STATES: dict[str, tuple[str, ...]] = {
    kind: RESOURCE_KINDS[kind].states for kind in CATALOG_TYPES
}
CATALOG_STATUSES: tuple[str, ...] = get_args(CatalogStatus)
_require_same("CatalogSource", get_args(CatalogSource), tuple(CATALOG_SOURCE.values()))
_require_same(
    "CatalogStatus",
    CATALOG_STATUSES,
    tuple(state for states in CATALOG_STATES.values() for state in states),
)
CATALOG_VISIBILITIES: tuple[str, ...] = get_args(CatalogVisibility)
if TYPE_CHECKING:
    # A static subset of ResourceType would spell the types again; the checker gets the superset.
    CatalogResourceType = ResourceType
else:
    CatalogResourceType = Literal[CATALOG_TYPES]
