"""Tests for serialization of objects used by discovery probing."""

from src.core.discovery_serialization import make_serializable


class _DiscoveryObject:
    def to_dict(self):
        return {"visible": "value", "nested": [1, 2]}


def test_make_serializable_uses_an_object_to_dict_representation():
    assert make_serializable(_DiscoveryObject()) == {
        "visible": "value",
        "nested": [1, 2],
    }
