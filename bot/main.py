from fastapi import FastAPI
from pydantic import BaseModel

from bot.commands.router import handle_message, plato_client
from bot.database.db import init_db
from bot.models.message import IncomingMessage
from bot.services.mvp import get_bridge_state, update_bridge_heartbeat

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


class BridgeHeartbeatPayload(BaseModel):
    current_group_id: str | None = None
    current_group_title: str | None = None
    last_error: str | None = None
    ack_navigation: bool = False


class BridgeResumePayload(BaseModel):
    group_id: str | None = None
    group_title: str | None = None


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


@app.get("/bridge-state")
def bridge_state():
    return get_bridge_state()


@app.post("/bridge-state/heartbeat")
def bridge_heartbeat(payload: BridgeHeartbeatPayload):
    return update_bridge_heartbeat(
        payload.current_group_id,
        payload.current_group_title,
        payload.last_error,
        payload.ack_navigation,
    )


@app.post("/bridge-state/resume")
def bridge_resume(payload: BridgeResumePayload):
    from bot.services.mvp import resume_from_off
    resume_from_off(payload.group_id, payload.group_title)
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}
