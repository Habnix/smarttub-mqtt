"""Browser smoke tests for the primary Web UI navigation.

The test is skipped locally when Playwright is not installed. CI installs its
Chromium runtime before running the test suite.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytest.importorskip("playwright.sync_api", reason="Playwright is only required in CI")

from playwright.sync_api import Page, expect
from uvicorn import Config, Server

from src.core.config_loader import (
    AppConfig,
    LoggingConfig,
    MQTTConfig,
    SmartTubConfig,
    WebConfig,
)
from src.web.app import create_app


class _StateManager:
    _last_snapshot = None

    def get_latest_snapshot(self):
        return self._last_snapshot

    @staticmethod
    def get_safe_fallback_state():
        return {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "components": {
                "spa": {
                    "state": "unknown",
                    "water_temperature": None,
                    "air_temperature": None,
                },
                "heater": {"state": "off"},
                "pumps": [],
                "lights": [],
            },
        }


@contextmanager
def _serve_web_app() -> Iterator[str]:
    """Run the ASGI app on a local TCP socket for browser-level tests."""
    config = AppConfig(
        smarttub=SmartTubConfig(
            email="spa@example.com", password="secret", device_id="spa-test"
        ),
        mqtt=MQTTConfig(broker_url="mqtt://broker"),
        web=WebConfig(),
        logging=LoggingConfig(),
    )
    app = create_app(config, _StateManager())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = Server(Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Web test server did not start")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_primary_navigation_is_usable_in_a_browser(page: Page):
    with _serve_web_app() as base_url:
        page.goto(base_url, wait_until="networkidle")
        expect(page.get_by_role("heading", name="Whirlpool-Status")).to_be_visible()
        expect(page.get_by_text("Whirlpool: spa-test")).to_be_visible()

        page.get_by_role("link", name="Steuerung").click()
        expect(page.get_by_role("heading", name="Whirlpool-Steuerung")).to_be_visible()

        page.get_by_role("link", name="Erkennung").click()
        expect(page.get_by_role("heading", name="Lichtmodi erkennen")).to_be_visible()
        expect(page.get_by_role("radio", name="Vollständiger Test")).to_be_visible()
