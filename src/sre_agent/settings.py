"""Runtime settings read by the composition root."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ

from sre_agent.release import ReleaseMetadata


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    openrouter_api_key: str | None = field(default=None, repr=False)
    openrouter_timeout_seconds: float = 30.0
    audit_hmac_key: str | None = field(default=None, repr=False)
    release_metadata: ReleaseMetadata = field(default_factory=ReleaseMetadata.defaults)
    grafana_mcp_endpoint: str | None = None
    grafana_mcp_token: str | None = field(default=None, repr=False)
    bok_jev_enabled: bool = False
    typesafe_api_key: str | None = field(default=None, repr=False)
    bok_jev_timeout_seconds: float = 5.0

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] = environ) -> "Settings":
        database_url = environment.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        api_key = environment.get("OPENROUTER_API_KEY") or None
        try:
            timeout = float(environment.get("OPENROUTER_TIMEOUT_SECONDS", "30"))
        except ValueError:
            raise ValueError("OPENROUTER_TIMEOUT_SECONDS must be numeric") from None
        if not 0 < timeout <= 120:
            raise ValueError("OPENROUTER_TIMEOUT_SECONDS must be between 0 and 120")
        jev_enabled_value = environment.get("BOK_JEV_ENABLED", "false").strip().lower()
        if jev_enabled_value not in {"true", "false"}:
            raise ValueError("BOK_JEV_ENABLED must be true or false")
        bok_jev_enabled = jev_enabled_value == "true"
        typesafe_api_key = environment.get("TYPESAFE_API_KEY") or None
        if bok_jev_enabled and not typesafe_api_key:
            raise RuntimeError("TYPESAFE_API_KEY is required when BOK_JEV_ENABLED is true")
        try:
            bok_jev_timeout = float(environment.get("BOK_JEV_TIMEOUT_SECONDS", "5"))
        except ValueError:
            raise ValueError("BOK_JEV_TIMEOUT_SECONDS must be numeric") from None
        if not 0 < bok_jev_timeout <= 30:
            raise ValueError("BOK_JEV_TIMEOUT_SECONDS must be between 0 and 30")
        mcp_token = (
            environment.get("GRAFANA_MCP_TOKEN")
            or environment.get("MCP_GRAFANA_SERVER_TOKEN")
            or None
        )
        return cls(
            database_url,
            api_key,
            timeout,
            environment.get("AUDIT_HMAC_KEY") or None,
            ReleaseMetadata.from_environment(environment),
            environment.get("GRAFANA_MCP_ENDPOINT") or None,
            mcp_token,
            bok_jev_enabled,
            typesafe_api_key,
            bok_jev_timeout,
        )
