"""E2E phases of the Telegram channel (#766), driven by scripts/run_telegram_e2e.sh.

Runs inside the seed container on the compose network: it plays the Telegram users through
fake-telegram, starts investigations through the real API, reads the outbox with SQL and
appends every observation to /artifacts/telegram-e2e.json. Any failed check exits non-zero.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

FAKE, API = "http://fake-telegram:8081", "http://api:8000"
ARTIFACT = Path("/artifacts/telegram-e2e.json")
OPERATOR, STRANGER, LATECOMER, EXPIRED = 222, 111, 333, 444


def http(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data, {"Content-Type": "application/json"} | (headers or {}), method=method
    )
    with urllib.request.urlopen(request, timeout=120) as reply:
        return json.load(reply)


def say(chat_id: int, text: str) -> None:
    http("POST", f"{FAKE}/_test/messages", {"chat_id": chat_id, "text": text})


def sent(chat_id: int | None = None) -> list[dict[str, Any]]:
    return [m for m in http("GET", f"{FAKE}/_test/sent") if chat_id in (None, m["chat_id"])]


def wait_for(predicate, seconds: float = 30) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(0.1)
    raise SystemExit(f"timed out after {seconds}s")


def sql(query: str, *args: Any) -> list[tuple]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        return connection.execute(query, args).fetchall()


def record(section: str, value: Any, checks: dict[str, bool]) -> None:
    document = json.loads(ARTIFACT.read_text()) if ARTIFACT.exists() else {}
    document[section] = {"observed": value, "checks": checks}
    ARTIFACT.write_text(json.dumps(document, indent=2, default=str))
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {section}: {name}")
    if not all(checks.values()):
        raise SystemExit(1)


def start_run(incident_id: str) -> str:
    started = http(
        "POST",
        f"{API}/v1/incidents/{incident_id}/runs",
        {"workflow_version": "1.0.0", "objective": "investigate"},
        {
            "Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"],
            "Idempotency-Key": f"telegram-e2e-{incident_id}",
        },
    )
    return started["run_id"]


def incident_texts(chat_id: int) -> list[str]:
    return [m["text"] for m in sent(chat_id) if "inc-" in m["text"] or "run_" in m["text"]]


def linking(code: str, expired_code: str) -> None:
    say(STRANGER, "hola, ¿qué incidentes hay?")
    say(STRANGER, "¿hola?")
    say(OPERATOR, f"/start {code}")
    wait_for(lambda: sent(OPERATOR) and sent(STRANGER))
    say(LATECOMER, f"/start {code}")
    say(EXPIRED, f"/start {expired_code}")
    wait_for(lambda: sent(LATECOMER) and sent(EXPIRED))
    links = sql("SELECT chat_id FROM incident.chat_links ORDER BY chat_id")
    record(
        "linking",
        {"replies": sent(), "chat_links": links},
        {
            "the code links the operator chat": "vinculado" in sent(OPERATOR)[0]["text"],
            "a used code is rejected": "no es válido" in sent(LATECOMER)[0]["text"],
            "an expired code is rejected": "no es válido" in sent(EXPIRED)[0]["text"],
            "an unlinked chat is told to link": "no está vinculado" in sent(STRANGER)[0]["text"],
            "an unlinked chat is told only once": len(sent(STRANGER)) == 1,
            "only the operator chat is allowed": links == [(OPERATOR,)],
        },
    )


def dispatch(incident_id: str) -> None:
    run_id = start_run(incident_id)

    def ours() -> list[dict[str, Any]]:
        return [m for m in sent(OPERATOR) if run_id in m["text"]]

    messages = wait_for(lambda: len(ours()) == 2 and ours())
    (intent_at,) = sql(
        "SELECT occurred_at FROM incident.run_events WHERE run_id=%s AND kind='dispatch_receipt' "
        "AND payload->'dispatch_receipt'->>'phase'='intent'",
        run_id,
    )[0]
    latency = (datetime.fromisoformat(messages[0]["received_at"]) - intent_at).total_seconds()
    record(
        "dispatch",
        {
            "run_id": run_id,
            "dispatched_at": intent_at,
            "messages": messages,
            "ack_latency_seconds": latency,
        },
        {
            "the acknowledgment arrives first": messages[0]["text"].startswith("Investigando"),
            f"the acknowledgment arrives in under 5 s ({latency:.3f} s)": 0 <= latency < 5,
            "the conclusion follows": messages[1]["text"].startswith("Investigación terminada"),
            "the conclusion gives a readable reason": "Sin conclusión (" not in messages[1]["text"],
            "unlinked chats receive no incident information": not any(
                incident_texts(chat) for chat in (STRANGER, LATECOMER, EXPIRED)
            ),
        },
    )


def outbox(run_id: str) -> list[tuple]:
    return sql(
        "SELECT message_id, chat_id, kind, attempts, sent_at IS NOT NULL, last_error "
        "FROM incident.chat_outbox WHERE payload->>'run_id'=%s ORDER BY message_id",
        run_id,
    )


def pending(incident_id: str) -> None:
    run_id = start_run(incident_id)
    Path("/artifacts/pending-run").write_text(run_id)
    rows = outbox(run_id)
    http("POST", f"{FAKE}/_test/fail-sends", {"count": 1})
    record(
        "pending",
        {"run_id": run_id, "outbox": rows},
        {
            "both messages wait in the outbox while the gateway is down": [
                (r[2], r[4]) for r in rows
            ]
            == [("investigation_ack", False), ("investigation_conclusion", False)],
            "nothing about the run reached Telegram": not any(
                run_id in t for t in incident_texts(OPERATOR)
            ),
        },
    )


def delivered(section: str) -> None:
    run_id = Path("/artifacts/pending-run").read_text()
    wait_for(lambda: len([m for m in sent(OPERATOR) if run_id in m["text"]]) >= 2)
    time.sleep(3)  # anything sent twice would arrive by now
    rows, messages = outbox(run_id), [m for m in sent(OPERATOR) if run_id in m["text"]]
    every = sql("SELECT count(*) FROM incident.chat_outbox WHERE sent_at IS NOT NULL")[0][0]
    record(
        section,
        {"outbox": rows, "messages": messages, "sent_rows": every, "fake_messages": len(sent())},
        {
            "each pending message arrives once across the restarts": len(messages) == 2,
            "the failed first send was retried": rows[0][3] == 2 and rows[0][4],
            "every sent outbox row reached Telegram once": every == len(sent()),
        },
    )


def unlinked(incident_id: str) -> None:
    before, removed, after = (
        Path(f"/artifacts/{name}.txt").read_text().strip()
        for name in ("links-before", "unlink", "links-after")
    )
    run_id = start_run(incident_id)
    wait_for(
        lambda: sql(
            "SELECT 1 FROM incident.run_events WHERE run_id=%s AND kind='dispatch_receipt' "
            "AND payload->'dispatch_receipt'->>'phase'='outcome'",
            run_id,
        ),
        60,
    )
    time.sleep(3)  # a message queued for the run would be sent by now
    record(
        "unlinked",
        {"links_before": before, "unlink": removed, "links_after": after, "run_id": run_id},
        {
            "links lists the operator chat without codes": re.fullmatch(
                rf"{OPERATOR} linked \S+", before
            )
            is not None,
            "unlink revokes the operator chat": removed == f"chat {OPERATOR} unlinked",
            "no chat is linked afterwards": after == "no chats",
            "nothing about the new run is queued": outbox(run_id) == [],
            "nothing about the new run reaches Telegram": not any(
                run_id in m["text"] for m in sent()
            ),
        },
    )


if __name__ == "__main__":
    phase, *arguments = sys.argv[1:]
    phases = {"linking": linking, "dispatch": dispatch, "pending": pending}
    phases |= {"delivered": delivered, "unlinked": unlinked}
    phases[phase](*arguments)
