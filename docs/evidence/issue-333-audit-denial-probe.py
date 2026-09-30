"""Replay controlled usage.read denial contexts in the owned disposable database."""

import json
import os
import runpy
import sys
from urllib.parse import urlsplit

# Require the repository's existing test-vs-demo database guard, then tighten it
# to this verification's exact Compose test service identity.
if os.environ.get("ISSUE333_CAPTURE_PROJECT") != "candidate-wt-9bb3531fa9f1":
    raise SystemExit("Refusing probe: wrong Compose project guard")
runpy.run_path("scripts/assert_test_database_isolated.py")

sys.path.insert(0, "/app/tests")
from test_usage_read_acceptance import ADMIN_KEY, AUDIT_KEY, DATABASE_URL  # noqa: E402

parsed = urlsplit(DATABASE_URL)
if (parsed.hostname, parsed.port, parsed.path.rstrip("/")) != (
    "python-checks-db",
    5432,
    "/python_checks",
):
    raise SystemExit("Refusing probe: TEST_DATABASE_URL is not the owned Compose test DB")

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sre_agent.application import create_application  # noqa: E402
from sre_agent.settings import Settings  # noqa: E402

# Fail closed unless the clean acceptance fixture has its known admin subject,
# usage resource, and usage grant. Never delete audit rows or reset the database.
if DATABASE_URL != "postgresql://python_checks@python-checks-db:5432/python_checks":
    raise SystemExit("Refusing probe: wrong owned database URL")
with psycopg.connect(DATABASE_URL) as connection:
    if connection.execute("SELECT current_database(), current_user").fetchone() != (
        "python_checks",
        "python_checks",
    ):
        raise SystemExit("Refusing probe: wrong database identity")
    baseline = connection.execute(
        """SELECT
             (SELECT count(*) FROM principals WHERE principal_id=%s),
             (SELECT count(*) FROM resources WHERE resource_type=%s AND resource_id=%s),
             (SELECT count(*) FROM grants WHERE resource_type=%s AND resource_id=%s)""",
        ("admin-human", "administrative_control", "usage", "administrative_control", "usage"),
    ).fetchone()
if baseline != (1, 1, 1):
    raise SystemExit("Refusing probe: expected seeded principal/resource/grant baseline")

client = TestClient(
    create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY)),
    raise_server_exceptions=False,
)
for name, cause in (
    ("inactive principal", "principal_inactive"),
    ("inactive usage resource", "resource_inactive"),
    ("missing usage resource", "resource_missing"),
):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE principals SET status=%s, updated_at=now() WHERE principal_id=%s",
            ("active", "admin-human"),
        )
        connection.execute(
            "UPDATE resources SET status=%s WHERE resource_type=%s AND resource_id=%s",
            ("active", "administrative_control", "usage"),
        )
        if cause == "principal_inactive":
            connection.execute(
                "UPDATE principals SET status=%s, updated_at=now() WHERE principal_id=%s",
                ("inactive", "admin-human"),
            )
        elif cause == "resource_inactive":
            connection.execute(
                "UPDATE resources SET status=%s WHERE resource_type=%s AND resource_id=%s",
                ("inactive", "administrative_control", "usage"),
            )
        else:
            connection.execute(
                "DELETE FROM grants WHERE resource_type=%s AND resource_id=%s",
                ("administrative_control", "usage"),
            )
            connection.execute(
                "DELETE FROM resources WHERE resource_type=%s AND resource_id=%s",
                ("administrative_control", "usage"),
            )

    response = client.get(
        "/v1/usage/consumption",
        params={"month": "2026-09"},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    with psycopg.connect(DATABASE_URL) as connection:
        event = connection.execute(
            """SELECT response_status, action, stage, outcome, reason_code,
                      authorization_denial_cause, identity->>'principal_status',
                      resource->>'resource_type', policy_decision->>'decision'
               FROM audit_events WHERE operation=%s ORDER BY occurred_at DESC LIMIT 1""",
            ("usage.read",),
        ).fetchone()
    if response.status_code != 403 or event is None:
        raise AssertionError(f"{name}: expected persisted HTTP 403")
    row = dict(
        zip(
            (
                "response_status",
                "action",
                "stage",
                "outcome",
                "reason_code",
                "authorization_denial_cause",
                "identity_principal_status",
                "resource_type",
                "policy_decision",
            ),
            event,
            strict=True,
        )
    )
    if row["authorization_denial_cause"] != cause:
        raise AssertionError(f"{name}: unexpected persisted denial cause")
    print(json.dumps({"case": name, "http_status": response.status_code, **row}, sort_keys=True))
client.close()
