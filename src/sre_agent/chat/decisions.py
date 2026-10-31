"""Approve or reject a proposed mitigation from a linked chat with one tap (issue #767).

A button's callback data is `a:` or `r:` plus the opaque token of one decision message; the
token is bound to the chat it was sent to and to the incident, run, proposal and incident
version that message shows. A tap sends the console's own command through `RunCommandService`
as the human principal the chat's link names: the same grant check, attribution and runtime,
recorded with the channel `telegram`. The runtime keeps a second tap from deciding twice: the
same button replays its first result, and any later tap finds the reviewed version stale.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from sre_agent.chat.outbox import Keyboard, mitigation_decision
from sre_agent.gateway.runs import RunCommandService
from sre_agent.persistence.database import Database

CALLBACK = re.compile(r"^([ar]):([0-9a-f]{32})$")
COMMANDS = {"a": "approve_mitigation", "r": "reject_mitigation"}
NOT_DECIDED = {
    401: "Tu usuario ya no está activo: no se decidió nada.",
    403: "No tienes permiso para decidir esta mitigación: no se decidió nada.",
}


class ChatDecisions:
    def __init__(self, database: Database, commands: RunCommandService) -> None:
        self.database, self.commands = database, commands

    async def tap(self, chat_id: int, data: str) -> tuple[str, tuple[str, Keyboard | None] | None]:
        """Decide once; returns the callback answer and, once decided, the message to show."""
        match = CALLBACK.fullmatch(data)
        if match is None:
            return "Este botón no es válido: no se decidió nada.", None
        choice, token = match.groups()
        async with self.database.transaction() as session:
            link = (
                await session.execute(
                    text("""SELECT l.principal_id, p.display_name, m.payload
                        FROM incident.chat_links l
                        JOIN incident.chat_outbox m ON m.chat_id = l.chat_id
                          AND m.kind = 'mitigation_decision' AND m.payload ->> 'token' = :token
                        LEFT JOIN principals p ON p.principal_id = l.principal_id
                        WHERE l.chat_id = :chat_id"""),
                    {"chat_id": chat_id, "token": token},
                )
            ).one_or_none()
        if link is None:
            return "Este chat no está vinculado a esta decisión: no se decidió nada.", None
        if link.principal_id is None:
            return "Vuelve a vincular este chat a tu usuario para decidir desde aquí.", None
        payload = link.payload
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
        reply = await self.commands.send_from_chat(
            link.principal_id,
            "telegram",
            payload["incident_id"],
            payload["run_id"],
            body,
            f"telegram-{choice}-{token}",
        )
        async with self.database.transaction() as session:
            message, keyboard = await mitigation_decision(session, payload)
        if keyboard is None:
            # Decided, by this tap or before it: the answer is the current state.
            return message.splitlines()[-1], (message, None)
        default = "No se pudo decidir; inténtalo de nuevo o decide en la consola."
        return NOT_DECIDED.get(reply.status_code, default), None
