"""Dependency-free liveness and PostgreSQL-backed readiness probes."""

from collections.abc import Awaitable, Callable

import psycopg
from fastapi import APIRouter, Response, status

ReadinessProbe = Callable[[], Awaitable[None]]


def postgres_readiness_probe(database_url: str) -> ReadinessProbe:
    async def probe() -> None:
        connection = await psycopg.AsyncConnection.connect(database_url, connect_timeout=2)
        async with connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
                row = await cursor.fetchone()
                if row != (1,):
                    raise RuntimeError("PostgreSQL readiness query returned an unexpected result")

    return probe


def health_router(readiness_probe: ReadinessProbe) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready(response: Response) -> dict[str, str]:
        try:
            await readiness_probe()
        except Exception:  # The response must not expose driver errors, DSNs, or credentials.
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unavailable", "dependency": "postgresql"}
        return {"status": "ok", "dependency": "postgresql"}

    return router
