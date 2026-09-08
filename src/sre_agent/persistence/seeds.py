"""Explicit, deterministic bootstrap for the local governance store."""

import asyncio
from argparse import ArgumentParser
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from os import environ

from sqlalchemy import insert, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.governance.dto import ModelAlias
from sre_agent.persistence.api_keys import hash_api_key, is_api_key, verify_api_key
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import CredentialRow, GrantRow, PrincipalRow, ResourceRow

SEED_TIME = datetime(2026, 8, 22, tzinfo=UTC)
PRINCIPALS = (
    ("admin-human", "human", "Admin human"),
    ("demo-human", "human", "Demo human"),
    ("incident-harness", "agent", "Incident harness"),
    ("restricted-harness", "agent", "Restricted harness"),
)
ADMIN_RESOURCES = (
    ("administrative_control", "principals"),
    ("administrative_control", "credentials"),
)
ADMIN_GRANTS = (
    ("grant-admin-human-admin-read-principals", "admin-human", "admin.read"),
    ("grant-admin-human-admin-write-principals", "admin-human", "admin.write"),
    ("grant-admin-human-admin-read-credentials", "admin-human", "admin.read"),
    ("grant-admin-human-admin-write-credentials", "admin-human", "admin.write"),
)
KEY_ENV = (
    "ADMIN_HUMAN_API_KEY",
    "DEMO_HUMAN_API_KEY",
    "INCIDENT_HARNESS_API_KEY",
    "RESTRICTED_HARNESS_API_KEY",
)
ROUTING_ENV = (
    "TRIAGE_AGENT_MODEL",
    "TRIAGE_AGENT_PROVIDER",
    "REMEDIATION_AGENT_MODEL",
    "REMEDIATION_AGENT_PROVIDER",
)


class SeedConflict(RuntimeError):
    """A secret-free indication that seed-owned state is incompatible."""


@dataclass(frozen=True, slots=True)
class RouteSetting:
    alias: str
    model: str
    provider: str


@dataclass(frozen=True, slots=True)
class RoutingSettings:
    routes: tuple[RouteSetting, RouteSetting]

    @classmethod
    def from_environment(cls, source: Mapping[str, str] | None = None) -> "RoutingSettings":
        values = environ if source is None else source
        missing = next((name for name in ROUTING_ENV if not values.get(name)), None)
        if missing:
            raise ValueError(f"required routing setting is missing: {missing}")
        routes = (
            RouteSetting(
                "triage-agent", values["TRIAGE_AGENT_MODEL"], values["TRIAGE_AGENT_PROVIDER"]
            ),
            RouteSetting(
                "remediation-agent",
                values["REMEDIATION_AGENT_MODEL"],
                values["REMEDIATION_AGENT_PROVIDER"],
            ),
        )
        if routes[0].alias == routes[1].alias:
            raise ValueError("configured routing aliases must be unique")
        for route in routes:
            if len(route.alias) > 34:
                raise ValueError("routing aliases must fit deterministic grant identifiers")
            if any(
                marker in value
                for value in (route.alias, route.model, route.provider)
                for marker in ("<", ">")
            ):
                raise ValueError("routing assignment must not contain placeholders")
            try:
                ModelAlias(
                    model_alias_id=route.alias,
                    alias=route.alias,
                    concrete_model=route.model,
                    router="openrouter",
                    inference_provider=route.provider,
                    status="active",
                )
            except ValueError:
                raise ValueError("routing assignment has an invalid HT-01 shape") from None
        return cls(routes)


@dataclass(frozen=True, slots=True)
class SeedSettings:
    keys: tuple[str, str, str, str]
    routing: RoutingSettings

    @property
    def model(self) -> str:
        return self.routing.routes[0].model

    @property
    def provider(self) -> str:
        return self.routing.routes[0].provider

    @classmethod
    def from_environment(cls, source: Mapping[str, str] | None = None) -> "SeedSettings":
        values = environ if source is None else source
        missing = next((name for name in KEY_ENV if not values.get(name)), None)
        if missing:
            raise ValueError(f"required seed setting is missing: {missing}")
        keys = tuple(values[name] for name in KEY_ENV)
        if any(not is_api_key(key) or "<" in key for key in keys):
            raise ValueError("development API keys must use the required non-placeholder shape")
        if len({key[:8] for key in keys}) != len(keys):
            raise ValueError("development API key prefixes must be unique")
        return cls(keys=keys, routing=RoutingSettings.from_environment(values))


def _require(
    row: object, fields: tuple[str, ...] | list[str], values: tuple[object, ...], entity: str
) -> None:
    for field, value in zip(fields, values, strict=True):
        if getattr(row, field) != value:
            raise SeedConflict(f"seed_state_conflict: {entity}.{field}")


def _grant_id(alias: str) -> str:
    return f"grant-incident-harness-invoke-{alias}"


def _resource_values(route: RouteSetting) -> dict[str, object]:
    return {
        "resource_type": "llm_model",
        "resource_id": route.alias,
        "status": "active",
        "model_alias_id": route.alias,
        "alias": route.alias,
        "concrete_model": route.model,
        "router": "openrouter",
        "inference_provider": route.provider,
    }


def _grant_values(route: RouteSetting) -> dict[str, object]:
    return {
        "grant_id": _grant_id(route.alias),
        "principal_id": "incident-harness",
        "action": "invoke",
        "resource_type": "llm_model",
        "resource_id": route.alias,
        "effect": "allow",
        "status": "active",
        "created_at": SEED_TIME,
    }


async def _seed_session(
    session: AsyncSession,
    settings: SeedSettings,
    *,
    reconcile_routing: bool,
    expected_routing_digest: str | None,
) -> bool:
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    await session.execute(text("SELECT pg_advisory_xact_lock(112024)"))
    ids = [principal_id for principal_id, _, _ in PRINCIPALS]
    principals = [row for pid in ids if (row := await session.get(PrincipalRow, pid)) is not None]
    credentials = [
        row
        for pid in ids
        if (row := await session.get(CredentialRow, f"credential-{pid}")) is not None
    ]
    routes = settings.routing.routes
    resources = [
        row
        for route in routes
        if (row := await session.get(ResourceRow, ("llm_model", route.alias))) is not None
    ]
    grants = [
        row
        for route in routes
        if (row := await session.get(GrantRow, _grant_id(route.alias))) is not None
    ]
    admin_resources = [
        row for key in ADMIN_RESOURCES if (row := await session.get(ResourceRow, key)) is not None
    ]
    admin_grants = [
        row
        for grant_id, _, _ in ADMIN_GRANTS
        if (row := await session.get(GrantRow, grant_id)) is not None
    ]
    existing = principals + credentials + resources + grants
    if existing:
        if reconcile_routing:
            if expected_routing_digest is None:
                raise ValueError("routing reconciliation requires the checked routing digest")
            observed_digest = _routing_digest(settings.routing, resources)
            if observed_digest != expected_routing_digest:
                raise SeedConflict("seed_state_conflict: routing_snapshot_changed")
        present_resources = {row.resource_id for row in resources}
        missing_routes = [route for route in routes if route.alias not in present_resources]
        if missing_routes:
            await session.execute(
                insert(ResourceRow), [_resource_values(route) for route in missing_routes]
            )
        present_grants = {row.resource_id for row in grants}
        missing_grants = [route for route in routes if route.alias not in present_grants]
        if missing_grants:
            await session.execute(
                insert(GrantRow), [_grant_values(route) for route in missing_grants]
            )
        if reconcile_routing:
            for route in routes:
                await session.execute(
                    update(ResourceRow)
                    .where(
                        ResourceRow.resource_type == "llm_model",
                        ResourceRow.resource_id == route.alias,
                    )
                    .values(
                        status="active",
                        model_alias_id=route.alias,
                        alias=route.alias,
                        concrete_model=route.model,
                        router="openrouter",
                        inference_provider=route.provider,
                    )
                )
        await session.flush()
        resources = [
            row
            for route in routes
            if (row := await session.get(ResourceRow, ("llm_model", route.alias))) is not None
        ]
        grants = [
            row
            for route in routes
            if (row := await session.get(GrantRow, _grant_id(route.alias))) is not None
        ]
    if existing and (len(admin_resources), len(admin_grants)) != (
        len(ADMIN_RESOURCES),
        len(ADMIN_GRANTS),
    ):
        # Additive convergence: databases seeded before #147 keep their data and
        # gain the missing administrative nodes. Missing resources/grants are
        # inserted with the same deterministic values as a fresh seed; existing
        # rows are then validated by the convergence check below.
        present_resources = {(row.resource_type, row.resource_id) for row in admin_resources}
        missing_resources = [
            dict(
                resource_type=resource_type,
                resource_id=resource_id,
                status="active",
                model_alias_id=None,
                alias=None,
                concrete_model=None,
                router=None,
                inference_provider=None,
            )
            for resource_type, resource_id in ADMIN_RESOURCES
            if (resource_type, resource_id) not in present_resources
        ]
        if missing_resources:
            await session.execute(insert(ResourceRow), missing_resources)
        present_grants = {row.grant_id for row in admin_grants}
        missing_grants = [
            dict(
                grant_id=grant_id,
                principal_id=principal_id,
                action=action,
                resource_type="administrative_control",
                resource_id="principals" if "principals" in grant_id else "credentials",
                effect="allow",
                status="active",
                created_at=SEED_TIME,
            )
            for grant_id, principal_id, action in ADMIN_GRANTS
            if grant_id not in present_grants
        ]
        if missing_grants:
            await session.execute(insert(GrantRow), missing_grants)
        await session.flush()
        admin_resources = [
            row
            for key in ADMIN_RESOURCES
            if (row := await session.get(ResourceRow, key)) is not None
        ]
        admin_grants = [
            row
            for grant_id, _, _ in ADMIN_GRANTS
            if (row := await session.get(GrantRow, grant_id)) is not None
        ]
    if not existing:
        # Compact construction keeps this atomic work unit within its review budget.
        # fmt: off
        await session.execute(insert(PrincipalRow), [
            dict(principal_id=pid, kind=kind, display_name=name, status="active",
                 created_at=SEED_TIME, updated_at=SEED_TIME)
            for pid, kind, name in PRINCIPALS])
        await session.execute(insert(CredentialRow), [
            dict(credential_id=f"credential-{pid}", principal_id=pid, prefix=key[:8],
                 key_hash=hash_api_key(key), status="active", created_at=SEED_TIME,
                 expires_at=None, revoked_at=None)
            for (pid, _, _), key in zip(PRINCIPALS, settings.keys, strict=True)])
        await session.execute(insert(ResourceRow), [_resource_values(route) for route in routes])
        await session.execute(insert(GrantRow), [_grant_values(route) for route in routes])
        fresh_admin_resources = [
            dict(resource_type=resource_type, resource_id=resource_id, status="active",
                 model_alias_id=None, alias=None, concrete_model=None, router=None,
                 inference_provider=None)
            for resource_type, resource_id in ADMIN_RESOURCES]
        if fresh_admin_resources:
            await session.execute(insert(ResourceRow), fresh_admin_resources)
        fresh_admin_grants = [
            dict(grant_id=grant_id, principal_id="admin-human", action=action,
                 resource_type="administrative_control",
                 resource_id="principals" if "principals" in grant_id else "credentials",
                 effect="allow", status="active", created_at=SEED_TIME)
            for grant_id, _, action in ADMIN_GRANTS]
        if fresh_admin_grants:
            await session.execute(insert(GrantRow), fresh_admin_grants)
        # fmt: on
        return True
    if (
        len(principals),
        len(credentials),
        len(resources),
        len(grants),
        len(admin_resources),
        len(admin_grants),
    ) != (4, 4, 2, 2, 2, 4):
        raise SeedConflict("seed_state_conflict: incomplete_seed_graph")
    by_principal = {row.principal_id: row for row in principals}
    by_credential = {row.principal_id: row for row in credentials}
    for (pid, kind, name), key in zip(PRINCIPALS, settings.keys, strict=True):
        _require(
            by_principal[pid],
            ("kind", "display_name", "status", "created_at", "updated_at"),
            (kind, name, "active", SEED_TIME, SEED_TIME),
            "principals",
        )
        credential = by_credential[pid]
        _require(
            credential,
            ("credential_id", "prefix", "status", "created_at", "expires_at", "revoked_at"),
            (f"credential-{pid}", key[:8], "active", SEED_TIME, None, None),
            "credentials",
        )
        if not verify_api_key(key, credential.key_hash):
            raise SeedConflict("seed_state_conflict: credentials.key_material")
    by_alias = {row.resource_id: row for row in resources}
    grants_by_resource = {row.resource_id: row for row in grants}
    for route in routes:
        _require(
            by_alias[route.alias],
            ("status", "model_alias_id", "alias", "concrete_model", "router", "inference_provider"),
            ("active", route.alias, route.alias, route.model, "openrouter", route.provider),
            "resources",
        )
        _require(
            grants_by_resource[route.alias],
            "principal_id action resource_type resource_id effect status created_at".split(),
            ("incident-harness", "invoke", "llm_model", route.alias, "allow", "active", SEED_TIME),
            "grants",
        )
    by_resource = {(row.resource_type, row.resource_id): row for row in admin_resources}
    for resource_type, resource_id in ADMIN_RESOURCES:
        _require(
            by_resource[(resource_type, resource_id)],
            ("status", "model_alias_id", "concrete_model"),
            ("active", None, None),
            "resources",
        )
    by_grant = {row.grant_id: row for row in admin_grants}
    for grant_id, principal_id, action in ADMIN_GRANTS:
        _require(
            by_grant[grant_id],
            "principal_id action resource_type effect status created_at".split(),
            (principal_id, action, "administrative_control", "allow", "active", SEED_TIME),
            "grants",
        )
    return False


async def seed(
    database: Database,
    settings: SeedSettings,
    *,
    reconcile_routing: bool = False,
    expected_routing_digest: str | None = None,
) -> bool:
    try:
        async with database.transaction() as session:
            return await _seed_session(
                session,
                settings,
                reconcile_routing=reconcile_routing,
                expected_routing_digest=expected_routing_digest,
            )
    except SQLAlchemyError:
        raise SeedConflict("seed_state_conflict: database_constraint") from None


async def routing_drift(
    database: Database, settings: RoutingSettings
) -> dict[str, tuple[str, ...]]:
    """Return only alias and field names; configured and persisted values stay private."""
    drift: dict[str, tuple[str, ...]] = {}
    async with database.sessions() as session:
        for route in settings.routes:
            row = await session.get(ResourceRow, ("llm_model", route.alias))
            if row is None:
                drift[route.alias] = ("missing",)
                continue
            expected = _resource_values(route)
            fields = tuple(
                field
                for field in (
                    "status",
                    "model_alias_id",
                    "alias",
                    "concrete_model",
                    "router",
                    "inference_provider",
                )
                if getattr(row, field) != expected[field]
            )
            if fields:
                drift[route.alias] = fields
    return drift


def _routing_digest(settings: RoutingSettings, rows: list[ResourceRow]) -> str:
    by_alias = {row.resource_id: row for row in rows}
    fields = (
        "status",
        "model_alias_id",
        "alias",
        "concrete_model",
        "router",
        "inference_provider",
    )
    parts: list[str] = []
    for route in sorted(settings.routes, key=lambda item: item.alias):
        row = by_alias.get(route.alias)
        parts.append(route.alias)
        parts.extend("<missing>" if row is None else str(getattr(row, field)) for field in fields)
    return sha256("\0".join(parts).encode()).hexdigest()


async def routing_digest(database: Database, settings: RoutingSettings) -> str:
    async with database.sessions() as session:
        rows = [
            row
            for route in settings.routes
            if (row := await session.get(ResourceRow, ("llm_model", route.alias))) is not None
        ]
        return _routing_digest(settings, rows)


async def _run() -> None:
    parser = ArgumentParser(description="Bootstrap and reconcile local governance data.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check-routing", action="store_true")
    actions.add_argument("--reconcile-routing", metavar="EXPECTED_SHA256")
    arguments = parser.parse_args()
    dsn = environ.get("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL is required")
    database = Database(dsn)
    try:
        if arguments.check_routing:
            drift = await routing_drift(database, RoutingSettings.from_environment())
            if not drift:
                print("routing_status: converged")
                return
            digest = await routing_digest(database, RoutingSettings.from_environment())
            summary = ";".join(
                f"{alias}={','.join(fields)}" for alias, fields in sorted(drift.items())
            )
            print(f"routing_status: drifted digest={digest} {summary}")
            raise SystemExit(2)
        settings = SeedSettings.from_environment()
        created = await seed(
            database,
            settings,
            reconcile_routing=arguments.reconcile_routing is not None,
            expected_routing_digest=arguments.reconcile_routing,
        )
        if arguments.reconcile_routing is not None:
            print("seed routing reconciled")
        else:
            print("seed created" if created else "seed converged")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
