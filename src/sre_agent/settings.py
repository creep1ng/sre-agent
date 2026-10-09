"""Runtime settings read by the composition root."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ

from sre_agent.investigator.client import GatewaySettings
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
    openrouter_management_key: str | None = field(default=None, repr=False)
    investigator_gateway: GatewaySettings | None = field(default=None, repr=False)

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
        mcp_token = (
            environment.get("GRAFANA_MCP_TOKEN")
            or environment.get("MCP_GRAFANA_SERVER_TOKEN")
            or None
        )
        investigator_configured = any(
            environment.get(name)
            for name in (
                "INVESTIGATOR_GATEWAY_URL",
                "INVESTIGATOR_GATEWAY_API_KEY",
                "INVESTIGATOR_MODEL_ALIAS",
            )
        )
        investigator_gateway = (
            GatewaySettings.from_environment(environment) if investigator_configured else None
        )
        return cls(
            database_url,
            api_key,
            timeout,
            environment.get("AUDIT_HMAC_KEY") or None,
            ReleaseMetadata.from_environment(environment),
            environment.get("GRAFANA_MCP_ENDPOINT") or None,
            mcp_token,
            openrouter_management_key=environment.get("OPENROUTER_MANAGEMENT_API_KEY") or None,
            investigator_gateway=investigator_gateway,
        )
