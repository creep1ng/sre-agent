"""The control plane: each resource's routes on the gate, composed once for the application and
for the provisioning scripts."""

from typing import Any

from fastapi import APIRouter

from sre_agent.control.aliases import AliasRoutes, aliases_router
from sre_agent.control.catalog import CatalogRoutes, catalog_router
from sre_agent.control.consumption_limits import ConsumptionLimitRoutes, consumption_limits_router
from sre_agent.control.credentials import CredentialRoutes, credentials_router
from sre_agent.control.grants import GrantRoutes, grants_router
from sre_agent.control.principals import PrincipalRoutes, principals_router
from sre_agent.control.service import ControlService, control_router
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore


class ControlPlane:
    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.sessions = sessions
        self.consumption_limits = ConsumptionLimitRoutes(sessions, audit, projector)
        self.principals = PrincipalRoutes(sessions, audit, projector)
        self.credentials = CredentialRoutes(sessions, audit, projector)
        self.grants = GrantRoutes(sessions, audit, projector)
        self.aliases = AliasRoutes(sessions, audit, projector)
        self.catalog = CatalogRoutes(sessions, audit, projector)
        # The routes that have not moved to their resource module yet (#1022).
        self.service = ControlService(sessions, audit, projector)

    def routers(self) -> list[APIRouter]:
        return [
            consumption_limits_router(self.consumption_limits),
            principals_router(self.principals),
            credentials_router(self.credentials),
            grants_router(self.grants),
            aliases_router(self.aliases),
            catalog_router(self.catalog),
            control_router(self.service),
        ]
