"""Issue #423 walkthrough probe: grant pre-create validation evidence.

Containerized E2E: exercises POST /v1/grants against real FastAPI + PostgreSQL
with missing/inactive principals and resources, records real HTTP statuses,
error codes, GrantRow counts (zero-mutation proof) and idempotency-record
counts (no binding consumed on rejection). Also traverses the stable-replay
path: create a grant, deactivate its principal/resource, then retry the same
key/body within retention and expect the registered 201 replay (not 404),
plus a distinct new-tuple duplicate expecting 409. Admitted creates use the
exact #480 matrix value bare "invoke" on llm_model (GRANT_ADMITTED_ACTIONS);
rejection probes keep non-admitted "invoke.x" behind missing/inactive refs so
404-before-422 and 403-before-lookup ordering still holds. Prints ONLY the JSON
transcript to stdout. CA8 automatic asserts then verify every case (status
plus grant_rows plus bindings plus error_code) against the pre-create
contract, report the summary to stderr, and exit non-zero on ANY violation
so the run FAILS instead of merely recording.
"""

import asyncio
import json
import os
import sys
import uuid

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://python_checks@python-checks-db:5432/python_checks",
)
AUDIT_KEY = "issue423-walkthrough-audit-key"
NS = "probe-423"


def sql_setup() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active') ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO principals (principal_id, kind, display_name, status, "
            "created_at, updated_at) VALUES ('admin-human', 'human', 'Admin', "
            "'active', now(), now()) ON CONFLICT DO NOTHING"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, "
            "resource_id, effect, status, created_at) VALUES "
            "('grant-admin-human-admin-write-grants', 'admin-human', 'admin.write', "
            "'administrative_control', 'grants', 'allow', 'active', now()) "
            "ON CONFLICT DO NOTHING"
        )
        connection.execute("DELETE FROM grants WHERE grant_id LIKE 'probe-423-%'")
        connection.execute(
            "DELETE FROM idempotency_records WHERE canonical_path = '/v1/grants' "
            "AND outcome ->> 'resource_id' LIKE 'probe-423-%'"
        )
        connection.execute("DELETE FROM credentials WHERE principal_id LIKE 'probe-423-%'")
        connection.execute("DELETE FROM principals WHERE principal_id LIKE 'probe-423-%'")
        connection.execute("DELETE FROM resources WHERE resource_id LIKE 'probe-423-%'")
        for principal_id, status in (
            (f"{NS}-active-human", "active"),
            (f"{NS}-inactive-human", "inactive"),
            (f"{NS}-restricted", "active"),
            (f"{NS}-replay-human", "active"),
            (f"{NS}-replay-human-2", "active"),
        ):
            connection.execute(
                "INSERT INTO principals (principal_id, kind, display_name, status, "
                "created_at, updated_at) VALUES (%s, 'human', %s, %s, now(), now())",
                (principal_id, principal_id, status),
            )
        for resource_id, status in (
            (f"{NS}-active-model", "active"),
            (f"{NS}-inactive-model", "inactive"),
            (f"{NS}-replay-model", "active"),
            (f"{NS}-replay-model-2", "active"),
        ):
            connection.execute(
                "INSERT INTO resources (resource_type, resource_id, status, "
                "model_alias_id, alias, concrete_model, router, inference_provider, "
                "owner_id, source, source_ref, display_name, visibility, "
                "description, tags) VALUES ('llm_model', %s, %s, %s, %s, "
                "'openai/gpt-4o-mini', 'openrouter', 'openai', %s, 'model_alias', "
                "%s, %s, 'private', '', '[]')",
                (
                    resource_id,
                    status,
                    f"alias-{resource_id}",
                    resource_id,
                    f"alias-{resource_id}",
                    f"alias-{resource_id}",
                    resource_id,
                ),
            )


async def mint_keys() -> tuple[str, str]:
    database = Database(DATABASE_URL)
    try:
        async with database.sessions() as session:
            admin = await CredentialRepository(session).issue("admin-human")
            restricted = await CredentialRepository(session).issue(f"{NS}-restricted")
            await session.commit()
            return admin.key, restricted.key
    finally:
        await database.dispose()


def counts(grant_id: str) -> tuple[int, int]:
    with psycopg.connect(DATABASE_URL) as connection:
        grants = connection.execute(
            "SELECT count(*) FROM grants WHERE grant_id = %s", (grant_id,)
        ).fetchone()[0]
        bindings = connection.execute(
            "SELECT count(*) FROM idempotency_records "
            "WHERE canonical_path = '/v1/grants' AND outcome ->> 'resource_id' = %s",
            (grant_id,),
        ).fetchone()[0]
    return grants, bindings


def fresh_key() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:32]


def grant_body(grant_id: str, principal_id: str, resource_id: str, action: str) -> dict:
    return {
        "grant_id": grant_id,
        "principal_id": principal_id,
        "action": action,
        "resource": {"resource_type": "llm_model", "resource_id": resource_id},
        "effect": "allow",
    }


def deactivate_principal(principal_id: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE principals SET status = 'inactive' WHERE principal_id = %s",
            (principal_id,),
        )


def deactivate_resource(resource_id: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE resources SET status = 'inactive' WHERE resource_id = %s",
            (resource_id,),
        )


def main() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    sql_setup()
    admin_key, restricted_key = asyncio.run(mint_keys())

    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    cases = []

    def attempt(name: str, body: dict, key: str, auth: str) -> dict:
        grant_id = body["grant_id"]
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/v1/grants",
                json=body,
                headers={
                    "Authorization": f"Bearer {auth}",
                    "Idempotency-Key": key,
                },
            )
        payload = response.json()
        grant_rows, bindings = counts(grant_id)
        return {
            "case": name,
            "status": response.status_code,
            "error_code": payload.get("error", {}).get("code"),
            "grant_rows": grant_rows,
            "idempotency_bindings": bindings,
        }

    cases.append(
        attempt(
            "missing principal",
            grant_body(f"{NS}-g-missing-p", f"{NS}-no-such", f"{NS}-active-model", "invoke.x"),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "inactive principal",
            grant_body(
                f"{NS}-g-inactive-p",
                f"{NS}-inactive-human",
                f"{NS}-active-model",
                "invoke.x",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "missing resource",
            grant_body(
                f"{NS}-g-missing-r",
                f"{NS}-active-human",
                f"{NS}-no-such",
                "invoke.x",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "inactive resource",
            grant_body(
                f"{NS}-g-inactive-r",
                f"{NS}-active-human",
                f"{NS}-inactive-model",
                "invoke.x",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "restricted caller before lookup",
            grant_body(f"{NS}-g-denied", f"{NS}-no-such", f"{NS}-no-such", "invoke.x"),
            fresh_key(),
            restricted_key,
        )
    )
    valid = grant_body(f"{NS}-g-valid", f"{NS}-active-human", f"{NS}-active-model", "invoke")
    valid_key = fresh_key()
    cases.append(attempt("valid create", valid, valid_key, admin_key))
    with TestClient(app, raise_server_exceptions=False) as client:
        replay = client.post(
            "/v1/grants",
            json=valid,
            headers={
                "Authorization": f"Bearer {admin_key}",
                "Idempotency-Key": valid_key,
            },
        )
    grant_rows, bindings = counts(valid["grant_id"])
    cases.append(
        {
            "case": "idempotent replay of valid create",
            "status": replay.status_code,
            "error_code": replay.json().get("error", {}).get("code"),
            "grant_rows": grant_rows,
            "idempotency_bindings": bindings,
        }
    )
    cases.append(
        attempt(
            "duplicate active tuple",
            grant_body(
                f"{NS}-g-duplicate",
                f"{NS}-active-human",
                f"{NS}-active-model",
                "invoke",
            ),
            fresh_key(),
            admin_key,
        )
    )
    replay_principal = grant_body(
        f"{NS}-g-replay-p",
        f"{NS}-replay-human",
        f"{NS}-replay-model",
        "invoke",
    )
    replay_principal_key = fresh_key()
    cases.append(
        attempt("replay principal setup create", replay_principal, replay_principal_key, admin_key)
    )
    deactivate_principal(f"{NS}-replay-human")
    cases.append(
        attempt(
            "stable replay after principal deactivated",
            replay_principal,
            replay_principal_key,
            admin_key,
        )
    )
    replay_resource = grant_body(
        f"{NS}-g-replay-r",
        f"{NS}-replay-human-2",
        f"{NS}-replay-model-2",
        "invoke",
    )
    replay_resource_key = fresh_key()
    cases.append(
        attempt("replay resource setup create", replay_resource, replay_resource_key, admin_key)
    )
    deactivate_resource(f"{NS}-replay-model-2")
    cases.append(
        attempt(
            "stable replay after resource deactivated",
            replay_resource,
            replay_resource_key,
            admin_key,
        )
    )
    print(json.dumps({"issue": 423, "cases": cases}, indent=2, sort_keys=True), flush=True)
    assert_transcript(cases)


def assert_transcript(cases: list) -> None:
    """CA8 automatic asserts: fail the run (non-zero exit) on ANY violation.

    Each expectation checks real endpoint state: HTTP status plus GrantRow
    count plus idempotency-binding count plus the error envelope code.
    Missing/inactive refs must be rejected with 404 resource_not_found and
    zero rows plus zero bindings; the restricted caller stays 403
    resource_unavailable before lookup; admitted bare-invoke creates must
    persist exactly one row with one binding; the same-key replay must stay
    stable; the new-tuple duplicate must stay 409; the stable replays after
    deactivation must stay 201 via the peek path. Summary goes to stderr so
    stdout stays pure JSON for transcript regeneration.
    """
    expected = {
        # Missing/inactive refs: rejected before claim, nothing persisted.
        "missing principal": (404, "resource_not_found", 0, 0),
        "inactive principal": (404, "resource_not_found", 0, 0),
        "missing resource": (404, "resource_not_found", 0, 0),
        "inactive resource": (404, "resource_not_found", 0, 0),
        # Denied caller before lookup.
        "restricted caller before lookup": (403, "resource_unavailable", 0, 0),
        # Admitted bare-invoke creates: one row and one binding.
        "valid create": (201, None, 1, 1),
        "idempotent replay of valid create": (201, None, 1, 1),
        # New-tuple duplicate keeps the published conflict envelope.
        "duplicate active tuple": (409, "idempotency_conflict", 0, 0),
        # Stable replays after deactivation keep 201 via the peek path.
        "replay principal setup create": (201, None, 1, 1),
        "stable replay after principal deactivated": (201, None, 1, 1),
        "replay resource setup create": (201, None, 1, 1),
        "stable replay after resource deactivated": (201, None, 1, 1),
    }
    by_name = {case["case"]: case for case in cases}
    failures = []
    for name, (want_status, want_code, want_rows, want_bindings) in expected.items():
        actual = by_name.get(name)
        if actual is None:
            failures.append(f"case {name!r}: missing from transcript")
            continue
        for field, want in (
            ("status", want_status),
            ("error_code", want_code),
            ("grant_rows", want_rows),
            ("idempotency_bindings", want_bindings),
        ):
            if actual.get(field) != want:
                failures.append(
                    f"case {name!r}: expected {field}={want!r} "
                    f"actual {field}={actual.get(field)!r} "
                    f"(status={actual.get('status')!r} "
                    f"error_code={actual.get('error_code')!r} "
                    f"grant_rows={actual.get('grant_rows')!r} "
                    f"bindings={actual.get('idempotency_bindings')!r})"
                )
    failed_names = {failure.split(":")[0] for failure in failures}
    passed_cases = len(expected) - len(failed_names)
    print(
        f"CA8 asserts: {passed_cases}/{len(expected)} cases passed, {len(failures)} violation(s)",
        file=sys.stderr,
    )
    for failure in failures:
        print(f"CA8 violation: {failure}", file=sys.stderr)
    if failures or len(cases) != len(expected):
        print(
            f"CA8 result: FAIL ({len(failures)} violation(s); "
            f"transcript cases={len(cases)} expected={len(expected)})",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"CA8 result: PASS (all {len(expected)} cases match the pre-create contract)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
