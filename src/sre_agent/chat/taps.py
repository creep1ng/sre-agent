"""Carry out in the API what a Telegram tap decided (#722, #767).

The gateway faces the internet and holds no executor key, agent key or credential to act as
someone: it verifies the tap (chat, Telegram user and token) and queues the run command in
`incident.chat_taps`. `TapWorker` runs in the API, claims each tap and sends it through
`RunCommandService.send_from_chat`, the console's path: grant and attribution checks, then for
an approval with a catalog operation the executor's checks, the signed call, its audit and the
timeline. It writes the outcome back for the gateway's answer and queues what the chat must see
when the tap decided nothing: why an approval was refused, or a fresh proposal when the incident
changed. A decision that was taken is edited in by the `decisions_chat_update` trigger.

A tap is claimed in its own transaction and replayed after two minutes if the API died with it;
the idempotency key makes the replay answer the first result instead of deciding twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.chat.outbox import REFUSALS, asks_decision, enqueue, mitigation_decision
from sre_agent.persistence.database import Database

if TYPE_CHECKING:
    # The gateway imports this module too; only the API needs the command service.
    from sre_agent.gateway.runs import RunCommandService

logger = logging.getLogger("sre_agent.chat.taps")
MAX_TAP_ATTEMPTS = 5
# What a tap's outcome is called when the incident moved on: a fresh proposal was queued.
INCIDENT_CHANGED = "incident_changed"


async def queue_tap(
    session: AsyncSession,
    *,
    key: str,
    chat_id: int,
    decision_message_id: int,
    principal_id: str,
    payload: dict[str, Any],
    body: dict[str, Any],
) -> None:
    """Queue one verified tap. The same button tapped again waits for the same outcome once it
    decided; after one that decided nothing (refused, not allowed, stale) it is sent again, as a
    console retry would be: the grant, the executor or the incident may have changed."""
    await session.execute(
        text("""INSERT INTO incident.chat_taps (idempotency_key, chat_id, decision_message_id,
                principal_id, incident_id, run_id, body)
            VALUES (:key, :chat_id, :message_id, :principal_id, :incident_id, :run_id,
                CAST(:body AS jsonb))
            ON CONFLICT (idempotency_key) DO UPDATE SET queued_at = clock_timestamp(),
              claimed_at = NULL, attempts = 0, done_at = NULL, status_code = NULL,
              error_code = NULL
            WHERE incident.chat_taps.status_code >= 400"""),
        {"key": key, "chat_id": chat_id, "message_id": decision_message_id}
        | {"principal_id": principal_id, "incident_id": payload["incident_id"]}
        | {"run_id": payload["run_id"], "body": json.dumps(body)},
    )


async def tap_outcome(database: Database, key: str) -> tuple[int, str | None] | None:
    async with database.transaction() as session:
        row = (
            await session.execute(
                text("""SELECT status_code, error_code FROM incident.chat_taps
                    WHERE idempotency_key = :key AND done_at IS NOT NULL"""),
                {"key": key},
            )
        ).one_or_none()
    return None if row is None else (row.status_code, row.error_code)


class TapWorker:
    def __init__(self, database: Database, commands: RunCommandService) -> None:
        self.database, self.commands = database, commands

    async def run(self, idle_seconds: float = 0.5) -> None:
        while True:
            try:
                if await self.run_once():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Only the type: the row and the command may carry incident content.
                logger.warning("chat tap not carried out: %s", type(error).__name__)
            await asyncio.sleep(idle_seconds)

    async def run_once(self) -> bool:
        """Carry out the oldest due tap; False when none is due."""
        async with self.database.transaction() as session:
            tap = (
                (
                    await session.execute(
                        text("""UPDATE incident.chat_taps
                            SET claimed_at = clock_timestamp(), attempts = attempts + 1
                            WHERE tap_id = (
                              SELECT tap_id FROM incident.chat_taps
                              WHERE done_at IS NULL AND attempts < :max AND (claimed_at IS NULL
                                OR claimed_at < clock_timestamp() - interval '2 minutes')
                              ORDER BY tap_id LIMIT 1 FOR UPDATE SKIP LOCKED)
                            RETURNING tap_id, idempotency_key, chat_id, decision_message_id,
                              principal_id, incident_id, run_id, body"""),
                        {"max": MAX_TAP_ATTEMPTS},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if tap is None:
            return False
        reply = await self.commands.send_from_chat(
            tap["principal_id"],
            "telegram",
            tap["incident_id"],
            tap["run_id"],
            tap["body"],
            tap["idempotency_key"],
        )
        code = (
            (json.loads(reply.body).get("error") or {}).get("code")
            if reply.status_code >= 400
            else None
        )
        async with self.database.transaction() as session:
            code = await self._follow_up(session, tap, reply.status_code, code)
            await session.execute(
                text("""UPDATE incident.chat_taps SET done_at = clock_timestamp(),
                    status_code = :status, error_code = :code WHERE tap_id = :tap_id"""),
                {"status": reply.status_code, "code": code, "tap_id": tap["tap_id"]},
            )
        return True

    async def _follow_up(
        self, session: AsyncSession, tap: Any, status: int, code: str | None
    ) -> str | None:
        """What the chat must see when the tap decided nothing; the outcome's code."""
        if status < 400:
            return code
        payload = await session.scalar(
            text("SELECT payload FROM incident.chat_outbox WHERE message_id = :message_id"),
            {"message_id": tap["decision_message_id"]},
        )
        target = {"target": tap["decision_message_id"], "incident_id": tap["incident_id"]}
        dedup = f"tap:{tap['tap_id']}"
        if code in REFUSALS:
            # Nothing moved: the buttons stay, and the message says why.
            refused = target | {"refused": code, "at": datetime.now(UTC).isoformat()}
            await enqueue(
                session,
                chat_id=tap["chat_id"],
                kind="decision_update",
                dedup_key=dedup,
                payload=refused,
            )
            return code
        _, keyboard = await mitigation_decision(session, payload)
        version = await session.scalar(
            text("SELECT version FROM incident.incidents WHERE incident_id = :incident_id"),
            {"incident_id": tap["incident_id"]},
        )
        if status == 409 and asks_decision(keyboard) and version != payload["incident_version"]:
            # Still waiting, but on another version: the same tap would stay stale forever.
            fresh = {**payload, "token": uuid4().hex, "incident_version": version}
            key = f"mitigation_decision:{payload['run_id']}:{payload['mitigation_id']}:{version}"
            await enqueue(
                session,
                chat_id=tap["chat_id"],
                kind="decision_update",
                dedup_key=dedup,
                payload=target | {"stale": True},
            )
            await enqueue(
                session,
                chat_id=tap["chat_id"],
                kind="mitigation_decision",
                dedup_key=key,
                payload=fresh,
            )
            return INCIDENT_CHANGED
        return code
