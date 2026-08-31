"""Runtime settings read by the composition root."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    openrouter_api_key: str | None = field(default=None, repr=False)
    openrouter_timeout_seconds: float = 30.0
    audit_hmac_key: str | None = field(default=None, repr=False)

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
        return cls(database_url, api_key, timeout, environment.get("AUDIT_HMAC_KEY") or None)
