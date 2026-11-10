"""Read independently persisted receiver stores and live runtime SQL after E2E."""

import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg

directory = Path(sys.argv[1] if len(sys.argv) > 1 else "/proof")
scenarios = (
    "success",
    "reject",
    "pre_dispatch",
    "5xx",
    "loss",
    "timeout",
    "before_dispatch",
    "before_effect",
    "after_effect",
    "before_commit",
    "concurrent",
)
records = []
for scenario in scenarios:
    proof = json.loads((directory / f"{scenario}.json").read_text())
    ledger = directory / f"{scenario}-receiver.sqlite"
    with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        counter = db.execute("SELECT value FROM counter").fetchone()[0]
        operations = [dict(row) for row in db.execute("SELECT * FROM operations ORDER BY sequence")]
    assert counter == proof["receiver_final"]["counter"]
    assert operations == proof["receiver_final"]["operations"]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as db:
        receipts = db.execute(
            "SELECT payload->'dispatch_receipt' FROM incident.run_events "
            "WHERE run_id=%s AND kind='dispatch_receipt' ORDER BY sequence",
            (proof["read_state"]["run_id"],),
        ).fetchall()
        results = db.execute(
            "SELECT count(*) FROM incident.run_events "
            "WHERE run_id=%s AND kind='investigation_result'",
            (proof["read_state"]["run_id"],),
        ).fetchone()[0]
    assert [row[0] for row in receipts] == proof["terminal_receipts"]
    assert results == (1 if scenario in {"success", "concurrent"} else 0)
    records.append(
        {
            "scenario": scenario,
            "tested_sha": proof["tested_sha"],
            "base_sha": proof["base_sha"],
            "run_id": proof["read_state"]["run_id"],
            "receiver_counter_sql": counter,
            "receiver_operations_sql": operations,
            "runtime_receipts_sql": [row[0] for row in receipts],
            "runtime_result_count_sql": results,
        }
    )
    print(
        f"SQL_INSPECTION {scenario}: receiver counter={counter}, sent={len(operations)}, "
        f"runtime={receipts[-1][0]['status']}, result_events={results}"
    )
(directory / "runtime-sql.json").write_text(json.dumps(records, indent=2) + "\n")
print("SQL_INSPECTION: persisted receiver and live runtime records agree for all scenarios")
