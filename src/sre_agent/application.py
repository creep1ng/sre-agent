# ruff: noqa: I001
"""Single composition root for all runtime planes."""

import httpx
from fastapi import FastAPI

from sre_agent import control, harness, incident
from sre_agent.gateway import health
from sre_agent.gateway.authentication import AuthenticationFailed, authentication_failed_handler
from sre_agent.gateway.health import ReadinessProbe
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.providers import LLMProvider
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import AuditStore, PostgresAuditStore, ResponsesService, responses_router  # noqa: E501  # fmt: skip
from sre_agent.persistence.database import Database
from sre_agent.settings import Settings


def create_application(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    provider_client: httpx.AsyncClient | None = None,
    llm_provider: LLMProvider | None = None,
    audit_store: AuditStore | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.from_environment()
    probe = readiness_probe or health.postgres_readiness_probe(runtime_settings.database_url)
    database = Database(runtime_settings.database_url)
    shared_provider_client = None
    provider = llm_provider
    if provider is None and runtime_settings.openrouter_api_key:
        shared_provider_client = provider_client or httpx.AsyncClient(
            base_url="https://openrouter.ai",
            timeout=runtime_settings.openrouter_timeout_seconds,
        )
        provider = OpenRouterProvider(
            shared_provider_client, api_key=runtime_settings.openrouter_api_key
        )

    application = FastAPI(title="SRE Agent", version="0.1.0")
    application.include_router(health.health_router(probe))
    application.state.planes = (control, incident, harness)
    application.state.session_provider = database.sessions
    application.state.database = database
    application.state.llm_provider = provider
    if provider is not None and runtime_settings.audit_hmac_key:
        store = audit_store or PostgresAuditStore(database.sessions)
        service = ResponsesService(database.sessions, provider, store, AuditProjector(runtime_settings.audit_hmac_key.encode()))  # noqa: E501  # fmt: skip
        application.include_router(responses_router(service))
    application.add_exception_handler(AuthenticationFailed, authentication_failed_handler)
    application.add_event_handler("shutdown", database.dispose)
    if shared_provider_client is not None:
        application.add_event_handler("shutdown", shared_provider_client.aclose)
    return application
