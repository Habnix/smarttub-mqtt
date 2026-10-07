"""Tests for Web UI freshness helpers."""

from datetime import UTC, datetime, timedelta

from src.web.view_models import _is_state_stale


def test_missing_or_invalid_state_timestamp_is_stale():
    assert _is_state_stale(None)
    assert _is_state_stale("not-a-timestamp")
    assert _is_state_stale(12345)  # type: ignore[arg-type]


def test_recent_state_timestamp_is_not_stale():
    timestamp = datetime.now(UTC).isoformat()

    assert not _is_state_stale(timestamp)


def test_old_state_timestamp_is_stale():
    timestamp = (datetime.now(UTC) - timedelta(seconds=121)).isoformat()

    assert _is_state_stale(timestamp)
