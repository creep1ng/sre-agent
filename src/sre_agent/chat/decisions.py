"""Approve or reject a proposed mitigation from a linked chat with one tap (issue #767).

A button's callback data is `a:` or `r:` plus the opaque token of one decision message; the
token is bound to the link it was sent to (chat and Telegram user; unlinking kills it) and to
the incident, run, proposal and incident version that message shows. The gateway only verifies
the tap and queues the console's own command for the human principal the link names
(`chat/taps.py`, #722): the API carries it out through `RunCommandService`, with the same grant
check, attribution, executor and runtime, recorded with the channel `telegram`. The runtime
keeps a second tap from deciding twice: the same button replays its first result, and any later
tap finds the reviewed version stale. When the incident changed while the proposal still waits,
the chat gets the proposal again with a fresh token bound to the current version.
"""

from __future__ import annotations

import asyncio
import re
from time import monotonic

from sqlalchemy import text

from sre_agent.chat.outbox import CHANGED, REFUSALS, asks_decision, mitigation_decision
from sre_agent.chat.taps import INCIDENT_CHANGED, queue_tap, tap_outcome
from sre_agent.persistence.database import Database
from sre_agent.vocabulary import RunCommand

CALLBACK = re.compile(r"^([ar]):([0-9a-f]{32})$")
COMMANDS = {"a": RunCommand.APPROVE_MITIGATION, "r": RunCommand.REJECT_MITIGATION}
NOT_DECIDED = {
    401: "Tu usuario ya no está activo: no se decidió nada.",
    403: "No tienes permiso para decidir esta mitigación: no se decidió nada.",
}
# Telegram keeps a callback waiting for its answer for a few seconds only; a rollback may take
# longer, and then the decision message tells the result.
WAIT_SECONDS = 8
WORKING = "Recibido: aplicando tu decisión; el mensaje se actualizará con el resultado."


class ChatDecisions:
    def __init__(self, database: Database, wait_seconds: float = WAIT_SECONDS) -> None:
        self.database, self.wait_seconds = database, wait_seconds

    async def tap(self, chat_id: int, user_id: int, data: str) -> str:
        """Queue the decision once and answer with its outcome, or that it is under way."""
        match = CALLBACK.fullmatch(data)
        if match is None:
            return "Este botón no es válido: no se decidió nada."
        choice, token = match.groups()
        async with self.database.transaction() as session:
            link = (
                await session.execute(
                    text("""SELECT l.principal_id, p.display_name, m.payload, m.message_id
                        FROM incident.chat_links l
                        JOIN incident.chat_outbox m ON m.chat_id = l.chat_id
                          AND m.kind = 'mitigation_decision' AND m.payload ->> 'token' = :token
                          AND m.payload ->> 'link' = l.code_sha256
                        LEFT JOIN principals p ON p.principal_id = l.principal_id
                        WHERE l.chat_id = :chat_id AND l.telegram_user_id = :user_id"""),
                    {"chat_id": chat_id, "token": token, "user_id": user_id},
                )
            ).one_or_none()
            if link is None:
                return "Este chat no está vinculado a esta decisión: no se decidió nada."
            if link.principal_id is None:
                return "Vuelve a vincular este chat a tu usuario para decidir desde aquí."
            payload, key = link.payload, f"telegram-{choice}-{token}"
            body = {
                "command": COMMANDS[choice],
                "actor": "human",
                "actor_reference": {
                    "reference_version": "1.0.0",
                    "principal_id": link.principal_id,
                    "display_name": link.display_name,
                },
                "expected_incident_version": payload["incident_version"],
            }
            await queue_tap(
                session,
                key=key,
                chat_id=chat_id,
                decision_message_id=link.message_id,
                principal_id=link.principal_id,
                payload=payload,
                body=body,
            )
        deadline = monotonic() + self.wait_seconds
        while (outcome := await tap_outcome(self.database, key)) is None:
            if monotonic() >= deadline:
                return WORKING
            await asyncio.sleep(0.25)
        status, code = outcome
        if code in REFUSALS:
            return f"No se aplicó: {REFUSALS[code]} ({code})."
        if code == INCIDENT_CHANGED:
            return CHANGED
        async with self.database.transaction() as session:
            message, keyboard = await mitigation_decision(session, payload)
        if not asks_decision(keyboard):
            # Decided, by this tap or before it: the answer is the current state.
            decided = [
                line for line in message.splitlines() if " por " in line and " desde " in line
            ]
            return (decided or message.splitlines())[-1]
        default = "No se pudo decidir; inténtalo de nuevo o decide en la consola."
        return NOT_DECIDED.get(status, default)
