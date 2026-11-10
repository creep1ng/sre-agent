#!/usr/bin/env python3
"""Bounded PostgreSQL fault controller for the issue #25 connected UI proof."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg

ROOT = Path("/evidence")
ORIGINAL_TABLE = "public.audit_events"
FAULT_TABLE = "public.audit_events_issue25_fault"


def safe_settings():
    from sre_agent.settings import Settings

    env = {key: value for key, value in os.environ.items() if not key.startswith("OPENROUTER")}
    settings = Settings.from_environment(env)
    parsed = urlsplit(settings.database_url)
    if (
        parsed.hostname != "db"
        or parsed.port not in (None, 5432)
        or unquote(parsed.path.lstrip("/")) != "audit25_closure"
    ):
        raise RuntimeError("database target is not the isolated issue-25 database")
    return settings


def table_state(connection):
    original, fault = connection.execute(
        "SELECT to_regclass(%s) IS NOT NULL, to_regclass(%s) IS NOT NULL",
        (ORIGINAL_TABLE, FAULT_TABLE),
    ).fetchone()
    return bool(original), bool(fault)


def wait_for(path: Path, timeout_seconds: int):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.2)
    raise TimeoutError("controlled query-fault marker timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="maximum wait for each browser marker (default: 120; maximum: 180)",
    )
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 180:
        parser.error("--timeout-seconds must be between 1 and 180")

    settings = safe_settings()
    ready = ROOT / "query-fault-ready.json"
    active = ROOT / "query-fault-active"
    done = ROOT / "query-fault-done"
    failed = ROOT / "issue-25-query-failure-failed.json"

    # A prior interrupted run must not activate a later browser accidentally.
    active.unlink(missing_ok=True)
    done.unlink(missing_ok=True)
    rename_attempted = False
    try:
        wait_for(ready, args.timeout_seconds)
        with psycopg.connect(
            settings.database_url, autocommit=True, connect_timeout=5
        ) as connection:
            if table_state(connection) != (True, False):
                raise RuntimeError("audit table is not in its expected initial state")
            # Arm cleanup before sending DDL so an ambiguous client-side error
            # after a committed rename still triggers a database-state check.
            rename_attempted = True
            connection.execute(
                "ALTER TABLE public.audit_events RENAME TO audit_events_issue25_fault"
            )

        # If this write fails (for example, an unusable evidence mount), finally
        # still restores the table because the rename has already committed.
        active.write_text("active\n", encoding="utf-8")
        wait_for(done, args.timeout_seconds)
        if failed.is_file():
            raise RuntimeError("connected browser capture reported a failure")
    finally:
        if rename_attempted:
            # Inspect actual database state, not only the local flag: the server
            # may commit the rename even if the client loses its acknowledgement.
            with psycopg.connect(
                settings.database_url, autocommit=True, connect_timeout=5
            ) as connection:
                current = table_state(connection)
                if current == (False, True):
                    connection.execute(
                        "ALTER TABLE public.audit_events_issue25_fault RENAME TO audit_events"
                    )
                elif current != (True, False):
                    raise RuntimeError("audit table names are not safely recoverable")
                if table_state(connection) != (True, False):
                    raise RuntimeError("audit table restoration could not be verified")
        active.unlink(missing_ok=True)

    print("Connected query-fault handshake completed; audit table restored and verified.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda signum, _frame: sys.exit(128 + signum))
    try:
        main()
    except Exception as failure:
        # Do not include driver errors, connection details, or environment values.
        print(
            "issue-25 query-fault controller failed; cleanup was attempted "
            f"({type(failure).__name__})",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
