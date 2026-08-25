"""Single composition root for all runtime planes."""

from fastapi import FastAPI

from sre_agent import control, harness, incident
from sre_agent.gateway import health
from sre_agent.gateway.authentication import AuthenticationFailed, authentication_failed_handler
from sre_agent.gateway.health import ReadinessProbe
from sre_agent.persistence.database import Database
from sre_agent.settings import Settings


def create_application(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.from_environment()
    probe = readiness_probe or health.postgres_readiness_probe(runtime_settings.database_url)
    database = Database(runtime_settings.database_url)

    application = FastAPI(title="SRE Agent", version="0.1.0")
    application.include_router(health.health_router(probe))
    application.state.planes = (control, incident, harness)
    application.state.session_provider = database.sessions
    application.add_exception_handler(AuthenticationFailed, authentication_failed_handler)
    application.add_event_handler("shutdown", database.dispose)
    return application
