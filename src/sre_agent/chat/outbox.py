"""Linked chats and the durable outbox every chat message goes through (issue #766).

Producers call `enqueue` inside their own transaction; dispatch receipts are enqueued by the
`run_events_chat_outbox` trigger. The gateway renders each message when it sends it, so a new
message kind is one entry in `RENDERERS`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.persistence.database import Database

MAX_ATTEMPTS = 10
MAX_BACKOFF_SECONDS = 60
# Telegram rejects texts over 4096 characters; model text alone may reach 4000.
MAX_TEXT = 3900

logger = logging.getLogger("sre_agent.chat.outbox")


class DeliveryError(Exception):
    """A failed send; its message must not carry secrets.

    `final` marks a send the chat will never accept; `retry_after` is the wait Telegram asked for.
    """

    def __init__(self, message: str, *, final: bool = False, retry_after: float | None = None):
        super().__init__(message)
        self.final, self.retry_after = final, retry_after


async def enqueue(
    session: AsyncSession,
    *,
    chat_id: int,
    kind: str,
    dedup_key: str,
    payload: Mapping[str, Any] | None = None,
) -> bool:
    """Queue one message for one chat; False when the chat already has this dedup key."""
    if kind not in RENDERERS:
        raise ValueError(f"unknown chat message kind: {kind}")
    queued = await session.scalar(
        text("""INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
            VALUES (:chat_id, :kind, :dedup_key, CAST(:payload AS jsonb))
            ON CONFLICT (chat_id, dedup_key) DO NOTHING RETURNING message_id"""),
        {
            "chat_id": chat_id,
            "kind": kind,
            "dedup_key": dedup_key,
            "payload": json.dumps(dict(payload or {})),
        },
    )
    return queued is not None


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class ChatStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def issue_link_code(self, ttl: timedelta) -> tuple[str, datetime]:
        code, now = token_urlsafe(24), datetime.now(UTC)
        async with self.database.transaction() as session:
            await session.execute(
                text("""INSERT INTO incident.chat_link_codes (code_sha256, created_at, expires_at)
                    VALUES (:digest, :now, :expires_at)"""),
                {"digest": _digest(code), "now": now, "expires_at": now + ttl},
            )
        return code, now + ttl

    async def receive(self, update_id: int, chat_id: int, message: str) -> None:
        """Answer one incoming message; a replayed update answers nothing new."""
        reply_key = f"update:{update_id}"
        command, _, code = message.strip().partition(" ")
        async with self.database.transaction() as session:
            if command == "/start" and code:
                # Used, expired and unknown codes are rejected alike.
                digest = await session.scalar(
                    text("""UPDATE incident.chat_link_codes
                        SET used_at = clock_timestamp(), used_by_chat_id = :chat_id
                        WHERE code_sha256 = :digest AND used_at IS NULL
                          AND expires_at > clock_timestamp()
                        RETURNING code_sha256"""),
                    {"chat_id": chat_id, "digest": _digest(code.strip())},
                )
                if digest is not None:
                    await session.execute(
                        text("""INSERT INTO incident.chat_links (chat_id, code_sha256, linked_at)
                            VALUES (:chat_id, :digest, clock_timestamp())
                            ON CONFLICT (chat_id) DO NOTHING"""),
                        {"chat_id": chat_id, "digest": digest},
                    )
                kind = "link_confirmed" if digest is not None else "link_rejected"
                await enqueue(session, chat_id=chat_id, kind=kind, dedup_key=reply_key)
                return
            linked = await session.scalar(
                text("SELECT 1 FROM incident.chat_links WHERE chat_id = :chat_id"),
                {"chat_id": chat_id},
            )
            if linked is None:
                # Once per chat, so a stranger cannot fill the queue ahead of the operator.
                await enqueue(session, chat_id=chat_id, kind="not_linked", dedup_key="not_linked")

    async def links(self) -> list[tuple[int, datetime]]:
        async with self.database.transaction() as session:
            rows = await session.execute(
                text("SELECT chat_id, linked_at FROM incident.chat_links ORDER BY linked_at")
            )
            return [(row.chat_id, row.linked_at) for row in rows]

    async def unlink(self, chat_id: int) -> bool:
        """Remove a chat from the allow list and drop what is still queued for it."""
        async with self.database.transaction() as session:
            removed = await session.scalar(
                text("DELETE FROM incident.chat_links WHERE chat_id = :chat_id RETURNING chat_id"),
                {"chat_id": chat_id},
            )
            await session.execute(
                text("""UPDATE incident.chat_outbox SET attempts = :max, last_error = 'unlinked'
                    WHERE chat_id = :chat_id AND sent_at IS NULL"""),
                {"chat_id": chat_id, "max": MAX_ATTEMPTS},
            )
        return removed is not None

    async def deliver_next(self, send: Callable[[int, str], Awaitable[None]]) -> bool:
        """Send the oldest due message of one chat; False when nothing is due.

        The row stays locked until the send is recorded, so two gateways never send it twice.
        A gateway killed between the send and the commit sends it again (at least once).
        """
        async with self.database.transaction() as session:
            row = (
                (
                    await session.execute(
                        text("""SELECT message_id, chat_id, kind, payload, attempts
                            FROM incident.chat_outbox m
                            WHERE sent_at IS NULL AND attempts < :max
                              AND next_attempt_at <= clock_timestamp()
                              AND NOT EXISTS (
                                SELECT 1 FROM incident.chat_outbox o
                                WHERE o.chat_id = m.chat_id AND o.sent_at IS NULL
                                  AND o.attempts < :max AND o.message_id < m.message_id)
                            ORDER BY message_id LIMIT 1 FOR UPDATE SKIP LOCKED"""),
                        {"max": MAX_ATTEMPTS},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return False
            try:
                body = await RENDERERS[row["kind"]](session, row["payload"])
            except Exception as error:
                # A message that cannot be rendered never will be: stop retrying it.
                failure = DeliveryError(f"render: {type(error).__name__}", final=True)
                await self._failed(session, row, failure)
                return True
            if len(body) > MAX_TEXT:
                body = body[:MAX_TEXT] + "… (texto completo en la consola)"
            try:
                await send(row["chat_id"], body)
            except DeliveryError as error:
                await self._failed(session, row, error)
                return True
            await session.execute(
                text("""UPDATE incident.chat_outbox SET sent_at = clock_timestamp(),
                    attempts = attempts + 1, last_error = NULL WHERE message_id = :message_id"""),
                {"message_id": row["message_id"]},
            )
            return True

    @staticmethod
    async def _failed(session: AsyncSession, row: Mapping[str, Any], error: DeliveryError) -> None:
        if error.final:
            logger.warning("chat message %s dropped: %s", row["message_id"], error)
        attempts = MAX_ATTEMPTS if error.final else row["attempts"] + 1
        delay = error.retry_after or min(2 ** row["attempts"], MAX_BACKOFF_SECONDS)
        await session.execute(
            text("""UPDATE incident.chat_outbox SET attempts = :attempts, last_error = :error,
                next_attempt_at = clock_timestamp() + make_interval(secs => :delay)
                WHERE message_id = :message_id"""),
            {
                "attempts": attempts,
                "error": str(error)[:200],
                "delay": delay,
                "message_id": row["message_id"],
            },
        )


async def _incident_label(session: AsyncSession, payload: Mapping[str, Any]) -> str:
    state = await session.scalar(
        text("SELECT state FROM incident.incidents WHERE incident_id = :incident_id"),
        {"incident_id": payload["incident_id"]},
    )
    alert = state.get("alert") if isinstance(state, Mapping) else None
    summary = alert.get("summary") if isinstance(alert, Mapping) else None
    return f"{payload['incident_id']}: {summary}" if summary else str(payload["incident_id"])


async def _investigation_ack(session: AsyncSession, payload: Mapping[str, Any]) -> str:
    label = await _incident_label(session, payload)
    return f"Investigando {label}\nEjecución {payload['run_id']}. Te escribo aquí cuando termine."


async def _investigation_conclusion(session: AsyncSession, payload: Mapping[str, Any]) -> str:
    label = await _incident_label(session, payload)
    receipt = await session.scalar(
        text("SELECT payload -> 'dispatch_receipt' FROM incident.run_events WHERE event_id = :id"),
        {"id": payload["event_id"]},
    )
    outcome = await session.scalar(
        text("""SELECT payload -> 'outcome' FROM incident.run_events
            WHERE run_id = :run_id AND kind = 'investigation_result'
            ORDER BY sequence DESC LIMIT 1"""),
        {"run_id": payload["run_id"]},
    )
    header = f"Investigación terminada: {label}\nEjecución {payload['run_id']}."
    if receipt.get("status") != "success" or not isinstance(outcome, Mapping):
        code = receipt.get("reason_code") or receipt.get("status")
        reason = REASONS.get(code, "la investigación no terminó")
        return f"{header}\nSin conclusión: {reason} ({code})."
    match outcome.get("action"):
        case "propose_hypothesis":
            detail = f"Hipótesis ({outcome['confidence']}): {outcome['statement']}"
        case "propose_mitigation":
            detail = "Mitigación propuesta, pendiente de tu aprobación en la consola."
        case "conclude":
            detail = f"Conclusión: {outcome['summary']}"
        case _:
            detail = f"Necesita una persona: {outcome.get('reason', '')}"
    return f"{header}\n{detail}"


# Reason codes of the dispatch outcome receipt (gateway/investigation.py), for the operator.
REASONS = {
    "producer_interrupted": "la investigación se interrumpió antes de terminar",
    "harness_not_configured": "no hay un modelo configurado para investigar",
    "harness_identity_unavailable": "la identidad del investigador no está disponible",
    "mcp_discovery_denied": "no hay permiso para usar las herramientas de observabilidad",
    "mcp_discovery_rejected": "las herramientas de observabilidad rechazaron la conexión",
    "mcp_discovery_transient": "las herramientas de observabilidad no respondieron",
    "investigator_failed": "el investigador falló",
    "stale_incident_snapshot": "el incidente cambió mientras se investigaba",
    "governed_call_denied": "se denegó una consulta del investigador",
    "investigation_mcp_contract_rejected": "una herramienta respondió fuera de contrato",
    "investigation_denied": "se denegó la investigación",
    "investigation_max_steps": "se agotaron los pasos sin llegar a una conclusión",
    "investigation_invalid_output": "el modelo respondió en un formato no válido",
    "investigation_pre_dispatch_rejected": "la solicitud al modelo se rechazó antes de enviarla",
    "investigation_upstream_unavailable": "el proveedor del modelo no respondió",
    "investigation_tool_unavailable": (
        "una herramienta de observabilidad falló o no respondió a tiempo"
    ),
    "tool_timeout": "una herramienta de observabilidad superó el tiempo límite de la consulta",
    "result_persistence_uncertain": "no se pudo confirmar que el resultado se guardó",
}


def _fixed(message: str) -> Callable[[AsyncSession, Mapping[str, Any]], Awaitable[str]]:
    async def render(session: AsyncSession, payload: Mapping[str, Any]) -> str:
        return message

    return render


RENDERERS: dict[str, Callable[[AsyncSession, Mapping[str, Any]], Awaitable[str]]] = {
    "investigation_ack": _investigation_ack,
    "investigation_conclusion": _investigation_conclusion,
    "link_confirmed": _fixed(
        "Chat vinculado. Aquí recibirás el acuse y la conclusión de cada investigación."
    ),
    "link_rejected": _fixed("Este enlace no es válido, ya se usó o caducó. Pide uno nuevo."),
    "not_linked": _fixed("Este chat no está vinculado. Ábrelo con un enlace de vinculación."),
}
