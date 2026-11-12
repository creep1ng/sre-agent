"""Auth storage-failure contract for incident queries (issue #189).

Exercises the real _authenticate path shared by detail, timeline and
snapshot: a well-formed bearer whose credential lookup fails must surface
503 storage_unavailable (retryable with Retry-After), never a 500.
Malformed credentials still yield 401 without touching the repository.
"""

import asyncio
from uuid import uuid4

from sre_agent.gateway.incidents import IncidentQueryService
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.repositories import CredentialRepository

WORKFLOW = load_incident_workflow("agent/workflows/incident-response.yaml")
WELL_FORMED_BEARER = "Bearer sre_demo00000000000000000001"


class _Sessions:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return None


async def _exploding_authorizer(session, principal):
    raise AssertionError("authorization must not run before authentication")


def _service():
    return IncidentQueryService(_Sessions(), WORKFLOW, _exploding_units, _exploding_authorizer)


async def _exploding_units():
    raise AssertionError("storage must not be touched on auth failure")


async def _outage(self, key, **kwargs):
    raise RuntimeError("simulated credential store outage")


def test_credential_store_outage_returns_503(monkeypatch) -> None:
    monkeypatch.setattr(CredentialRepository, "authenticate", _outage)
    principal, error = _run(WELL_FORMED_BEARER)
    assert principal is None
    assert error.status_code == 503
    body = error.body.decode()
    assert "storage_unavailable" in body and "true" in body
    assert error.headers["retry-after"] == "5"


def test_malformed_bearer_returns_401_without_repository(monkeypatch) -> None:
    def _forbidden(self, key, **kwargs):
        raise AssertionError("repository must not be consulted for malformed credentials")

    monkeypatch.setattr(CredentialRepository, "authenticate", _forbidden)
    for authorization in (None, "Bearer invalid"):
        principal, error = _run(authorization)
        assert principal is None
        assert error.status_code == 401


def _run(authorization):
    return asyncio.run(_service()._authorized_principal(uuid4(), authorization))
