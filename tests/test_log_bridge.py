"""Regression tests for structured MQTT log forwarding."""

import json

from src.mqtt.log_bridge import CommandAuditLogger, _MQTTForwarder


class _MQTTClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def publish_sync(self, *args, **kwargs) -> None:
        if kwargs:
            self.calls.append((*args, kwargs["qos"], kwargs["retain"]))
        else:
            self.calls.append(args)


def test_mqtt_log_forwarder_respects_enabled_flag():
    mqtt_client = _MQTTClient()
    forwarder = _MQTTForwarder(False, "warning", mqtt_client, "smarttub/meta/logs")

    forwarder(None, "error", {"event": "failure", "level": "error"})

    assert mqtt_client.calls == []


def test_mqtt_log_forwarder_respects_minimum_level():
    mqtt_client = _MQTTClient()
    forwarder = _MQTTForwarder(True, "warning", mqtt_client, "smarttub/meta/logs")

    forwarder(None, "info", {"event": "informational", "level": "info"})
    forwarder(None, "warning", {"event": "warning", "level": "warning"})

    assert len(mqtt_client.calls) == 1
    topic, payload, qos, retain = mqtt_client.calls[0]
    assert topic == "smarttub/meta/logs"
    assert json.loads(payload) == {"event": "warning", "level": "warning"}
    assert (qos, retain) == (0, False)


def test_mqtt_log_forwarder_redacts_secret_fields_and_bearer_tokens():
    mqtt_client = _MQTTClient()
    forwarder = _MQTTForwarder(True, "info", mqtt_client, "smarttub/meta/logs")

    event = forwarder(
        None,
        "info",
        {
            "event": "request",
            "authorization": "Bearer top-secret",
            "error": "upstream token=also-secret",
            "level": "info",
        },
    )

    payload = json.loads(mqtt_client.calls[0][1])
    assert payload["authorization"] == "[REDACTED]"
    assert "top-secret" not in repr(payload)
    assert "also-secret" not in repr(payload)
    assert event == payload


def test_command_audit_forwards_payload_shape_without_values():
    mqtt_client = _MQTTClient()
    config = type(
        "Config",
        (),
        {
            "mqtt": type("Mqtt", (), {"base_topic": "smarttub"})(),
            "logging": type("Logging", (), {"mqtt_forwarding": True})(),
        },
    )()
    audit = CommandAuditLogger(config, mqtt_client)

    audit.log_command_attempt(
        "command-1",
        "set_light_color",
        {"color": "private-value", "token": "secret-value"},
    )

    payload = json.loads(mqtt_client.calls[0][1])
    assert payload["command_params"]["payload_fields"] == [
        "color",
        "[REDACTED]",
    ]
    assert "private-value" not in repr(payload)
    assert "secret-value" not in repr(payload)
