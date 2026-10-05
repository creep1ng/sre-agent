"""Issue #423 CA3 walkthrough probe: admitted-action validation evidence.

Containerized E2E: exercises POST /v1/grants against real FastAPI + PostgreSQL
with non-admitted actions (unknown root, cross-type, dotted invoke refinement,
dotted run refinement), ordering probes (bad action behind inactive resource
stays 404, behind a denied caller stays 403), an admitted bare invoke (201),
its stable same-key replay (201 via the peek path, which precedes the new-only
action guard), a new-tuple duplicate with an admitted action (409, unchanged),
a corrected retry of a rejected grant_id with a fresh key (201, proving no
binding was consumed on reject), and an admitted control-plane action (201).
Records real HTTP statuses, error codes, GrantRow counts (zero-mutation proof)
and idempotency-record counts (no binding consumed on rejection). Prints ONLY
the JSON transcript to stdout. CA8 automatic asserts then verify every case
(status plus grant_rows plus bindings plus error_code) against the admitted-
action contract, report the summary to stderr, and exit non-zero on ANY
violation so the run FAILS instead of merely recording.
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
AUDIT_KEY = "issue423-action-walkthrough-audit-key"
NS = "probe-423b"


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
        connection.execute("DELETE FROM grants WHERE grant_id LIKE 'probe-423b-%'")
        connection.execute(
            "DELETE FROM idempotency_records WHERE canonical_path = '/v1/grants' "
            "AND outcome ->> 'resource_id' LIKE 'probe-423b-%'"
        )
        connection.execute("DELETE FROM credentials WHERE principal_id LIKE 'probe-423b-%'")
        connection.execute("DELETE FROM principals WHERE principal_id LIKE 'probe-423b-%'")
        connection.execute("DELETE FROM resources WHERE resource_id LIKE 'probe-423b-%'")
        for principal_id, status in (
            (f"{NS}-active-human", "active"),
            (f"{NS}-inactive-human", "inactive"),
            (f"{NS}-restricted", "active"),
        ):
            connection.execute(
                "INSERT INTO principals (principal_id, kind, display_name, status, "
                "created_at, updated_at) VALUES (%s, 'human', %s, %s, now(), now())",
                (principal_id, principal_id, status),
            )
        for resource_id, status in (
            (f"{NS}-active-model", "active"),
            (f"{NS}-inactive-model", "inactive"),
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
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, "
            "owner_id, source, source_ref, display_name, visibility, "
            "description, tags) VALUES ('incident_workflow', %s, 'active', "
            "%s, 'incident_workflow', %s, %s, 'private', '', '[]') "
            "ON CONFLICT DO NOTHING",
            (
                f"{NS}-workflow",
                f"{NS}-owner",
                f"{NS}-workflow@1.0.0",
                f"{NS}-workflow",
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


def grant_body(
    grant_id: str,
    principal_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
) -> dict:
    return {
        "grant_id": grant_id,
        "principal_id": principal_id,
        "action": action,
        "resource": {"resource_type": resource_type, "resource_id": resource_id},
        "effect": "allow",
    }


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

    rejected_id = f"{NS}-g-unknown-action"
    cases.append(
        attempt(
            "unknown action root",
            grant_body(
                rejected_id, f"{NS}-active-human", "llm_model", f"{NS}-active-model", "delete"
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "cross-type action over llm_model",
            grant_body(
                f"{NS}-g-cross-type",
                f"{NS}-active-human",
                "llm_model",
                f"{NS}-active-model",
                "mcp.invoke",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "cross-type contract action over llm_model",
            grant_body(
                f"{NS}-g-cross-contract",
                f"{NS}-active-human",
                "llm_model",
                f"{NS}-active-model",
                "bok.search",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "dotted invoke refinement is rejected",
            grant_body(
                f"{NS}-g-invoke-delete",
                f"{NS}-active-human",
                "llm_model",
                f"{NS}-active-model",
                "invoke.delete",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "dotted run refinement is rejected",
            grant_body(
                f"{NS}-g-run-unpublished",
                f"{NS}-active-human",
                "incident_workflow",
                f"{NS}-workflow",
                "run.start.unpublished",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "inactive resource plus bad action orders 404 first",
            grant_body(
                f"{NS}-g-ordering",
                f"{NS}-active-human",
                "llm_model",
                f"{NS}-inactive-model",
                "delete",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "restricted caller plus bad action stays 403",
            grant_body(
                f"{NS}-g-denied-action",
                f"{NS}-no-such",
                "llm_model",
                f"{NS}-no-such",
                "delete",
            ),
            fresh_key(),
            restricted_key,
        )
    )
    valid = grant_body(
        f"{NS}-g-valid",
        f"{NS}-active-human",
        "llm_model",
        f"{NS}-active-model",
        "invoke",
    )
    valid_key = fresh_key()
    cases.append(attempt("admitted bare invoke creates", valid, valid_key, admin_key))
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
            "case": "stable replay of admitted create",
            "status": replay.status_code,
            "error_code": replay.json().get("error", {}).get("code"),
            "grant_rows": grant_rows,
            "idempotency_bindings": bindings,
        }
    )
    cases.append(
        attempt(
            "new-tuple duplicate with admitted action",
            grant_body(
                f"{NS}-g-duplicate",
                f"{NS}-active-human",
                "llm_model",
                f"{NS}-active-model",
                "invoke",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "corrected retry of rejected grant_id with fresh key",
            grant_body(
                rejected_id,
                f"{NS}-active-human",
                "llm_model",
                f"{NS}-active-model",
                "admin.read",
            ),
            fresh_key(),
            admin_key,
        )
    )
    cases.append(
        attempt(
            "admitted control-plane action creates",
            grant_body(
                f"{NS}-g-control",
                f"{NS}-active-human",
                "administrative_control",
                "grants",
                "admin.write",
            ),
            fresh_key(),
            admin_key,
        )
    )
    print(json.dumps({"issue": 423, "cases": cases}, indent=2, sort_keys=True), flush=True)
    assert_transcript(cases)


def assert_transcript(cases: list) -> None:
    """CA8 automatic asserts: fail the run (non-zero exit) on ANY violation.

    Each expectation checks real endpoint state: HTTP status plus GrantRow
    count plus idempotency-binding count plus the error envelope code.
    Non-admitted actions must be rejected with 422 validation_error and zero
    rows plus zero bindings; admitted creates must persist exactly one row
    with one binding; the same-key replay must stay stable; the new-tuple
    duplicate must stay 409. Summary goes to stderr so stdout stays pure
    JSON for transcript regeneration.
    """
    expected = {
        # Non-admitted actions: rejected before claim, nothing persisted.
        "unknown action root": (422, "validation_error", 0, 0),
        "cross-type action over llm_model": (422, "validation_error", 0, 0),
        "cross-type contract action over llm_model": (422, "validation_error", 0, 0),
        "dotted invoke refinement is rejected": (422, "validation_error", 0, 0),
        "dotted run refinement is rejected": (422, "validation_error", 0, 0),
        # Ordering probes: 404 before 422, 403 before lookup.
        "inactive resource plus bad action orders 404 first": (
            404,
            "resource_not_found",
            0,
            0,
        ),
        "restricted caller plus bad action stays 403": (
            403,
            "resource_unavailable",
            0,
            0,
        ),
        # Admitted actions: created with one row and one binding.
        "admitted bare invoke creates": (201, None, 1, 1),
        "stable replay of admitted create": (201, None, 1, 1),
        # New-tuple duplicate keeps the published conflict envelope.
        "new-tuple duplicate with admitted action": (
            409,
            "idempotency_conflict",
            0,
            0,
        ),
        # Corrected retry with a fresh key succeeds: rejection consumed nothing.
        "corrected retry of rejected grant_id with fresh key": (201, None, 1, 1),
        "admitted control-plane action creates": (201, None, 1, 1),
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
        f"CA8 result: PASS (all {len(expected)} cases match the admitted-action contract)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
