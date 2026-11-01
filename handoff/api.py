import os
import secrets
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.runner import get_history, record_message
from handoff.events import publish, subscribe
from handoff.state import get_handler, list_human, release, start_human

ConversationId = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")


def require_token(x_attendant_token: str = Header(default="")) -> None:
    # Fail closed: without ATTENDANT_TOKEN configured, nobody gets in.
    expected = os.environ.get("ATTENDANT_TOKEN", "")
    if not expected or not secrets.compare_digest(x_attendant_token.encode(), expected.encode()):
        raise HTTPException(401, "Token de atendente inválido.")


router = APIRouter(prefix="/api/attendant", dependencies=[Depends(require_token)])


class AttendantMessage(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("/events")
def events() -> StreamingResponse:
    """Server-sent events with transfers and customer messages, so the attendant is notified."""

    def stream() -> Iterator[str]:
        pubsub = subscribe()
        try:
            yield ": connected\n\n"
            while True:
                message = pubsub.get_message(timeout=15)
                # Keepalive comment: also makes a closed connection fail the write and end the loop.
                yield f"data: {message['data']}\n\n" if message else ": keepalive\n\n"
        finally:
            pubsub.close()

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/conversations")
def conversations():
    """Conversations currently with a human, most recently active first (the attendant's queue)."""
    return list_human()


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str = ConversationId):
    return {"handled_by": get_handler(conversation_id), "messages": get_history(conversation_id)}


@router.post("/conversations/{conversation_id}/message")
def send_message(body: AttendantMessage, conversation_id: str = ConversationId):
    """Answer the customer. Also takes the conversation if it is with the agent, and renews the timeout."""
    record_message(conversation_id, body.text, "attendant")
    start_human(conversation_id)
    return {"handled_by": "human"}


@router.post("/conversations/{conversation_id}/release")
def release_conversation(conversation_id: str = ConversationId):
    """Give the conversation back to the agent."""
    release(conversation_id)
    publish({"type": "released", "conversation_id": conversation_id})
    return {"handled_by": "agent"}
