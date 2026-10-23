"""Enrolled services and the two named operations (contract schemas/executor/1.0.0)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

SERVICE_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"
# Docker's tag grammar: never a repository, a digest or a path.
TAG_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"


class RollbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    service: str = Field(pattern=SERVICE_PATTERN)
    to_tag: str = Field(pattern=TAG_PATTERN)


class RestartInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    service: str = Field(pattern=SERVICE_PATTERN)


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    input_model: type[BaseModel]
    parameters: tuple[str, ...]
    risk: Mapping[str, object]

    def describe(self) -> dict[str, Any]:
        return {
            "operation": self.name,
            "parameters": list(self.parameters),
            "risk": dict(self.risk),
        }


_RISK = {"touches_data": False, "blast_radius": "service", "downtime": "seconds"}
OPERATIONS: Mapping[str, Operation] = {
    "deployment.rollback": Operation(
        "deployment.rollback", RollbackInput, ("to_tag",), {"reversible": True, **_RISK}
    ),
    "deployment.restart": Operation(
        "deployment.restart", RestartInput, (), {"reversible": False, **_RISK}
    ),
}


class CatalogError(ValueError):
    """The catalog file does not describe services the executor can act on."""


@dataclass(frozen=True, slots=True)
class EnrolledService:
    service: str
    compose_service: str
    compose_project: str | None  # None: the executor's own Compose project
    image_repository: str | None
    operations: frozenset[str]

    def describe(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "image_repository": self.image_repository,
            "operations": [OPERATIONS[name].describe() for name in sorted(self.operations)],
        }


def load_catalog(path: str | Path) -> dict[str, EnrolledService]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or document.get("schema_version") != "v1":
        raise CatalogError("catalog must be a v1 document")
    defaults = document.get("defaults") or {}
    services: dict[str, EnrolledService] = {}
    for raw in document.get("services") or ():
        name = str(raw["service"])
        operations = frozenset(str(operation) for operation in raw.get("operations") or ())
        if name in services or not operations <= OPERATIONS.keys():
            raise CatalogError(f"service '{name}' is duplicated or names an unknown operation")
        repository = raw.get("image_repository")
        if "deployment.rollback" in operations and not repository:
            raise CatalogError(f"service '{name}' offers rollback without an image_repository")
        project = raw.get("compose_project", defaults.get("compose_project", "self"))
        services[name] = EnrolledService(
            service=name,
            compose_service=str(raw.get("compose_service", name)),
            compose_project=None if project == "self" else str(project),
            image_repository=str(repository) if repository else None,
            operations=operations,
        )
    return services
