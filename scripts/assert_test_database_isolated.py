"""Refuse to run destructive tests against the persistent demo database."""

import os
from urllib.parse import urlsplit


def database_identity(url: str) -> tuple[str | None, int | None, str]:
    parsed = urlsplit(url)
    port = parsed.port
    if port is None and parsed.scheme in {"postgres", "postgresql"}:
        port = 5432
    return parsed.hostname, port, parsed.path.rstrip("/")


test_url = os.environ.get("TEST_DATABASE_URL", "")
demo_url = os.environ.get("DEMO_DATABASE_URL", "")

if not test_url or not demo_url:
    raise SystemExit("TEST_DATABASE_URL and DEMO_DATABASE_URL are required")

if database_identity(test_url) == database_identity(demo_url):
    raise SystemExit("Refusing to run tests against the demo database")
