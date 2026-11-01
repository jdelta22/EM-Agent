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


def _reason_key(conversation_id: str) -> str:
    # Does not match the "handoff:*" pattern used by list_human().
    return f"handoff_reason:{conversation_id}"


def start_human(conversation_id: str, reason: str | None = None) -> None:
    """Give the conversation to a human, or renew the timeout if it already is with one.

    `reason` (why the agent transferred) is kept for the attendant's queue; it expires with the
    handoff and is only replaced when a new one is given.
    """
    r = client()
    r.set(_key(conversation_id), "human", ex=TIMEOUT_SECONDS)
    if reason:
        r.set(_reason_key(conversation_id), reason, ex=TIMEOUT_SECONDS)
    else:
        r.expire(_reason_key(conversation_id), TIMEOUT_SECONDS)


def release(conversation_id: str) -> None:
    """Give the conversation back to the agent."""
    client().delete(_key(conversation_id), _reason_key(conversation_id))


def list_human() -> list[dict]:
    """Conversations currently with a human, most recently active first."""
    r = client()
    items = []
    for key in r.scan_iter("handoff:*"):
        conversation_id = key.removeprefix("handoff:")
        if r.get(key) != "human":
            continue
        items.append({
            "conversation_id": conversation_id,
            "reason": r.get(_reason_key(conversation_id)),
            "expires_in": max(r.ttl(key), 0),
        })
    return sorted(items, key=lambda i: -i["expires_in"])
