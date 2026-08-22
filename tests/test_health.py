from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.settings import Settings


def test_liveness_does_not_call_readiness_dependency() -> None:
    calls = 0

    async def readiness_probe() -> None:
        nonlocal calls
        calls += 1

    client = TestClient(
        create_application(Settings("postgresql://unused"), readiness_probe=readiness_probe)
    )

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == 0


def test_readiness_reports_healthy_postgres() -> None:
    async def readiness_probe() -> None:
        return None

    client = TestClient(
        create_application(Settings("postgresql://unused"), readiness_probe=readiness_probe)
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "dependency": "postgresql"}


def test_readiness_sanitizes_postgres_failure() -> None:
    secret_dsn = "postgresql://admin:do-not-leak@db:5432/sre_agent"

    async def readiness_probe() -> None:
        raise RuntimeError(secret_dsn)

    client = TestClient(create_application(Settings(secret_dsn), readiness_probe=readiness_probe))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "dependency": "postgresql"}
    assert secret_dsn not in response.text
