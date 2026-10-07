"""Regression tests for snapshot publication delegation."""

from src.core.state_publisher import StatePublisher


class _Mapper:
    def __init__(self):
        self.published = []

    def publish_state_snapshot(self, snapshot):
        return [snapshot["timestamp"], snapshot["components"]]

    def publish_messages(self, messages):
        self.published.append(messages)


def test_state_publisher_maps_and_publishes_one_snapshot():
    mapper = _Mapper()
    publisher = StatePublisher(mapper)
    snapshot = {"timestamp": "now", "components": {"spa": {"state": "READY"}}}

    count = publisher.publish(snapshot)

    assert count == 2
    assert mapper.published == [["now", {"spa": {"state": "READY"}}]]
