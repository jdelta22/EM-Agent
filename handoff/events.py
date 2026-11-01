import json

from redis.client import PubSub

from handoff.state import client

# Events for attendants: {"type": "transfer" | "customer_message" | "released", "conversation_id": ...}
CHANNEL = "handoff:events"


def publish(event: dict) -> None:
    client().publish(CHANNEL, json.dumps(event, ensure_ascii=False))


def subscribe() -> PubSub:
    """A pub/sub already subscribed to the events channel. The caller must close it."""
    pubsub = client().pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(CHANNEL)
    return pubsub
