import os
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from agent.prompt import SYSTEM_PROMPT
from agent.tools import TOOLS

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")

# Upper bound of graph steps per customer message (model + tool calls), so a misbehaving
# tool loop cannot run forever.
RECURSION_LIMIT = 15

FALLBACK_REPLY = (
    "Tive um problema para responder agora. Pode tentar de novo em instantes? "
    "Se preferir, posso passar você para um atendente."
)


@lru_cache
def _model() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL, max_tokens=1024).bind_tools(TOOLS)


def _call_model(state: MessagesState) -> dict:
    # The system prompt must stay identical on every call: thinking blocks saved in the history
    # are signed against it, and the API rejects them if it changes.
    messages = [SystemMessage(SYSTEM_PROMPT), *state["messages"]]
    return {"messages": [_model().invoke(messages)]}


def _checkpointer() -> PostgresSaver:
    # PostgresSaver requires autocommit connections, unlike the pool used by the tools.
    pool = ConnectionPool(
        os.environ["DATABASE_URL"],
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()  # creates the checkpoint tables on first run; no-op afterwards
    return saver


@lru_cache
def get_graph():
    builder = StateGraph(MessagesState)
    builder.add_node("model", _call_model)
    builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", tools_condition)  # -> "tools" or END
    builder.add_edge("tools", "model")
    return builder.compile(checkpointer=_checkpointer())


def _text(content) -> str:
    """Extract the text from a model message (a string, or a list of content blocks)."""
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def reply(conversation_id: str, message: str) -> str:
    """Run one customer message through the agent and return the answer.

    The conversation history lives in the Postgres checkpoint, keyed by `conversation_id`.
    """
    config = {"configurable": {"thread_id": conversation_id}, "recursion_limit": RECURSION_LIMIT}
    result = get_graph().invoke({"messages": [HumanMessage(message)]}, config)
    return _text(result["messages"][-1].content).strip() or FALLBACK_REPLY


ATTENDANT_PREFIX = "[Atendente humano] "


def _thread(conversation_id: str) -> dict:
    return {"configurable": {"thread_id": conversation_id}}


def record_message(conversation_id: str, text: str, role: str) -> None:
    """Append a message to the history without running the model (used while a human answers).

    role: "customer" or "attendant". Attendant messages are stored as assistant messages with a
    prefix, so that if the agent takes over again it can tell them apart from its own.
    """
    if role == "customer":
        message = HumanMessage(text)
    else:
        message = AIMessage(ATTENDANT_PREFIX + text, name="attendant")
    get_graph().update_state(_thread(conversation_id), {"messages": [message]}, as_node="model")


def get_history(conversation_id: str) -> list[dict]:
    """The visible conversation as [{"role": "customer" | "agent" | "attendant", "text": ...}]."""
    state = get_graph().get_state(_thread(conversation_id))
    history = []
    for m in state.values.get("messages", []):
        text = _text(m.content).strip()
        if not text or m.type not in ("human", "ai") or getattr(m, "tool_calls", None):
            continue  # tool results, and assistant steps that call tools (only the final answer is shown)
        if m.type == "human":
            role = "customer"
        elif m.name == "attendant":
            role, text = "attendant", text.removeprefix(ATTENDANT_PREFIX)
        else:
            role = "agent"
        history.append({"role": role, "text": text})
    return history
