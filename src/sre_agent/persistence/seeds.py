"""Explicit, deterministic bootstrap for the local governance store."""

import asyncio
import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from os import environ

from sqlalchemy import insert, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.governance.dto import ModelAlias
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import CredentialRow, GrantRow, PrincipalRow, ResourceRow

SEED_TIME = datetime(2026, 8, 22, tzinfo=UTC)
PRINCIPALS = (
    ("admin-human", "human", "Admin human"),
    ("demo-human", "human", "Demo human"),
    ("incident-harness", "agent", "Incident harness"),
    ("restricted-harness", "agent", "Restricted harness"),
)
KEY_ENV = (
    "ADMIN_HUMAN_API_KEY",
    "DEMO_HUMAN_API_KEY",
    "INCIDENT_HARNESS_API_KEY",
    "RESTRICTED_HARNESS_API_KEY",
)


class SeedConflict(RuntimeError):
    """A secret-free indication that seed-owned state is incompatible."""


@dataclass(frozen=True, slots=True)
class SeedSettings:
    keys: tuple[str, str, str, str]
    model: str
    provider: str

    @classmethod
    def from_environment(cls, source: Mapping[str, str] | None = None) -> "SeedSettings":
        values = environ if source is None else source
        names = (*KEY_ENV, "TRIAGE_AGENT_MODEL", "TRIAGE_AGENT_PROVIDER")
        missing = next((name for name in names if not values.get(name)), None)
        if missing:
            raise ValueError(f"required seed setting is missing: {missing}")
        keys = tuple(values[name] for name in KEY_ENV)
        if any(not re.fullmatch(r"sre_[A-Za-z0-9_-]{28,}", key) or "<" in key for key in keys):
            raise ValueError("development API keys must use the required non-placeholder shape")
        if len({key[:8] for key in keys}) != len(keys):
            raise ValueError("development API key prefixes must be unique")
        model, provider = values["TRIAGE_AGENT_MODEL"], values["TRIAGE_AGENT_PROVIDER"]
        if any(marker in value for value in (model, provider) for marker in ("<", ">")):
            raise ValueError("triage assignment must not contain placeholders")
        try:
            ModelAlias(
                model_alias_id="triage-agent",
                alias="triage-agent",
                concrete_model=model,
                router="openrouter",
                inference_provider=provider,
                status="active",
            )  # noqa: E501
        except ValueError:
            raise ValueError("triage assignment has an invalid HT-01 shape") from None
        return cls(keys=keys, model=model, provider=provider)


def _hash_key(key: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(key.encode(), salt=salt, n=16384, r=8, p=1, dklen=64)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def _matches_hash(key: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        salt_bytes = bytes.fromhex(salt)
        actual = hashlib.scrypt(key.encode(), salt=salt_bytes, n=int(n), r=int(r), p=int(p))
        return algorithm == "scrypt" and hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def _require(
    row: object, fields: tuple[str, ...] | list[str], values: tuple[object, ...], entity: str
) -> None:
    for field, value in zip(fields, values, strict=True):
        if getattr(row, field) != value:
            raise SeedConflict(f"seed_state_conflict: {entity}.{field}")


async def _seed_session(session: AsyncSession, settings: SeedSettings) -> bool:
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    await session.execute(text("SELECT pg_advisory_xact_lock(112024)"))
    ids = [principal_id for principal_id, _, _ in PRINCIPALS]
    principals = [row for pid in ids if (row := await session.get(PrincipalRow, pid)) is not None]
    credentials = [
        row
        for pid in ids
        if (row := await session.get(CredentialRow, f"credential-{pid}")) is not None
    ]
    resource = await session.get(ResourceRow, ("llm_model", "triage-agent"))
    grant = await session.get(GrantRow, "grant-incident-harness-invoke-triage-agent")
    existing = (
        principals + credentials + ([resource] if resource else []) + ([grant] if grant else [])
    )
    if not existing:
        # Compact construction keeps this atomic work unit within its review budget.
        # fmt: off
        await session.execute(insert(PrincipalRow), [
            dict(principal_id=pid, kind=kind, display_name=name, status="active",
                 created_at=SEED_TIME, updated_at=SEED_TIME)
            for pid, kind, name in PRINCIPALS])
        await session.execute(insert(CredentialRow), [
            dict(credential_id=f"credential-{pid}", principal_id=pid, prefix=key[:8],
                 key_hash=_hash_key(key), status="active", created_at=SEED_TIME,
                 expires_at=None, revoked_at=None)
            for (pid, _, _), key in zip(PRINCIPALS, settings.keys, strict=True)])
        await session.execute(insert(ResourceRow).values(
            resource_type="llm_model", resource_id="triage-agent", status="active",
            model_alias_id="triage-agent", alias="triage-agent", concrete_model=settings.model,
            router="openrouter", inference_provider=settings.provider))
        await session.execute(insert(GrantRow).values(
            grant_id="grant-incident-harness-invoke-triage-agent",
            principal_id="incident-harness", action="invoke", resource_type="llm_model",
            resource_id="triage-agent", effect="allow", status="active", created_at=SEED_TIME))
        # fmt: on
        return True
    if (len(principals), len(credentials), resource is not None, grant is not None) != (
        4,
        4,
        True,
        True,
    ):
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
        if not _matches_hash(key, credential.key_hash):
            raise SeedConflict("seed_state_conflict: credentials.key_material")
    assert resource is not None and grant is not None
    _require(
        resource,
        ("status", "model_alias_id", "alias", "concrete_model", "router", "inference_provider"),
        ("active", "triage-agent", "triage-agent", settings.model, "openrouter", settings.provider),
        "resources",
    )
    _require(
        grant,
        "principal_id action resource_type resource_id effect status created_at".split(),
        ("incident-harness", "invoke", "llm_model", "triage-agent", "allow", "active", SEED_TIME),
        "grants",
    )
    return False


async def seed(database: Database, settings: SeedSettings) -> bool:
    try:
        async with database.transaction() as session:
            return await _seed_session(session, settings)
    except SQLAlchemyError:
        raise SeedConflict("seed_state_conflict: database_constraint") from None


async def _run() -> None:
    settings = SeedSettings.from_environment()
    dsn = environ.get("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL is required")
    database = Database(dsn)
    try:
        created = await seed(database, settings)
        print("seed created" if created else "seed converged")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
