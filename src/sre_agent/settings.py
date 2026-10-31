"""Runtime settings read by the composition root."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ

from sre_agent.investigator.client import GatewaySettings
from sre_agent.investigator.contract import OutputLanguage
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
    investigator_tool_timeout_seconds: float = 30.0
    investigator_output_language: OutputLanguage = "es"
    openrouter_base_url: str = "https://openrouter.ai"

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
        base_url = environment.get("OPENROUTER_BASE_URL") or "https://openrouter.ai"
        # Both OpenRouter keys travel to this host, so plain HTTP is only for the local
        # stand-in that the consumption E2E runs (compose.consumption-e2e.yaml).
        insecure = environment.get("OPENROUTER_ALLOW_INSECURE_BASE_URL") == "1"
        if not base_url.startswith(("https://", "http://") if insecure else "https://"):
            raise ValueError(
                "OPENROUTER_BASE_URL must use https:// "
                "(http:// only with OPENROUTER_ALLOW_INSECURE_BASE_URL=1 for the E2E)"
            )
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
        management_key = environment.get("OPENROUTER_MANAGEMENT_API_KEY") or None
        if investigator_gateway is not None:
            # One model call may wait for the endpoint catalog, then the provider; each is
            # bounded by the provider timeout. 15 s covers the gateway's own work.
            provider_calls = 2 if management_key else 1
            model_timeout = min(provider_calls * timeout + 15, 180.0)
            investigator_gateway = investigator_gateway.model_copy(
                update={"timeout_seconds": model_timeout}
            )
        language: OutputLanguage
        match environment.get("INVESTIGATOR_OUTPUT_LANGUAGE") or "es":
            case "es" | "en" as language:
                pass
            case _:
                raise ValueError("INVESTIGATOR_OUTPUT_LANGUAGE must be es or en")
        try:
            tool_timeout = float(environment.get("INVESTIGATOR_TOOL_TIMEOUT_SECONDS") or "30")
        except ValueError:
            raise ValueError("INVESTIGATOR_TOOL_TIMEOUT_SECONDS must be numeric") from None
        # The gateway's MCP transport stops at 30 s (MCP_TIMEOUT_SECONDS), so more never helps.
        if not 0 < tool_timeout <= 30:
            raise ValueError("INVESTIGATOR_TOOL_TIMEOUT_SECONDS must be between 0 and 30")
        return cls(
            database_url,
            api_key,
            timeout,
            environment.get("AUDIT_HMAC_KEY") or None,
            ReleaseMetadata.from_environment(environment),
            environment.get("GRAFANA_MCP_ENDPOINT") or None,
            mcp_token,
            openrouter_management_key=management_key,
            investigator_gateway=investigator_gateway,
            investigator_tool_timeout_seconds=tool_timeout,
            investigator_output_language=language,
            openrouter_base_url=base_url,
        )
