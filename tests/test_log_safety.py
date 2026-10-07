"""Redaction contracts for untrusted diagnostics and command payloads."""

import json
import logging
from io import StringIO
from types import SimpleNamespace

from src.core.log_safety import payload_summary, redact_event_dict, redact_text
from src.mqtt.command_manager import CommandManager
from src.mqtt.log_bridge import _json_formatter


def test_redact_text_removes_credentials_and_truncates_untrusted_text() -> None:
    text = redact_text(
        "Authorization: Bearer abc.def password=hunter2 token=xyz " + "x" * 300,
        limit=100,
    )

    assert "abc.def" not in text
    assert "hunter2" not in text
    assert "xyz" not in text
    assert "[REDACTED]" in text
    assert len(text) == 101
    assert text.endswith("…")


def test_payload_summary_exposes_shape_but_never_values() -> None:
    summary = payload_summary(
        {"brightness": 75, "password": "secret-value", "token": "abc"}
    )

    assert summary == {
        "payload_type": "mapping",
        "payload_fields": ["brightness", "[REDACTED]", "[REDACTED]"],
        "payload_field_count": 3,
    }
    assert "secret-value" not in repr(summary)
    assert "abc" not in repr(summary)


def test_mqtt_command_log_does_not_contain_payload_values(caplog) -> None:
    manager = object.__new__(CommandManager)
    manager.smarttub_client = SimpleNamespace(spas=[])
    secret = "must-not-reach-logs"

    with caplog.at_level(logging.INFO, logger="smarttub.mqtt.commands"):
        manager._handle_command_message(
            "smarttub/spa-1/lights/zone-1/color_writetopic",
            {"color": secret, "token": "also-secret"},
        )

    assert secret not in caplog.text
    assert "also-secret" not in caplog.text
    record = next(
        record for record in caplog.records if record.msg == "mqtt-command-received"
    )
    assert record.payload_type == "mapping"
    assert record.payload_fields == ["color", "[REDACTED]"]


def test_command_transition_log_carries_the_correlation_id(caplog) -> None:
    manager = object.__new__(CommandManager)
    manager._command_history = []
    manager.mqtt_client = None
    manager.config = SimpleNamespace()

    with caplog.at_level(logging.INFO, logger="smarttub.mqtt.commands"):
        command_id = manager._accept_command("set_temperature")

    record = next(
        record for record in caplog.records if record.msg == "command-transition"
    )
    assert record.command_id == command_id
    assert record.command == "set_temperature"
    assert record.status == "accepted"


def test_event_redaction_is_recursive_and_handles_json_credentials() -> None:
    event = redact_event_dict(
        None,
        "error",
        {
            "event": 'upstream failed: {"password": "not-for-logs"}',
            "context": {"token": "also-not-for-logs", "nested": ["ok"]},
        },
    )

    assert "not-for-logs" not in repr(event)
    assert "also-not-for-logs" not in repr(event)
    assert event["context"] == {"token": "[REDACTED]", "nested": ["ok"]}


def test_standard_logging_tracebacks_are_redacted_and_json_encoded() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_json_formatter())
    logger = logging.getLogger("test.safe-json-logging")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)

    try:
        raise RuntimeError("request rejected: token=traceback-secret")
    except RuntimeError:
        logger.exception(
            "external request failed: password=message-secret",
            extra={"request_context": {"authorization": "header-secret"}},
        )

    event = json.loads(stream.getvalue())
    rendered = json.dumps(event)
    assert event["level"] == "error"
    assert event["request_context"] == {"authorization": "[REDACTED]"}
    assert "traceback-secret" not in rendered
    assert "message-secret" not in rendered
    assert "header-secret" not in rendered
    assert "[REDACTED]" in rendered
