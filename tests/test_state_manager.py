import asyncio
from typing import ClassVar

from src.core.state_manager import StateManager


def test_unavailable_state_does_not_invent_component_values():
    fallback = StateManager(
        smarttub_client=None, topic_mapper=None
    ).get_safe_fallback_state()

    assert fallback["components"] == {}
    assert fallback["quality"]["status"] == "unavailable"
    assert fallback["quality"]["observed_at"] is None
    assert fallback["quality"]["last_success_at"] is None
    assert fallback["quality"]["checked_at"] == fallback["timestamp"]


def test_sync_state_writes_the_latest_snapshot_under_the_snapshot_lock():
    class Client:
        @staticmethod
        async def get_state_snapshot():
            return {
                "timestamp": "2026-08-21T12:00:00+00:00",
                "components": {"spa": {"state": "ready"}},
            }

    class TopicMapper:
        @staticmethod
        def publish_state_snapshot(snapshot):
            return []

        @staticmethod
        def publish_messages(messages):
            return None

    class RecordingLock:
        entered = 0

        def __enter__(self):
            self.entered += 1
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    manager = StateManager(smarttub_client=Client(), topic_mapper=TopicMapper())
    lock = RecordingLock()
    manager._lock = lock

    asyncio.run(manager.sync_state())

    assert lock.entered == 1
    assert manager.get_latest_snapshot()["components"]["spa"]["state"] == "ready"
    assert lock.entered == 2


def test_failed_sync_keeps_last_observation_and_marks_it_stale():
    class Client:
        calls = 0

        @classmethod
        async def get_state_snapshot(cls):
            cls.calls += 1
            if cls.calls == 2:
                raise TimeoutError("cloud unavailable")
            return {
                "spa_id": "spa-test",
                "timestamp": "2026-08-21T12:00:00+00:00",
                "components": {
                    "heater": {"state": "on", "temperature": 38.5},
                    "pumps": [{"id": "P1", "state": "running"}],
                },
            }

    class TopicMapper:
        published: ClassVar[list] = []

        @classmethod
        def publish_state_snapshot(cls, snapshot):
            return [("snapshot", snapshot)]

        @classmethod
        def publish_state_quality(cls, **quality):
            return [("quality", quality)]

        @classmethod
        def publish_messages(cls, messages):
            cls.published.append(messages)

    manager = StateManager(Client(), TopicMapper())

    asyncio.run(manager.sync_state())
    asyncio.run(manager.sync_state())

    snapshot = manager.get_latest_snapshot()
    assert snapshot["components"]["heater"] == {
        "state": "on",
        "temperature": 38.5,
    }
    assert snapshot["components"]["pumps"] == [{"id": "P1", "state": "running"}]
    assert snapshot["quality"]["status"] == "stale"
    assert snapshot["quality"]["observed_at"] == "2026-08-21T12:00:00+00:00"
    assert snapshot["quality"]["last_success_at"] == "2026-08-21T12:00:00+00:00"
    assert snapshot["quality"]["checked_at"] > snapshot["quality"]["observed_at"]
    snapshot_publishes = [
        messages for messages in TopicMapper.published if messages[0][0] == "snapshot"
    ]
    assert len(snapshot_publishes) == 1
    assert TopicMapper.published[-1][0][1]["status"] == "stale"


def test_initial_failed_sync_reports_unavailable_without_component_telemetry():
    class Client:
        @staticmethod
        async def get_state_snapshot():
            raise TimeoutError("cloud unavailable")

    class TopicMapper:
        published: ClassVar[list] = []

        @staticmethod
        def publish_state_snapshot(snapshot):
            raise AssertionError("No component snapshot may be published")

        @classmethod
        def publish_state_quality(cls, **quality):
            return [quality]

        @classmethod
        def publish_messages(cls, messages):
            cls.published.extend(messages)

    manager = StateManager(Client(), TopicMapper())

    asyncio.run(manager.sync_state())

    assert manager.get_latest_snapshot() is None
    assert TopicMapper.published[-1]["status"] == "unavailable"


def test_unchanged_observations_are_published_as_complete_snapshots_each_poll():
    class Client:
        @staticmethod
        async def get_state_snapshot():
            return {
                "spa_id": "spa-test",
                "timestamp": "2026-08-21T12:00:00+00:00",
                "components": {"pumps": [{"id": "P1", "state": "on"}]},
            }

    class TopicMapper:
        snapshots: ClassVar[list] = []

        @classmethod
        def publish_state_snapshot(cls, snapshot):
            cls.snapshots.append(snapshot)
            return []

        @staticmethod
        def publish_state_quality(**_quality):
            return []

        @staticmethod
        def publish_messages(_messages):
            return None

    manager = StateManager(Client(), TopicMapper())

    assert asyncio.run(manager.sync_state()) is True
    assert asyncio.run(manager.sync_state()) is True

    assert manager.PUBLICATION_MODE == "full_snapshot"
    assert len(TopicMapper.snapshots) == 2
    assert (
        TopicMapper.snapshots[0]["components"] == TopicMapper.snapshots[1]["components"]
    )


def test_state_manager_has_no_competing_delta_or_command_registry_api():
    obsolete_paths = {
        "_aggregate_spa_states",
        "_attempt_error_recovery",
        "_detect_changes",
        "_should_update",
        "_trigger_safe_fallback",
        "_update_state",
        "get_pending_commands",
        "reconcile_command_result",
        "register_pending_command",
        "remove_pending_command",
    }

    assert obsolete_paths.isdisjoint(dir(StateManager))
