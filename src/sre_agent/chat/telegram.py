"""Telegram Bot API over long polling: no public URL, works behind NAT (issue #766).

    python -m sre_agent.chat.telegram gateway       # answer updates and drain the outbox
    python -m sre_agent.chat.telegram link --principal ID [--ttl-seconds N]  # one-time link
    python -m sre_agent.chat.telegram links | unlink CHAT_ID   # list or revoke linked chats

The bot token travels only in request paths. httpx logs those paths at INFO, so its logger is
held at WARNING, and errors name the method and status, never the URL.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from datetime import timedelta
from typing import Any

import httpx

from sre_agent.chat.outbox import ChatStore, DeliveryError, Keyboard
from sre_agent.persistence.database import Database

logger = logging.getLogger("sre_agent.chat.telegram")


class BotApi:
    def __init__(self, http: httpx.AsyncClient, token: str) -> None:
        self._http, self._token = http, token

    async def call(self, method: str, *, wait: float = 10, **fields: Any) -> Any:
        try:
            path = f"/bot{self._token}/{method}"
            reply = await self._http.post(path, json=fields, timeout=wait)
        except httpx.HTTPError as error:
            raise DeliveryError(f"{method}: {type(error).__name__}") from None
        try:
            body = reply.json()
        except ValueError:
            body = {}
        if reply.status_code != 200 or not body.get("ok"):
            # 400 (malformed, too long) and 403 (bot blocked) never succeed for that message;
            # 401 and 404 mean a bad token, which the operator fixes, so those are retried.
            raise DeliveryError(
                f"{method}: HTTP {reply.status_code} {body.get('description', '')}",
                final=reply.status_code in (400, 403),
                retry_after=(body.get("parameters") or {}).get("retry_after"),
            )
        return body["result"]

    async def send(self, chat_id: int, message: str, keyboard: Keyboard | None = None) -> None:
        markup = {"reply_markup": {"inline_keyboard": keyboard}} if keyboard else {}
        await self.call("sendMessage", chat_id=chat_id, text=message, **markup)


async def _poll(bot: BotApi, store: ChatStore, poll_seconds: int) -> None:
    # Telegram keeps an update until a later getUpdates offset confirms it, so a restart
    # replays unconfirmed updates; `receive` answers each update id at most once.
    offset = None
    while True:
        try:
            updates = await bot.call(
                "getUpdates",
                wait=poll_seconds + 10,
                offset=offset,
                timeout=poll_seconds,
                allowed_updates=["message"],
            )
        except DeliveryError as error:
            logger.warning("polling failed: %s", error)
            await asyncio.sleep(2)
            continue
        for update in updates:
            message = update.get("message") or {}
            try:
                if isinstance(message.get("text"), str) and "chat" in message:
                    chat_id = message["chat"]["id"]
                    await store.receive(update["update_id"], chat_id, message["text"])
            except Exception as error:
                # Unconfirmed, the update comes back with the next poll.
                logger.warning("update not stored: %s", type(error).__name__)
                await asyncio.sleep(2)
                break
            offset = update["update_id"] + 1


async def _deliver(bot: BotApi, store: ChatStore, stopping: asyncio.Event) -> None:
    while not stopping.is_set():
        if not await store.deliver_next(bot.send):
            try:
                await asyncio.wait_for(stopping.wait(), 0.5)
            except TimeoutError:
                pass


async def gateway(database_url: str, api_url: str, token: str, poll_seconds: int) -> None:
    database, stopping = Database(database_url), asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stopping.set)
    try:
        async with httpx.AsyncClient(base_url=api_url) as http:
            bot, store = BotApi(http, token), ChatStore(database)
            me = await bot.call("getMe")
            logger.info("telegram gateway started as @%s", me.get("username"))
            poller = asyncio.create_task(_poll(bot, store, poll_seconds))
            # A stop finishes the message being sent; only a kill mid-send repeats it.
            await _deliver(bot, store, stopping)
            poller.cancel()
            await asyncio.gather(poller, return_exceptions=True)
    finally:
        await database.dispose()


async def link(
    database_url: str, api_url: str, token: str, ttl: timedelta, principal_id: str
) -> str:
    database = Database(database_url)
    try:
        async with httpx.AsyncClient(base_url=api_url) as http:
            me = await BotApi(http, token).call("getMe")
        code, expires_at = await ChatStore(database).issue_link_code(ttl, principal_id)
    finally:
        await database.dispose()
    return f"https://t.me/{me['username']}?start={code} (expires {expires_at.isoformat()})"


async def manage_links(database_url: str, unlink_chat_id: int | None) -> str:
    database = Database(database_url)
    try:
        store = ChatStore(database)
        if unlink_chat_id is not None:
            removed = await store.unlink(unlink_chat_id)
            return f"chat {unlink_chat_id} {'unlinked' if removed else 'was not linked'}"
        rows = await store.links()
    finally:
        await database.dispose()
    lines = (f"{chat} linked {at.isoformat()} as {who or 'nobody'}" for chat, at, who in rows)
    return "\n".join(lines) or "no chats"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m sre_agent.chat.telegram")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("gateway")
    commands.add_parser("links")
    commands.add_parser("unlink").add_argument("chat_id", type=int)
    link_parser = commands.add_parser("link")
    # The human the chat decides as (#767): whoever runs this already holds the database.
    link_parser.add_argument("--principal", required=True, help="an active human principal id")
    link_parser.add_argument(
        "--ttl-seconds", type=int, default=900, choices=range(1, 86401), metavar="1..86400"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    database_url, token = os.environ.get("DATABASE_URL"), os.environ.get("TELEGRAM_BOT_TOKEN")
    if database_url and arguments.command in ("links", "unlink"):
        print(asyncio.run(manage_links(database_url, getattr(arguments, "chat_id", None))))
        return
    if not database_url or not token:
        raise SystemExit("DATABASE_URL and TELEGRAM_BOT_TOKEN are required")
    api_url = os.environ.get("TELEGRAM_API_URL") or "https://api.telegram.org"
    if arguments.command == "link":
        print(
            asyncio.run(
                link(
                    database_url,
                    api_url,
                    token,
                    timedelta(seconds=arguments.ttl_seconds),
                    arguments.principal,
                )
            )
        )
        return
    poll_seconds = int(os.environ.get("TELEGRAM_POLL_TIMEOUT_SECONDS") or 25)
    asyncio.run(gateway(database_url, api_url, token, poll_seconds))


if __name__ == "__main__":
    main()
