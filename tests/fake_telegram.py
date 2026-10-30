"""Fake Telegram Bot API for the #766 E2E: getMe, getUpdates (long polling) and sendMessage.

Like Telegram, it keeps an update until a getUpdates offset above its id confirms it, and it
answers 401 to any other token. `/_test/*` lets the E2E play the user: inject messages, read
what the bot sent (with the time each send arrived) and fail the next sends.

    uvicorn fake_telegram:app --app-dir tests --port 8081   # FAKE_TELEGRAM_TOKEN required
"""

import asyncio
import os
from datetime import UTC, datetime
from html import escape
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

TOKEN = os.environ["FAKE_TELEGRAM_TOKEN"]
app = FastAPI()
updates: list[dict[str, Any]] = []
sent: list[dict[str, Any]] = []
state = {"next_update": 1, "fail_sends": 0}
arrived = asyncio.Condition()


def _reply(result: Any = None, status: int = 200, description: str = "") -> JSONResponse:
    if status != 200:
        body = {"ok": False, "error_code": status, "description": description}
        return JSONResponse(body, status)
    return JSONResponse({"ok": True, "result": result})


@app.post("/bot{token}/{method}")
async def bot(token: str, method: str, request: Request) -> JSONResponse:
    if token != TOKEN:
        return _reply(status=401, description="Unauthorized")
    fields = await request.json()
    if method == "getMe":
        return _reply({"id": 7000001, "is_bot": True, "username": "midnight_fake_bot"})
    if method == "getUpdates":
        offset = fields.get("offset")
        if offset is not None:
            updates[:] = [item for item in updates if item["update_id"] >= offset]
        async with arrived:
            try:
                await asyncio.wait_for(arrived.wait_for(lambda: bool(updates)), fields["timeout"])
            except TimeoutError:
                pass
        return _reply(list(updates))
    if method == "sendMessage":
        if state["fail_sends"] > 0:
            state["fail_sends"] -= 1
            return _reply(status=502, description="Bad Gateway (fake failure)")
        record = {
            "message_id": len(sent) + 1,
            "chat_id": fields["chat_id"],
            "text": fields["text"],
            "received_at": datetime.now(UTC).isoformat(),
        }
        sent.append(record)
        return _reply(record)
    return _reply(status=404, description="Not Found")


@app.post("/_test/messages")
async def user_message(request: Request) -> JSONResponse:
    fields = await request.json()
    update = {
        "update_id": state["next_update"],
        "message": {"chat": {"id": fields["chat_id"]}, "text": fields["text"]},
    }
    state["next_update"] += 1
    async with arrived:
        updates.append(update)
        arrived.notify_all()
    return JSONResponse(update)


@app.get("/_test/sent")
async def sent_messages() -> JSONResponse:
    return JSONResponse(sent)


@app.post("/_test/fail-sends")
async def fail_sends(request: Request) -> JSONResponse:
    state["fail_sends"] = int((await request.json())["count"])
    return JSONResponse(state)


@app.get("/_test/transcript")
async def transcript() -> HTMLResponse:
    rows = "".join(
        f"<tr><td>{item['message_id']}</td><td>{item['chat_id']}</td>"
        f"<td>{escape(item['received_at'])}</td><td><pre>{escape(item['text'])}</pre></td></tr>"
        for item in sent
    )
    return HTMLResponse(
        "<html><body style='font-family:sans-serif'><h3>Fake Telegram: messages the bot sent"
        "</h3><table border=1 cellpadding=4><tr><th>#</th><th>chat</th><th>received at</th>"
        f"<th>text</th></tr>{rows}</table></body></html>"
    )
