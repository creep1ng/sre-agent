"""Runtime settings read by the composition root."""

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return cls(database_url=database_url)
