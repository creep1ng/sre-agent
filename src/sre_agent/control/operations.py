"""The one registry of control-plane operations.

Each operation names its audit operation, its route and the scope it asks for. The scope table,
the audit names and the `x-governed-scope` OpenAPI extras derive from it.
"""

from dataclasses import dataclass
from typing import Any

from sre_agent.gate.pipeline import Scope, ScopeDeclaration, declare

RESOURCE_TYPE = "administrative_control"


@dataclass(frozen=True)
class ControlOperation:
    """One control route: `path` is its scope key (`{id}`), `route` the path it is served at."""

    name: str
    method: str
    path: str
    route: str
    action: str
    resource_id: str
    # Whether its OpenAPI entry documents the scope as `x-governed-scope`.
    documented: bool = True

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.path

    @property
    def scope(self) -> Scope:
        return Scope(self.action, RESOURCE_TYPE, self.resource_id)

    def declare(self) -> ScopeDeclaration:
        """Register the operation in the gate; the module that serves it on the gate calls this."""
        return declare(
            self.method,
            self.route,
            action=self.action,
            resource_type=RESOURCE_TYPE,
            resource_id=self.resource_id,
        )

    @property
    def openapi_extra(self) -> dict[str, Any]:
        """The route's `x-governed-scope`, or nothing for a route that does not document it."""
        if not self.documented:
            return {}
        return {
            "x-governed-scope": {
                "action": self.action,
                "resource_type": RESOURCE_TYPE,
                "resource_id": self.resource_id,
            }
        }


def _operation(
    name: str,
    method: str,
    path: str,
    action: str,
    resource_id: str,
    *,
    route: str | None = None,
    documented: bool = True,
) -> ControlOperation:
    return ControlOperation(name, method, path, route or path, action, resource_id, documented)


READ, WRITE = "admin.read", "admin.write"
# fmt: off
OPERATIONS: tuple[ControlOperation, ...] = (
    _operation("consumption_limits.replace", "PUT", "/v1/consumption-limits", WRITE,
               "consumption_limits"),
    _operation("consumption_limits.get", "GET", "/v1/consumption-limits", READ,
               "consumption_limits"),
    _operation("principals.create", "POST", "/v1/principals", WRITE, "principals"),
    _operation("principals.list", "GET", "/v1/principals", READ, "principals"),
    _operation("principals.get", "GET", "/v1/principals/{id}", READ, "principals",
               route="/v1/principals/{principal_id}"),
    _operation("principals.status.replace", "PUT", "/v1/principals/{id}/status", WRITE,
               "principals", route="/v1/principals/{principal_id}/status", documented=False),
    _operation("credentials.issue", "POST", "/v1/principals/{id}/credentials", WRITE, "credentials",
               route="/v1/principals/{principal_id}/credentials", documented=False),
    _operation("credentials.list", "GET", "/v1/principals/{id}/credentials", READ, "credentials",
               route="/v1/principals/{principal_id}/credentials", documented=False),
    _operation("credentials.revoke", "DELETE", "/v1/credentials/{id}", WRITE, "credentials",
               route="/v1/credentials/{credential_id}", documented=False),
    _operation("credentials.rotate", "POST", "/v1/credentials/{id}/rotation", WRITE, "credentials",
               route="/v1/credentials/{credential_id}/rotation", documented=False),
    _operation("grants.create", "POST", "/v1/grants", WRITE, "grants"),
    _operation("grants.list", "GET", "/v1/grants", READ, "grants"),
    _operation("grants.revoke", "DELETE", "/v1/grants/{id}", WRITE, "grants",
               route="/v1/grants/{grant_id}", documented=False),
    _operation("aliases.create", "POST", "/v1/model-aliases", WRITE, "model_aliases"),
    _operation("aliases.list", "GET", "/v1/model-aliases", READ, "model_aliases"),
    _operation("aliases.get", "GET", "/v1/model-aliases/{id}", READ, "model_aliases",
               route="/v1/model-aliases/{alias_id}"),
    _operation("aliases.assignment.replace", "PUT", "/v1/model-aliases/{id}/assignment", WRITE,
               "model_aliases", route="/v1/model-aliases/{alias_id}/assignment"),
    _operation("aliases.status.replace", "PUT", "/v1/model-aliases/{id}/status", WRITE,
               "model_aliases", route="/v1/model-aliases/{alias_id}/status"),
    _operation("catalog.create", "POST", "/v1/catalog/resources", WRITE, "catalog"),
    _operation("catalog.list", "GET", "/v1/catalog/resources", READ, "catalog"),
    _operation("catalog.read", "GET", "/v1/catalog/resources/{type}/{id}", READ, "catalog",
               route="/v1/catalog/resources/{resource_type}/{id}"),
    _operation("catalog.create", "POST", "/v1/skills/versions", WRITE, "catalog"),
    _operation("catalog.read", "GET", "/v1/skills/{skill_id}/{version}", READ, "catalog"),
    _operation("catalog.status.replace", "PUT", "/v1/skills/{skill_id}/{version}/status", WRITE,
               "catalog"),
    # Reading a skill's lifecycle status asks for the write grant, as its publication does.
    _operation("catalog.read", "GET", "/v1/skills/{skill_id}/{version}/status", WRITE, "catalog"),
    _operation("catalog.create", "POST", "/v1/bok/collections/versions", WRITE, "catalog"),
    _operation("catalog.read", "GET", "/v1/bok/collections/{collection_id}/versions/{version}",
               READ, "catalog"),
)
# fmt: on
CONTROL: dict[tuple[str, str], ControlOperation] = {op.key: op for op in OPERATIONS}
assert len(CONTROL) == len(OPERATIONS), "a control route is registered twice"
CONTROL_SCOPES: dict[tuple[str, str], tuple[str, str, str]] = {
    key: (op.action, RESOURCE_TYPE, op.resource_id) for key, op in CONTROL.items()
}
CONTROL_OPERATIONS: dict[tuple[str, str], tuple[str, str, str, str]] = {
    key: (op.name, *CONTROL_SCOPES[key]) for key, op in CONTROL.items()
}
