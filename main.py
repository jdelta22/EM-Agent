import logging
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.runner import reply
from handoff.state import get_handler

logger = logging.getLogger("em_agent")

app = FastAPI(title="EM Agent")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # The client keeps the id between messages. Without one, a new conversation starts.
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ChatResponse(BaseModel):
    conversation_id: str
    handled_by: Literal["agent", "human"]
    # None when a human attendant has the conversation: the answer will come from them.
    reply: str | None


@app.get("/api/health")
def health():
    return {"status": "ok"}


# A plain `def` (not async): the agent and its tools are blocking, so FastAPI runs this in a thread.
@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    conversation_id = body.conversation_id or uuid.uuid4().hex

    try:
        handler = get_handler(conversation_id)
    except Exception:
        # Without the handoff state we can't tell whether a human is answering, so the agent
        # must not talk over them.
        logger.exception("could not read handoff state")
        raise HTTPException(503, "Serviço indisponível no momento. Tente novamente em instantes.")

    if handler == "human":
        return ChatResponse(conversation_id=conversation_id, handled_by="human", reply=None)

    try:
        answer = reply(conversation_id, body.message)
    except Exception:
        logger.exception("agent failed")
        raise HTTPException(502, "Não consegui responder agora. Tente novamente em instantes.")
    return ChatResponse(conversation_id=conversation_id, handled_by="agent", reply=answer)
