"""Central redaction and bounded summaries for diagnostic logging."""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

_SECRET_NAME = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|secret|token|api[_-]?key)"
    r"\s*[:=]\s*([^\s,;&]+)"
)
_JSON_SECRET_ASSIGNMENT = re.compile(
    r'(?i)("(?:authorization|cookie|password|passwd|secret|token|api[_-]?key)"\s*:\s*)'
    r'("(?:\\.|[^"\\])*")'
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")


def redact_text(value: object, *, limit: int = 200) -> str:
    """Redact common credential forms and bound untrusted diagnostic text."""
    text = str(value)
    text = _BEARER.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _JSON_SECRET_ASSIGNMENT.sub(r'\1"[REDACTED]"', text)
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def payload_summary(payload: Any) -> dict[str, Any]:
    """Describe an inbound payload without logging its values."""
    if isinstance(payload, Mapping):
        fields = [
            "[REDACTED]" if _SECRET_NAME.search(str(key)) else str(key)[:64]
            for key in list(payload)[:20]
        ]
        return {
            "payload_type": "mapping",
            "payload_fields": fields,
            "payload_field_count": len(payload),
        }
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return {"payload_type": "bytes", "payload_size": len(payload)}
    if isinstance(payload, str):
        return {"payload_type": "text", "payload_size": len(payload)}
    return {"payload_type": type(payload).__name__}


def _redact_value(value: Any) -> Any:
    """Recursively make a value safe for an event payload."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _SECRET_NAME.search(str(key))
            else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value, limit=500)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"[{type(value).__name__} {len(value)} bytes]"
    if isinstance(value, BaseException):
        return redact_text(value, limit=500)
    return value


def redact_event_dict(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor that redacts secret fields and bounds text values."""
    for key, value in list(event_dict.items()):
        if _SECRET_NAME.search(str(key)):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _redact_value(value)
    return event_dict
