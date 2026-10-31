"""E2E phases of the Telegram channel (#766, #767), driven by scripts/run_telegram_e2e.sh.

Runs inside the seed container on the compose network: it plays the Telegram users through
fake-telegram, starts investigations through the real API, reads the outbox with SQL and
appends every observation to /artifacts/telegram-e2e.json. Any failed check exits non-zero.
"""

from __future__ import annotations

import asyncio
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
            "links lists the operator chat and its human without codes": re.fullmatch(
                rf"{OPERATOR} linked \S+ as demo-human", before
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


# #767: four mitigation proposals for the broken sre-checkout deploy, one per journey.
JOURNEYS = ("approve", "reject", "console", "unlinked")
PROPOSALS = Path("/artifacts/proposals.json")
TOKEN = re.compile(r"^[ar]:[0-9a-f]{32}$")


async def _propose(stamp: str) -> dict[str, dict[str, str]]:
    sys.path.insert(0, "/app/src")
    from sre_agent.application import INCIDENT_WORKFLOW_PATH
    from sre_agent.incident.runtime import ActorReference, IncidentCommand, IncidentRuntime
    from sre_agent.incident.workflow import load_incident_workflow
    from sre_agent.persistence.database import Database
    from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

    database, now = Database(os.environ["DATABASE_URL"]), datetime.now().astimezone()
    runtime = IncidentRuntime(
        load_incident_workflow(INCIDENT_WORKFLOW_PATH),
        lambda: PostgresIncidentUnitOfWork(database),
    )
    alert = {"alert_id": f"alt-767-{stamp}", "service": "sre-checkout", "severity": "sev2"}
    alert |= {"status": "triaged", "observed_at": "2026-10-31T10:05:00Z"}
    alert |= {"summary": "Checkout 5xx above 5 %.", "source": "grafana-alerting"}
    evidence = [{"evidence_id": "ev_767", "summary": "sre-checkout 5xx at 12 % since 10:01."}]
    hypothesis = {"hypothesis_id": "hyp_767", "supporting_evidence": ["ev_767"]}
    hypothesis["statement"] = "El despliegue v2.4.1 de sre-checkout rompió el pago."
    proposals = {}
    try:
        for journey in JOURNEYS:
            incident_id, run_id = f"inc-767-{journey}-{stamp}", f"run_767{journey[:4]}{stamp}"
            state = {"workflow_id": "incident-response", "workflow_version": "1.0.0"}
            state |= {"state": "active", "severity": "sev2", "impact": "Checkout falla."}
            state |= {"alert": alert, "hypotheses": [], "evidence": [], "approvals": []}
            state |= {"mitigation_strategy": None, "postmortem": None}
            mitigation = {"mitigation_id": f"mit_767{journey}", "approval_status": "pending"}
            mitigation |= {"description": "Volver sre-checkout a la versión anterior, v2.4.0."}
            mitigation |= {"risk": "low", "operation": "deployment.rollback"}
            mitigation |= {"based_on_hypothesis": "hyp_767"}
            async with PostgresIncidentUnitOfWork(database) as work:
                state["updated_at"] = now.isoformat()
                await work.incidents.add(incident_id, state, now=now)
                run = {"workflow_version": "1.0.0", "current_state": "active", "status": "running"}
                await work.runs.add(run_id, incident_id, run, now=now)
            agent = ActorReference(principal_id="incident-harness")
            hypothesize = {"hypotheses": [hypothesis], "evidence": evidence}
            steps = (
                ("start_investigation", "system", None, {}),
                ("continue_investigation", "agent", "continue_investigation",
                 {"remaining_step_budget": 2, "incident_patch": hypothesize}),
                ("propose_mitigation", "agent", "propose_mitigation",
                 {"incident_patch": {"mitigation_strategy": mitigation, "evidence": evidence}}),
            )  # fmt: skip
            for step, actor, outcome, inputs in steps:
                await runtime.execute(
                    IncidentCommand(
                        f"e2e-767-{step}-{run_id}", incident_id, run_id, step, actor,
                        actor_reference=agent if outcome else None, outcome=outcome,
                        inputs=inputs or None,
                    )
                )  # fmt: skip
            proposals[journey] = {"incident_id": incident_id, "run_id": run_id}
    finally:
        await database.dispose()
    return proposals


def proposals(stamp: str) -> None:
    sql(
        "INSERT INTO incident.change_events (change_id, source, external_id, service, kind, "
        "status, version, occurred_at, recorded_at, recorded_by) VALUES (%s, 'e2e', %s, "
        "'sre-checkout', 'deploy', 'succeeded', 'v2.4.1', '2026-10-31T10:00:00Z', now(), "
        "'telegram-e2e') RETURNING change_id",
        f"chg_767_{stamp}",
        f"deploy-{stamp}",
    )
    created = asyncio.run(_propose(stamp))
    PROPOSALS.write_text(json.dumps(created))
    messages = wait_for(lambda: len(prompts()) == len(JOURNEYS) and prompts())
    buttons = [[label for label, _ in m["buttons"][0]] for m in messages]
    data = [d for m in messages for _, d in m["buttons"][0]]
    marked = [m for m in sent() if "🟠" in m["text"]]
    record(
        "proposals",
        {"proposals": created, "messages": messages},
        {
            "one decision message per proposal reaches the operator chat": sorted(
                m["text"].splitlines()[0] for m in messages
            )
            == sorted(f"🟠 Decisión pendiente: {p['incident_id']}" for p in created.values()),
            "it names service, cause, suspect change, proposal and risk": all(
                all(
                    part in m["text"]
                    for part in (
                        "Servicio: sre-checkout",
                        "Causa: El despliegue v2.4.1",
                        "Cambio sospechoso: despliegue v2.4.1",
                        "Propuesta: Volver sre-checkout a la versión anterior",
                        "Riesgo: bajo",
                        "Detalle: operación del catálogo deployment.rollback",
                    )
                )
                for m in messages
            ),
            "each offers Aprobar and Rechazar": buttons == [["Aprobar", "Rechazar"]] * 4,
            "the callback data is opaque": all(
                TOKEN.fullmatch(d) and "inc-" not in d and "run_" not in d for d in data
            ),
            "only decision messages carry the decision marker": marked == messages,
        },
    )


def prompts(chat_id: int = OPERATOR) -> list[dict[str, Any]]:
    return [m for m in sent(chat_id) if m["text"].startswith("🟠")]


def prompt(journey: str) -> dict[str, Any]:
    incident_id = json.loads(PROPOSALS.read_text())[journey]["incident_id"]
    # Pending or decided, the first line names the incident.
    return next(m for m in sent(OPERATOR) if m["text"].split("\n")[0].endswith(incident_id))


def tap(chat_id: int, message_id: int, data: str) -> str:
    """Tap a button as Telegram reports it, and wait for the bot's answer to that tap."""
    body = {"chat_id": chat_id, "message_id": message_id, "data": data}
    query = http("POST", f"{FAKE}/_test/taps", body)["callback_query"]["id"]

    def answered() -> str | None:
        answers = http("GET", f"{FAKE}/_test/answers")["answers"]
        return next((a["text"] for a in answers if a["callback_query_id"] == query), None)

    return wait_for(answered)


def press(chat_id: int, message: dict[str, Any], label: str) -> str:
    return tap(chat_id, message["message_id"], dict(message["buttons"][0])[label])


def decisions(journey: str) -> list[tuple]:
    run_id = json.loads(PROPOSALS.read_text())[journey]["run_id"]
    return sql(
        "SELECT document->>'transition_id', document->>'outcome', "
        "document->'actor_reference'->>'principal_id', document->>'actor', "
        "document->>'channel', decided_at FROM incident.decisions WHERE run_id=%s "
        "AND document->>'transition_id' IN ('apply_mitigation','reject_mitigation') "
        "ORDER BY decided_at",
        run_id,
    )


def approval_status(journey: str) -> str:
    incident_id = json.loads(PROPOSALS.read_text())[journey]["incident_id"]
    return sql(
        "SELECT state->'mitigation_strategy'->>'approval_status' FROM incident.incidents "
        "WHERE incident_id=%s",
        incident_id,
    )[0][0]


def approve() -> None:
    message = prompt("approve")
    Path("/artifacts/approve-message.json").write_text(json.dumps(message))
    answer, edited = press(OPERATOR, message, "Aprobar"), prompt("approve")
    rows = decisions("approve")
    record(
        "approve",
        {"answer": answer, "edited": edited, "decisions": rows},
        {
            "the tap records one approval": [r[:2] for r in rows]
            == [("apply_mitigation", "approve")],
            "as the linked human, through Telegram": rows[0][2:5]
            == ("demo-human", "human", "telegram"),
            "the mitigation is approved": approval_status("approve") == "approved",
            "the answer says who decided": answer.startswith("Aprobada por Demo")
            and "desde Telegram" in answer,
            "the message shows who decided and loses its buttons": edited["buttons"] == []
            and edited["text"].endswith(answer),
        },
    )


def double_tap() -> None:
    # The buttons as first sent: a client that has not refreshed the message can still tap them.
    message = json.loads(Path("/artifacts/approve-message.json").read_text())
    again, reject = press(OPERATOR, message, "Aprobar"), press(OPERATOR, message, "Rechazar")
    rows = decisions("approve")
    record(
        "double_tap",
        {"answers": [again, reject], "decisions": rows},
        {
            "a second tap decides nothing more": len(rows) == 1,
            "both taps answer the decision already taken": again == reject
            and again.startswith("Aprobada por"),
            "the mitigation stays approved": approval_status("approve") == "approved",
        },
    )


def stranger() -> None:
    message = prompt("unlinked")
    answer = press(STRANGER, message, "Aprobar")
    record(
        "stranger",
        {"answer": answer, "decisions": decisions("unlinked")},
        {
            "a tap from an unlinked chat decides nothing": decisions("unlinked") == [],
            "it is told the chat is not linked": "no está vinculado" in answer,
            "the mitigation is still pending": approval_status("unlinked") == "pending",
        },
    )


def console() -> None:
    created = json.loads(PROPOSALS.read_text())["console"]
    version = sql(
        "SELECT version FROM incident.incidents WHERE incident_id=%s", created["incident_id"]
    )[0][0]
    # What the console's Decisions view sends for «Rechazar».
    http(
        "POST",
        f"{API}/v1/incidents/{created['incident_id']}/runs/{created['run_id']}/commands",
        {
            "command": "reject_mitigation",
            "actor": "human",
            "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
            "expected_incident_version": version,
        },
        {
            "Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"],
            "Idempotency-Key": f"console-{created['run_id']}",
        },
    )
    answer, edited = press(OPERATOR, prompt("console"), "Aprobar"), prompt("console")
    rows = decisions("console")
    record(
        "console",
        {"answer": answer, "edited": edited, "decisions": rows},
        {
            "Aprobar after a console rejection approves nothing": [r[:2] for r in rows]
            == [("reject_mitigation", "reject")],
            "the console decision has no chat channel": rows[0][4] is None,
            "the mitigation stays rejected": approval_status("console") == "rejected",
            "the answer gives the current state": answer.startswith("Rechazada por")
            and "desde la consola" in answer,
            "the message shows it and loses its buttons": edited["buttons"] == [],
        },
    )


def reject() -> None:
    answer, edited = press(OPERATOR, prompt("reject"), "Rechazar"), prompt("reject")
    rows = decisions("reject")
    record(
        "reject",
        {"answer": answer, "edited": edited, "decisions": rows},
        {
            "the tap records one rejection": [r[:2] for r in rows]
            == [("reject_mitigation", "reject")],
            "as the linked human, through Telegram": rows[0][2:5]
            == ("demo-human", "human", "telegram"),
            "the mitigation is rejected": approval_status("reject") == "rejected",
            "the answer and the message say who rejected": answer.startswith("Rechazada por")
            and edited["text"].endswith(answer)
            and edited["buttons"] == [],
        },
    )


def unlinked_tap() -> None:
    answer = press(OPERATOR, prompt("unlinked"), "Aprobar")
    audit = sql(
        "SELECT d.incident_id, d.document->>'transition_id', d.document->>'outcome', "
        "d.document->'actor_reference'->>'principal_id', d.document->>'channel', d.decided_at "
        "FROM incident.decisions d WHERE d.incident_id LIKE 'inc-767-%%' AND "
        "d.document->>'actor' = 'human' ORDER BY d.decided_at"
    )
    record(
        "unlinked_tap",
        {"answer": answer, "decision_audit": audit},
        {
            "a tap after unlinking decides nothing": decisions("unlinked") == [],
            "it is told the chat is not linked": "no está vinculado" in answer,
            "the mitigation is still pending": approval_status("unlinked") == "pending",
            "the audit names the human and the channel of every decision": [
                (row[1], row[3], row[4]) for row in audit
            ]
            == [
                ("apply_mitigation", "demo-human", "telegram"),
                ("reject_mitigation", "demo-human", None),
                ("reject_mitigation", "demo-human", "telegram"),
            ],
        },
    )


if __name__ == "__main__":
    phase, *arguments = sys.argv[1:]
    phases = {"linking": linking, "dispatch": dispatch, "pending": pending}
    phases |= {"delivered": delivered, "unlinked": unlinked, "proposals": proposals}
    phases |= {"approve": approve, "double_tap": double_tap, "stranger": stranger}
    phases |= {"console": console, "reject": reject, "unlinked_tap": unlinked_tap}
    phases[phase](*arguments)
