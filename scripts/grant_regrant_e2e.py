#!/usr/bin/env python3
"""E2E for #759 (compose.grants-e2e.yaml): a revoked grant can be granted again.

Phase `cycle`: as admin-human, grant restricted-harness `admin.read` on the principals list,
revoke it and grant it again under a new grant_id and Idempotency-Key. Its access goes
200 -> 403 -> 200 and the audit holds the three grant events. A second identical active grant
answers 409 `grant_conflict`; reusing the revoked grant_id answers 409 `grant_id_conflict`.
Then one core seed grant and one setup grant are revoked: their access goes 200 -> 403.
Phase `after-seed` (after the seed and provision_demo.py ran again): the seed is a reset to
zero. Its output names both grants as restored under `<id>-restored-1`, the access answers 200
again, the revoked rows stay as history and the audit holds each revoke (with its principal)
followed by the seed's restore (a `grants.create` without identity). /health/ready answers 200
on the partial unique index revision.
Phase `second-seed` (after one more run): nothing is restored twice.
Appends to $ARTIFACT_DIR/issue-759-e2e.txt; exits 1 on a failed check.
"""

import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

API, ADMIN = os.environ["API_URL"], os.environ["ADMIN_HUMAN_API_KEY"]
RESTRICTED = os.environ["RESTRICTED_HARNESS_API_KEY"]
DEMO = os.environ["DEMO_HUMAN_API_KEY"]
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
ARTIFACTS = Path(os.environ.get("ARTIFACT_DIR", "/tmp"))
# A core seed grant (seeds.py) and a setup grant (provision_demo.py), each with a cheap read.
SEED_GRANTS = ("grant-admin-human-admin-read-audit", "grant-setup-human-change-read")
RESTORED = tuple(f"{grant_id}-restored-1" for grant_id in SEED_GRANTS)
STAMP = secrets.token_hex(4)
lines: list[str] = []


def call(method: str, path: str, key: str, body: object = None) -> tuple[int, object]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if method == "POST":
        headers["Idempotency-Key"] = f"e2e-759-{STAMP}-{secrets.token_hex(8)}"
    data = None if body is None else json.dumps(body).encode()
    try:
        request = urllib.request.Request(API + path, data, headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def check(name: str, ok: bool, observed: object) -> None:
    line = f"{'PASS' if ok else 'FAIL'} {name}: {observed}"
    lines.append(line if len(line) <= 300 else line[:297] + "...")
    print(line)


def grant(grant_id: str) -> tuple[int, object]:
    body = {
        "grant_id": grant_id,
        "principal_id": "restricted-harness",
        "action": "admin.read",
        "resource": {"resource_type": "administrative_control", "resource_id": "principals"},
        "effect": "allow",
    }
    return call("POST", "/v1/grants", ADMIN, body)


def access() -> int:
    return call("GET", "/v1/principals?limit=1", RESTRICTED)[0]


def seed_access() -> list[int]:
    return [
        call("GET", "/v1/audit-events?principal_id=demo-human&limit=1", ADMIN)[0],
        call("GET", "/v1/changes?limit=1", DEMO)[0],
    ]


def seed_audit(db: psycopg.Connection) -> list[tuple]:
    """The last four grant events: who revoked and when, then the seed's restores."""
    rows = db.execute(
        "SELECT operation, response_status, stage, identity->>'principal_kind', "
        "left(identity->'principal_ref'->>'digest', 12), occurred_at FROM audit_events "
        "WHERE operation IN ('grants.create','grants.revoke') ORDER BY occurred_at DESC LIMIT 4"
    ).fetchall()
    return [(*row[:5], row[5].isoformat(timespec="seconds")) for row in reversed(rows)]


def cycle(db: psycopg.Connection) -> None:
    started = db.execute("SELECT now()").fetchone()[0]
    first, second = f"grant-e2e759-{STAMP}-a", f"grant-e2e759-{STAMP}-b"
    observed = [grant(first)[0], access()]
    observed += [call("DELETE", f"/v1/grants/{first}", ADMIN)[0], access()]
    observed += [grant(second)[0], access()]
    check(
        "grant, revoke, grant again: 201 200 204 403 201 200",
        observed == [201, 200, 204, 403, 201, 200],
        observed,
    )
    refused = [grant(f"grant-e2e759-{STAMP}-c"), grant(first)]
    check(
        "a duplicate active grant answers grant_conflict, a reused id grant_id_conflict",
        [(status, body["error"]["code"]) for status, body in refused]
        == [(409, "grant_conflict"), (409, "grant_id_conflict")],
        [body["error"] for _, body in refused],
    )
    rows = db.execute(
        "SELECT operation, response_status, reason_code FROM audit_events "
        "WHERE operation IN ('grants.create','grants.revoke') AND occurred_at >= %s "
        "ORDER BY occurred_at",
        (started,),
    ).fetchall()
    expected = [
        ("grants.create", 201),
        ("grants.revoke", 204),
        ("grants.create", 201),
        ("grants.create", 409),
        ("grants.create", 409),
    ]
    check(
        "the audit holds grant, revoke, grant again and both refusals",
        [r[:2] for r in rows] == expected,
        rows,
    )
    states = db.execute(
        "SELECT grant_id, status FROM grants WHERE grant_id LIKE %s ORDER BY grant_id",
        (f"grant-e2e759-{STAMP}-%",),
    ).fetchall()
    check(
        "both rows remain: the revoked one and the active one",
        states == [(first, "revoked"), (second, "active")],
        states,
    )
    before = seed_access()
    revoked = [call("DELETE", f"/v1/grants/{grant_id}", ADMIN)[0] for grant_id in SEED_GRANTS]
    observed = [before, revoked, seed_access()]
    check(
        "two seed-owned grants revoked before the seed reruns: access 200 -> 403",
        observed == [[200, 200], [204, 204], [403, 403]],
        observed,
    )


def after_seed(db: psycopg.Connection) -> None:
    output = (ARTIFACTS / "seed-rerun.txt").read_text()
    named = [
        f"seed reset: grant {grant_id} was revoked; restored as {grant_id}-restored-1" in output
        for grant_id in SEED_GRANTS
    ]
    check(
        "the seed rerun converged and names each restored grant",
        all(named) and "converged" in output,
        output.strip().splitlines(),
    )
    check("the access answers 200 again", seed_access() == [200, 200], seed_access())
    states = db.execute(
        "SELECT grant_id, status FROM grants WHERE grant_id = ANY(%s) ORDER BY grant_id",
        (list(SEED_GRANTS + RESTORED),),
    ).fetchall()
    expected = sorted([(g, "revoked") for g in SEED_GRANTS] + [(g, "active") for g in RESTORED])
    check("the revoked rows stay as history next to the restored ones", states == expected, states)
    audit = seed_audit(db)
    check(
        "the audit holds each human revoke, then the seed's restore without identity",
        [row[:4] for row in audit]
        == [("grants.revoke", 204, "authorization", "human")] * 2
        + [("grants.create", 201, "audit", None)] * 2,
        audit,
    )
    status, ready = call("GET", "/health/ready", ADMIN)
    version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    index = db.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_grants_active_direct'"
    ).fetchone()
    check(
        "/health/ready answers 200 on the new revision",
        status == 200 and version == "20261030_03",
        (status, ready, version),
    )
    check("uniqueness holds only among active grants", bool(index) and "WHERE" in index[0], index)


def second_seed(db: psycopg.Connection) -> None:
    output = (ARTIFACTS / "seed-rerun-2.txt").read_text()
    check(
        "a second seed run restores nothing",
        "seed reset:" not in output and "converged" in output,
        output.strip().splitlines(),
    )
    restored = db.execute(
        "SELECT grant_id FROM grants WHERE grant_id LIKE '%-restored-%' ORDER BY grant_id"
    ).fetchall()
    expected = [(grant_id,) for grant_id in sorted(RESTORED)]
    check("still one restored row per grant", restored == expected, restored)
    restores = db.execute(
        "SELECT count(*) FROM audit_events WHERE operation = 'grants.create' AND stage = 'audit'"
    ).fetchone()[0]
    check("still two restore audit events", restores == 2, restores)
    check("the access still answers 200", seed_access() == [200, 200], seed_access())


if __name__ == "__main__":
    phases = {"cycle": cycle, "after-seed": after_seed, "second-seed": second_seed}
    with psycopg.connect(DSN, autocommit=True) as connection:
        phases[sys.argv[1]](connection)
    with (ARTIFACTS / "issue-759-e2e.txt").open("a") as artifact:
        artifact.write(f"Issue #759 E2E, phase {sys.argv[1]}\n" + "\n".join(lines) + "\n")
    sys.exit(1 if any(line.startswith("FAIL") for line in lines) else 0)
