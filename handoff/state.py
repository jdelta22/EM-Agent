import os
from functools import lru_cache
from typing import Literal

import redis

Handler = Literal["agent", "human"]


@lru_cache
def _client() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def _key(conversation_id: str) -> str:
    return f"handoff:{conversation_id}"


def get_handler(conversation_id: str) -> Handler:
    """Who is answering this conversation. Conversations with no key belong to the agent."""
    return "human" if _client().get(_key(conversation_id)) == "human" else "agent"


def set_handler(conversation_id: str, handler: Handler) -> None:
    _client().set(_key(conversation_id), handler)
