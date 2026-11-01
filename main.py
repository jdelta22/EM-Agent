import logging
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from agent.runner import get_history, record_message, reply
from handoff.api import router as attendant_router
from handoff.events import publish
from handoff.state import get_handler

logger = logging.getLogger("em_agent")

app = FastAPI(title="EM Agent")
app.include_router(attendant_router)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # The client keeps the id between messages. Without one, a new conversation starts.
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ChatResponse(BaseModel):
    conversation_id: str
    # Who answers the next message. It can be "human" together with a reply, when the agent
    # has just transferred the conversation.
    handled_by: Literal["agent", "human"]
    # None when a human has the conversation: the answer will come from them (see GET /api/chat/{id}).
    reply: str | None


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Plain `def` (not async): the agent and its tools are blocking, so FastAPI runs these in a thread.
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
        # Keep the message in the history (so the agent knows it if it takes over again) and
        # notify the attendant.
        try:
            record_message(conversation_id, body.message, "customer")
            publish({"type": "customer_message", "conversation_id": conversation_id, "text": body.message})
        except Exception:
            logger.exception("could not record message for human attendant")
            raise HTTPException(502, "Não consegui enviar sua mensagem. Tente novamente em instantes.")
        return ChatResponse(conversation_id=conversation_id, handled_by="human", reply=None)

    try:
        answer = reply(conversation_id, body.message)
    except Exception:
        logger.exception("agent failed")
        raise HTTPException(502, "Não consegui responder agora. Tente novamente em instantes.")

    # The agent may have transferred the conversation during this turn.
    try:
        handler = get_handler(conversation_id)
    except Exception:
        logger.exception("could not read handoff state after reply")
    return ChatResponse(conversation_id=conversation_id, handled_by=handler, reply=answer)


@app.get("/api/chat/{conversation_id}")
def chat_history(conversation_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$"), after: int = 0):
    """Messages of a conversation, from index `after`. The chat polls it to receive attendant replies."""
    try:
        handler = get_handler(conversation_id)
        messages = get_history(conversation_id)
    except Exception:
        logger.exception("could not load conversation")
        raise HTTPException(503, "Serviço indisponível no momento. Tente novamente em instantes.")
    return {"handled_by": handler, "total": len(messages), "messages": messages[max(after, 0):]}
