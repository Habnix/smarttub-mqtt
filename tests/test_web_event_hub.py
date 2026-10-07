"""Contracts for bounded live-web event delivery."""

import asyncio

from src.web.event_hub import WebEventHub


def test_event_hub_isolates_payloads_and_keeps_the_newest_event() -> None:
    async def scenario() -> None:
        hub = WebEventHub(queue_size=1)
        queue = hub.subscribe()
        original = {"quality": {"status": "live"}}

        await hub.publish("state", original)
        original["quality"]["status"] = "changed-outside-hub"
        await hub.publish("state", {"quality": {"status": "stale"}})

        event, payload = await queue.get()
        assert event == "state"
        assert payload == {"quality": {"status": "stale"}}

        hub.unsubscribe(queue)
        assert queue not in hub._subscribers

    asyncio.run(scenario())
