from fastapi import FastAPI
from pydantic import BaseModel

from bot.commands.router import handle_message, plato_client
from bot.database.db import init_db
from bot.models.message import IncomingMessage

app = FastAPI(title="Plato Group Bot Backend")


@app.on_event("startup")
def _startup():
    init_db()


class InboxPayload(BaseModel):
    message_id: str
    group_id: str
    user_id: str
    username: str
    text: str
    is_self: bool = False
    timestamp: str | None = None


@app.post("/inbox")
def inbox(payload: InboxPayload):
    msg = IncomingMessage(**payload.dict())
    response = handle_message(msg)
    return {"handled": response is not None, "response": response}


@app.get("/outbox")
def outbox(group_id: str | None = None, limit: int = 20, claim: bool = False):
    if claim:
        return plato_client.claim(group_id, limit)
    return plato_client.pending(group_id, limit)


@app.post("/outbox/{outbox_id}/ack")
def outbox_ack(outbox_id: int):
    plato_client.ack(outbox_id)
    return {"ok": True}


@app.post("/outbox/{outbox_id}/fail")
def outbox_fail(outbox_id: int, reason: str = ""):
    plato_client.fail(outbox_id, reason)
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}
