"""Incident detail query tests (HT-INC-RUNTIME-B, issue #189).

Covers CA1 (identity/state/version), CA5 read paths (401/403 without partial
content) and read-only behavior. Timeline, snapshot and PostgreSQL coverage
live in test_incident_query_timeline.py.
"""

from __future__ import annotations

from query_testkit import AUTH, MemoryUnits, _client, _deny, _seed, _service


def test_detail_returns_identity_state_and_version() -> None:
    units = MemoryUnits()
    _seed(units)
    response = _client(_service(units)).get("/v1/incidents/inc-demo", headers=AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["incident_id"] == "inc-demo"
    assert payload["state"] == "investigating"
    assert payload["severity"] == "sev2"
    assert payload["version"] == 4
    assert payload["alert"]["alert_id"] == "alt-payment-error-rate"
    assert [run["run_id"] for run in payload["runs"]] == ["run_demo0001"]


def test_detail_missing_incident_is_explicit() -> None:
    units = MemoryUnits()
    response = _client(_service(units)).get("/v1/incidents/inc-missing", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "incident_not_found"


def test_detail_with_unsupported_workflow_is_rejected() -> None:
    units = MemoryUnits()
    incident_id, _ = _seed(units)
    units._incidents[incident_id].state["workflow_version"] = "9.9.9"
    response = _client(_service(units)).get(f"/v1/incidents/{incident_id}", headers=AUTH)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_malformed_incident_id_is_rejected_on_all_endpoints() -> None:
    units = MemoryUnits()
    _seed(units)
    client = _client(_service(units))
    for path in (
        "/v1/incidents/12",
        "/v1/incidents/12/timeline",
        "/v1/incidents/12/snapshot",
    ):
        response = client.get(path, headers=AUTH)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_unauthenticated_and_unauthorized_reads_reveal_nothing() -> None:
    units = MemoryUnits()
    _seed(units)
    denied = _client(_service(units, authorizer=_deny))
    anonymous = denied.get("/v1/incidents/inc-demo")
    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"
    forbidden = denied.get("/v1/incidents/inc-demo", headers=AUTH)
    assert forbidden.status_code == 403
    assert "paymentservice" not in forbidden.text
    assert "inc-demo" not in forbidden.json()["error"]["message"]


def test_reads_do_not_mutate_authoritative_state() -> None:
    units = MemoryUnits()
    incident_id, run_id = _seed(units)
    client = _client(_service(units))
    client.get(f"/v1/incidents/{incident_id}", headers=AUTH)
    client.get(f"/v1/incidents/{incident_id}/timeline", headers=AUTH)
    assert units._incidents[incident_id].version == 4
    assert units._runs[run_id].version == 4
    assert len(units._events[run_id]) == 3


def test_detail_without_runs_returns_empty_runs_not_absence() -> None:
    units = MemoryUnits()
    incident_id, _ = _seed(units)
    units._runs.clear()
    response = _client(_service(units)).get(f"/v1/incidents/{incident_id}", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["runs"] == []
