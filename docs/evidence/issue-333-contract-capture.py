#!/usr/bin/env python3
"""Capture real, controlled U333-8 HTTP and persistence evidence.

This helper uses the existing acceptance-test provider stub and database seed.
It deliberately refuses any target except this task's disposable python-checks
database in its one owned Compose project. It never calls a live provider.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from fastapi.testclient import TestClient

EXPECTED_PROJECT = "candidate-wt-9bb3531fa9f1"
EXPECTED_DATABASE_URL = "postgresql://python_checks@python-checks-db:5432/python_checks"
ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8"
    )


def require_owned_target() -> str:
    project = os.environ.get("ISSUE333_CAPTURE_PROJECT")
    database_url = os.environ.get("TEST_DATABASE_URL")
    if project != EXPECTED_PROJECT:
        raise SystemExit("Refusing capture: wrong Compose project guard.")
    if database_url != EXPECTED_DATABASE_URL:
        raise SystemExit("Refusing capture: TEST_DATABASE_URL is not the owned ephemeral database")
    with psycopg.connect(database_url) as connection:
        database, user = connection.execute("SELECT current_database(), current_user").fetchone()
    if (database, user) != ("python_checks", "python_checks"):
        raise SystemExit("Refusing capture: wrong PostgreSQL identity.")
    return database_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database_url = require_owned_target()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT / "tests"))
    import test_usage_read_acceptance as acceptance  # noqa: PLC0415

    # Reuse the existing test-owned migration and demo seed, then its isolation
    # fixture, rather than inventing payload/event construction for the capture.
    acceptance.migrated_database.__wrapped__()
    isolated = acceptance.isolated_audit_events.__wrapped__()
    next(isolated)
    try:
        app = acceptance.create_application(
            acceptance.Settings(database_url, audit_hmac_key=acceptance.AUDIT_KEY),
            llm_provider=acceptance.ControlledAcceptanceProvider(),
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            openapi_response = client.get("/openapi.json")
            if openapi_response.status_code != 200:
                raise RuntimeError(f"GET /openapi.json returned {openapi_response.status_code}")
            openapi = openapi_response.json()
            path = "/v1/usage/consumption"
            operation = openapi["paths"][path]["get"]
            if openapi["info"].get("x-sre-agent-contract-version") != "2.5.0":
                raise RuntimeError("FastAPI did not advertise contract version 2.5.0")
            openapi_capture = {
                "source": "actual GET /openapi.json response",
                "http_status": openapi_response.status_code,
                "info": {
                    name: openapi["info"].get(name)
                    for name in ("title", "version", "x-sre-agent-contract-version")
                },
                "path": path,
                "get": {
                    name: operation[name]
                    for name in (
                        "operationId",
                        "summary",
                        "security",
                        "parameters",
                        "responses",
                        "x-required-query-one-of",
                        "x-maximum-evidence-rows",
                        "x-governed-scope",
                    )
                    if name in operation
                },
            }
            write_json(output / "issue-333-contract-openapi-http.json", openapi_capture)

            producer_response = client.post(
                "/v1/responses",
                headers=acceptance.auth("sre_inci_0123456789abcdefghijklmnop"),
                json={
                    "model": "triage-agent",
                    "input": "controlled integration fixture",
                    "incident_id": "issue333-produced-incident",
                    "run_id": "issue333-produced-run",
                },
            )
            if producer_response.status_code != 200:
                raise RuntimeError(f"POST /v1/responses returned {producer_response.status_code}")
            produced = producer_response.json()
            request_id = produced["request_id"]

            usage_response = client.get(
                "/v1/usage/consumption",
                params={"request_id": request_id},
                headers=acceptance.auth(),
            )
            if usage_response.status_code != 200:
                raise RuntimeError(f"GET usage returned {usage_response.status_code}")
            usage = usage_response.json()
            if usage.get("filter") != {"request_id": request_id}:
                raise RuntimeError("The persisted usage response is not for the produced request")
            expected = {
                "request_count": 1,
                "incident_runs": 1,
                "totals": {
                    "input_tokens": 11,
                    "output_tokens": 7,
                    "total_tokens": 18,
                    "cost": {
                        "amount": "0.0012300",
                        "currency": "USD",
                        "nature": "billed",
                        "precision": "exact",
                        "price_versions": ["openrouter:2026-09-10T14:00:00Z"],
                    },
                },
            }
            for key, value in expected.items():
                if usage.get(key) != value:
                    raise RuntimeError(f"Persisted usage response mismatch for {key}")

            write_json(
                output / "issue-333-contract-producer-http.json",
                {
                    "source": "actual POST /v1/responses response, controlled test provider",
                    "http_status": producer_response.status_code,
                    "request_id": request_id,
                    "response_id": produced.get("id"),
                    "status": produced.get("status"),
                    "model": produced.get("model"),
                    "metadata": produced.get("metadata"),
                    "output_text": "omitted from evidence; controlled fixture content",
                },
            )
            (output / "issue-333-contract-usage-read-http.json").write_text(
                usage_response.text + "\n", encoding="utf-8"
            )

            with psycopg.connect(database_url) as connection:
                producer_rows = connection.execute(
                    """SELECT operation, response_status, consumption
                       FROM audit_events
                       WHERE operation='responses.create'
                         AND correlation->>'request_id' = %s
                       ORDER BY occurred_at""",
                    (request_id,),
                ).fetchall()
                usage_rows = connection.execute(
                    """SELECT operation, response_status
                       FROM audit_events WHERE operation='usage.read'
                       ORDER BY occurred_at"""
                ).fetchall()
            if len(producer_rows) != 1 or len(usage_rows) != 1:
                raise RuntimeError(
                    f"Expected exactly one producer and usage-read audit row; got "
                    f"{len(producer_rows)} and {len(usage_rows)}"
                )
            event = producer_rows[0]
            consumption = event[2]
            keys = (
                "availability",
                "source",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "billed_usd",
                "currency",
                "precision",
            )
            persisted = {key: consumption.get(key) for key in keys}
            sql_evidence = {
                "database": "python_checks (owned ephemeral Compose DB)",
                "request_match": (
                    "producer correlation.request_id matched POST response and GET filter"
                ),
                "producer_query": (
                    "SELECT operation, response_status, consumption FROM audit_events "
                    "WHERE operation='responses.create' AND correlation->>'request_id' = %s "
                    "ORDER BY occurred_at"
                ),
                "producer_rows": [
                    {
                        "operation": event[0],
                        "response_status": event[1],
                        "consumption": persisted,
                    }
                ],
                "usage_read_query": (
                    "SELECT operation, response_status FROM audit_events "
                    "WHERE operation='usage.read' ORDER BY occurred_at"
                ),
                "usage_read_rows": [
                    {"operation": row[0], "response_status": row[1]} for row in usage_rows
                ],
            }
            write_json(output / "issue-333-contract-persisted-sql.json", sql_evidence)

        print("Controlled integration capture passed.")
        print(f"Compose project: {EXPECTED_PROJECT}; database: python_checks.")
        print("GET /openapi.json: HTTP 200; contract version 2.5.0; canonical usage route present.")
        print(f"POST /v1/responses: HTTP 200; controlled persisted request id {request_id}.")
        print(
            "GET /v1/usage/consumption: HTTP 200; request_count=1, incident_runs=1, "
            "tokens=11/7/18, exact billed USD=0.0012300."
        )
        print("SQL: one matching responses.create event and one usage.read event, both status 200.")
        print(f"Sanitized JSON/SQL captures: {output}")
    finally:
        isolated.close()


if __name__ == "__main__":
    main()
