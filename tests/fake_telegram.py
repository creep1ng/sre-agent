"""Fake Telegram Bot API for the #766 and #767 E2Es: getMe, getUpdates (long polling),
sendMessage with inline keyboards, answerCallbackQuery and editMessageText.

Like Telegram, it keeps an update until a getUpdates offset above its id confirms it, answers
401 to any other token, 400 to a text over 4096 characters, to a callback answer over 200 and
to an edit that changes nothing. It refuses URL buttons on `localhost` or on an IP address that
is not public (loopback, private, tailnet) with BUTTON_URL_INVALID; that is this fake's stand-in
for the hosts real Telegram refuses, not a verified copy of its rules.
`/_test/*` lets the E2E play the user: inject messages and button taps, read what the bot sent
(with the time each send arrived), the callback answers and the edits, and fail sends.

    uvicorn fake_telegram:app --app-dir tests --port 8081
"""

import asyncio
import ipaddress
from datetime import UTC, datetime
from html import escape
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

# Synthetic, never a real bot's: scripts/run_telegram_e2e.sh gives the gateway the same one.
TOKEN = "7000001:fake-e2e-token"
app = FastAPI()
updates: list[dict[str, Any]] = []
sent: list[dict[str, Any]] = []
answers: list[dict[str, Any]] = []
edits: list[dict[str, Any]] = []
state = {"next_update": 1, "fail_sends": 0}
arrived = asyncio.Condition()


def _buttons(fields: dict[str, Any]) -> list[list[tuple[str, str]]] | None:
    """(label, callback data or URL) per button; None when a URL button would be refused."""
    rows = (fields.get("reply_markup") or {}).get("inline_keyboard", [])
    for button in (b for row in rows for b in row if "url" in b):
        host = urlsplit(button["url"]).hostname or ""
        try:
            refused = not ipaddress.ip_address(host).is_global
        except ValueError:
            refused = host == "localhost" or "." not in host
        if refused:
            return None
    return [[(b["text"], b.get("callback_data") or b["url"]) for b in row] for row in rows]


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
        if not 1 <= len(fields["text"]) <= 4096:
            return _reply(status=400, description="Bad Request: message is too long")
        if (buttons := _buttons(fields)) is None:
            return _reply(status=400, description="Bad Request: BUTTON_URL_INVALID")
        record = {
            "message_id": len(sent) + 1,
            "chat_id": fields["chat_id"],
            "text": fields["text"],
            "received_at": datetime.now(UTC).isoformat(),
            "buttons": buttons,
        }
        sent.append(record)
        return _reply(record)
    if method == "answerCallbackQuery":
        if len(fields["text"]) > 200:
            return _reply(status=400, description="Bad Request: answer text is too long")
        answers.append({"callback_query_id": fields["callback_query_id"], "text": fields["text"]})
        return _reply(True)
    if method == "editMessageText":
        message = next(
            (
                m
                for m in sent
                if (m["chat_id"], m["message_id"]) == (fields["chat_id"], fields["message_id"])
            ),
            None,
        )
        if message is None:
            return _reply(status=400, description="Bad Request: message to edit not found")
        if (buttons := _buttons(fields)) is None:
            return _reply(status=400, description="Bad Request: BUTTON_URL_INVALID")
        if message["text"] == fields["text"] and message["buttons"] == buttons:
            return _reply(status=400, description="Bad Request: message is not modified")
        message.update(text=fields["text"], buttons=buttons)
        edits.append({**fields, "edited_at": datetime.now(UTC).isoformat()})
        return _reply(message)
    return _reply(status=404, description="Not Found")


async def _push(update: dict[str, Any]) -> JSONResponse:
    async with arrived:
        updates.append(update)
        arrived.notify_all()
    return JSONResponse(update)


@app.post("/_test/messages")
async def user_message(request: Request) -> JSONResponse:
    fields = await request.json()
    update = {
        "update_id": state["next_update"],
        "message": {
            "chat": {"id": fields["chat_id"], "type": fields.get("chat_type", "private")},
            "from": {"id": fields.get("from_id", fields["chat_id"])},
            "text": fields["text"],
        },
    }
    state["next_update"] += 1
    return await _push(update)


@app.post("/_test/taps")
async def tap(request: Request) -> JSONResponse:
    """A button tap on message `message_id` in chat `chat_id`, by user `from_id` (the chat's)."""
    fields = await request.json()
    query_id = f"cbq-{state['next_update']}"
    message = {"message_id": fields["message_id"], "chat": {"id": fields["chat_id"]}}
    query = {"id": query_id, "data": fields["data"], "message": message}
    query["from"] = {"id": fields.get("from_id", fields["chat_id"])}
    update = {"update_id": state["next_update"], "callback_query": query}
    state["next_update"] += 1
    return await _push(update)


@app.get("/_test/sent")
async def sent_messages() -> JSONResponse:
    return JSONResponse(sent)


@app.get("/_test/answers")
async def callback_answers() -> JSONResponse:
    return JSONResponse({"answers": answers, "edits": edits})


@app.post("/_test/fail-sends")
async def fail_sends(request: Request) -> JSONResponse:
    state["fail_sends"] = int((await request.json())["count"])
    return JSONResponse(state)


@app.get("/_test/transcript")
async def transcript() -> HTMLResponse:
    rows = "".join(
        f"<tr><td>{item['message_id']}</td><td>{item['chat_id']}</td>"
        f"<td>{escape(item['received_at'])}</td><td><pre>{escape(item['text'])}</pre>"
        + "".join(f"[{escape(label)}] " for row in item["buttons"] for label, _ in row)
        + "</td></tr>"
        for item in sent
    )
    taps = "".join(f"<li>{escape(item['text'])}</li>" for item in answers)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif'><h3>Fake Telegram: messages the bot sent"
        "</h3><table border=1 cellpadding=4><tr><th>#</th><th>chat</th><th>received at</th>"
        f"<th>text</th></tr>{rows}</table><h3>Answers to button taps</h3><ol>{taps}</ol>"
        "</body></html>"
    )
