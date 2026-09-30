"""Per-run timeline isolation over the real incident query seam (HU-OPS-05, #40a).

The service and router under test are the production #189 read path; only
storage is memory-backed (MemoryUnits). Every assertion goes through
TestClient(incident_router(service)): explicit run_id scoping, cursor
pagination inside one run, reload stability and latest-run default. No
cross-run timeline is ever assembled: each response covers a single run.
"""

from query_testkit import (
    AUTH,
    NOW,
    MemoryUnits,
    _client,
    _decision_document,
    _seed,
    _service,
)

from sre_agent.incident.persistence import RunEvent


def _seed_two_runs(units):
    _seed(units, run_id="run_demo0001")
    _seed(units, run_id="run_demo0002")
    units._decisions["dec_demo0009"] = _decision_document("human", "demo-human")
    units._events["run_demo0002"].append(
        RunEvent(
            "evt_demo0009",
            "inc-demo",
            "run_demo0002",
            3,
            "state_change",
            {
                "transition_id": "continue_investigation",
                "to": "verifying",
                "decision_id": "dec_demo0009",
            },
            NOW,
            None,
        )
    )
    return "inc-demo"


def test_detail_lists_every_run_of_the_incident() -> None:
    units = MemoryUnits()
    incident_id = _seed_two_runs(units)
    runs = _client(_service(units)).get(f"/v1/incidents/{incident_id}", headers=AUTH).json()["runs"]
    assert [run["run_id"] for run in runs] == ["run_demo0001", "run_demo0002"]
    for run in runs:
        assert run["status"] == "running"
        assert run["current_state"] == "investigating"


def test_timeline_is_scoped_to_the_explicit_run() -> None:
    units = MemoryUnits()
    incident_id = _seed_two_runs(units)
    client = _client(_service(units))
    first = client.get(
        f"/v1/incidents/{incident_id}/timeline", params={"run_id": "run_demo0001"}, headers=AUTH
    ).json()
    second = client.get(
        f"/v1/incidents/{incident_id}/timeline", params={"run_id": "run_demo0002"}, headers=AUTH
    ).json()
    assert [event["sequence"] for event in first["events"]] == [0, 1, 2]
    assert [event["sequence"] for event in second["events"]] == [0, 1, 2, 3]
    assert "verifying" not in {event["state"] for event in first["events"]}
    assert second["events"][-1]["state"] == "verifying"


def test_pagination_stays_inside_the_selected_run() -> None:
    units = MemoryUnits()
    incident_id = _seed_two_runs(units)
    client = _client(_service(units))
    page_one = client.get(
        f"/v1/incidents/{incident_id}/timeline",
        params={"run_id": "run_demo0002", "limit": 2},
        headers=AUTH,
    ).json()
    page_two = client.get(
        f"/v1/incidents/{incident_id}/timeline",
        params={"run_id": "run_demo0002", "after": page_one["next_cursor"], "limit": 2},
        headers=AUTH,
    ).json()
    sequences = [event["sequence"] for event in page_one["events"] + page_two["events"]]
    assert sequences == [0, 1, 2, 3]
    assert len({event["event_id"] for event in page_one["events"] + page_two["events"]}) == 4
    assert page_two["has_more"] is False


def test_reload_returns_the_same_persisted_events() -> None:
    units = MemoryUnits()
    incident_id = _seed_two_runs(units)
    client = _client(_service(units))
    params = {"run_id": "run_demo0002", "limit": 50}
    before = client.get(f"/v1/incidents/{incident_id}/timeline", params=params, headers=AUTH).json()
    after = client.get(f"/v1/incidents/{incident_id}/timeline", params=params, headers=AUTH).json()
    assert after == before


def test_default_run_resolves_to_the_latest_run() -> None:
    units = MemoryUnits()
    incident_id = _seed_two_runs(units)
    events = (
        _client(_service(units))
        .get(f"/v1/incidents/{incident_id}/timeline", headers=AUTH)
        .json()["events"]
    )
    assert [event["sequence"] for event in events] == [0, 1, 2, 3]


def test_event_contract_order_is_ascending_by_sequence() -> None:
    units = MemoryUnits()
    incident_id = _seed_two_runs(units)
    events = (
        _client(_service(units))
        .get(
            f"/v1/incidents/{incident_id}/timeline",
            params={"run_id": "run_demo0001"},
            headers=AUTH,
        )
        .json()["events"]
    )
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    for event in events:
        assert event["actor"]["type"] in ("human", "agent", "system")
        assert event["occurred_at"]
        assert isinstance(event["summary"], str) and event["summary"]
