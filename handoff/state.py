import os
from functools import lru_cache
from typing import Literal

import redis

Handler = Literal["agent", "human"]

# A human conversation expires after this many seconds without attendant activity, and the agent
# takes over again. No key means "agent", so expiry needs no scheduled job.
TIMEOUT_SECONDS = int(os.environ.get("HANDOFF_TIMEOUT_SECONDS", "1800"))


@lru_cache
def client() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def _key(conversation_id: str) -> str:
    return f"handoff:{conversation_id}"


def get_handler(conversation_id: str) -> Handler:
    """Who is answering this conversation. Conversations with no key belong to the agent."""
    return "human" if client().get(_key(conversation_id)) == "human" else "agent"


def start_human(conversation_id: str) -> None:
    """Give the conversation to a human, or renew the timeout if it already is with one."""
    client().set(_key(conversation_id), "human", ex=TIMEOUT_SECONDS)


def release(conversation_id: str) -> None:
    """Give the conversation back to the agent."""
    client().delete(_key(conversation_id))
