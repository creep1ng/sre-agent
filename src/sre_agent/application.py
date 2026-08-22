"""Single composition root for all runtime planes."""

from fastapi import FastAPI

from sre_agent import control, harness, incident
from sre_agent.gateway import health
from sre_agent.gateway.health import ReadinessProbe
from sre_agent.settings import Settings


def create_application(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.from_environment()
    probe = readiness_probe or health.postgres_readiness_probe(runtime_settings.database_url)

    application = FastAPI(title="SRE Agent", version="0.1.0")
    application.include_router(health.health_router(probe))
    application.state.planes = (control, incident, harness)
    return application
