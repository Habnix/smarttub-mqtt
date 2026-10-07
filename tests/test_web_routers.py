"""Regression tests for the extracted Web API routers."""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.core.command_models import (
    CloudCommandError,
    CommandResult,
    CommandStatus,
)
from src.core.config_loader import (
    AppConfig,
    LoggingConfig,
    MQTTConfig,
    SmartTubConfig,
    WebConfig,
)
from src.core.discovery_result_store import DiscoveryResultStore
from src.web.app import create_app


class _StateManager:
    _last_snapshot = None

    def get_latest_snapshot(self):
        return self._last_snapshot

    @staticmethod
    def get_safe_fallback_state():
        return {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "quality": {
                "status": "unavailable",
                "observed_at": None,
                "last_success_at": None,
                "checked_at": "2026-01-01T00:00:00+00:00",
            },
            "components": {},
        }


class _SmartTubClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.temperature: float | None = None
        self.pump_calls: list[tuple[bool, str | None]] = []
        self.light_state_calls: list[tuple[bool, str | None]] = []
        self.light_color_calls: list[tuple[str, str | None]] = []
        self.light_brightness_calls: list[tuple[int, str | None]] = []
        self.light_mode_calls: list[tuple[str, str | None]] = []

    async def set_temperature(self, temperature: float) -> None:
        self.temperature = temperature

    async def set_pump_state(self, enabled: bool, pump_id: str | None = None) -> None:
        self.pump_calls.append((enabled, pump_id))

    async def set_light_state(self, enabled: bool, light_id: str | None = None) -> None:
        self.light_state_calls.append((enabled, light_id))

    async def set_light_color(self, color: str, light_id: str | None = None) -> None:
        self.light_color_calls.append((color, light_id))

    async def set_light_brightness(
        self, brightness: int, light_id: str | None = None
    ) -> None:
        self.light_brightness_calls.append((brightness, light_id))

    async def set_light_mode(self, mode: str, light_id: str | None = None) -> None:
        self.light_mode_calls.append((mode, light_id))


class _DiscoveryCoordinator:
    async def get_status(self):
        return {"status": "idle"}


_DEFAULT_COORDINATOR = object()


def _client(
    command_manager=None,
    discovery_coordinator=_DEFAULT_COORDINATOR,
    state_manager=None,
    capability_detector=None,
    discovery_result_store=None,
    device_id=None,
    mqtt_connected=True,
    web_ui_refresh_seconds=5,
) -> tuple[TestClient, _SmartTubClient]:
    config = AppConfig(
        smarttub=SmartTubConfig(
            email="spa@example.com", password="secret", device_id=device_id
        ),
        mqtt=MQTTConfig(broker_url="mqtt://broker"),
        web=WebConfig(),
        logging=LoggingConfig(),
    )
    config.web_ui.refresh_interval_seconds = web_ui_refresh_seconds
    smarttub_client = _SmartTubClient()
    coordinator = (
        _DiscoveryCoordinator()
        if discovery_coordinator is _DEFAULT_COORDINATOR
        else discovery_coordinator
    )
    app = create_app(
        config,
        state_manager or _StateManager(),
        smarttub_client=smarttub_client,
        capability_detector=capability_detector,
        discovery_coordinator=coordinator,
        command_manager=command_manager,
        discovery_result_store=discovery_result_store,
        mqtt_broker=SimpleNamespace(is_connected=mqtt_connected),
    )
    return TestClient(app, raise_server_exceptions=False), smarttub_client


def _assert_shared_component_headings(response_text: str) -> None:
    """Keep the user-facing component names identical across web pages."""
    for heading in (
        "Pumpe P1 – Jet",
        "Pumpe P2 – Zirkulation",
        "Licht Zone 1 – Innen",
        "Licht Zone 2 – Außen",
    ):
        assert heading in response_text


def test_liveness_and_readiness_have_distinct_http_contracts():
    state_manager = _StateManager()
    timestamp = datetime.now(UTC).isoformat()
    state_manager._last_snapshot = {
        "timestamp": timestamp,
        "quality": {"status": "live", "observed_at": timestamp},
        "components": {},
    }
    command_manager = SimpleNamespace(is_worker_running=True)
    client, _ = _client(
        state_manager=state_manager,
        command_manager=command_manager,
    )

    live = client.get("/live")
    ready = client.get("/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "live"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_readiness_returns_503_while_mqtt_is_disconnected():
    state_manager = _StateManager()
    timestamp = datetime.now(UTC).isoformat()
    state_manager._last_snapshot = {
        "timestamp": timestamp,
        "quality": {"status": "live", "observed_at": timestamp},
        "components": {},
    }
    client, _ = _client(
        state_manager=state_manager,
        command_manager=SimpleNamespace(is_worker_running=True),
        mqtt_connected=False,
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["components"]["mqtt"]["status"] == "not_ready"


def test_extracted_routers_keep_the_public_command_and_discovery_routes():
    client, _ = _client()
    paths = {route.path for route in client.app.routes if hasattr(route, "path")}
    for route in client.app.routes:
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            paths.update(child_route.path for child_route in included_router.routes)

    assert {
        "/api/commands/set_temperature",
        "/api/commands/set_heat_mode",
        "/api/commands/set_filtration_mode",
        "/api/commands/set_pump_state",
        "/api/commands/set_light_state",
        "/api/commands/set_light_color",
        "/api/commands/set_light_brightness",
        "/api/commands/set_light_mode",
        "/api/commands/history",
        "/api/discovery/progress",
        "/api/discovery/progress/{spa_id}",
        "/api/discovery/status",
        "/api/discovery/start",
        "/api/discovery/stop",
        "/api/discovery/results",
        "/api/discovery/reset",
    }.issubset(paths)


def test_web_assets_are_available_outside_the_repository_working_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    client, _ = _client()

    response = client.get("/static/ui.js")

    assert response.status_code == 200
    assert "refreshDashboardState" in response.text


def test_state_api_reports_unavailable_without_invented_components():
    client, _ = _client()

    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json()["quality"]["status"] == "unavailable"
    assert response.json()["components"] == {}


def test_command_router_delegates_to_the_supplied_smarttub_client():
    client, smarttub_client = _client()

    response = client.post("/api/commands/set_temperature", json={"temperature": 37.5})

    assert response.status_code == 200
    assert smarttub_client.temperature == 37.5
    assert response.json()["message"] == "Temperature command sent for 37.5°C"
    assert response.json()["status"] == "sent"
    assert response.json()["command"]["status"] == "sent"
    assert response.json()["command"]["command_id"]


def test_component_commands_target_the_requested_pump_or_light():
    client, smarttub_client = _client()

    pump = client.post(
        "/api/commands/set_pump_state", json={"state": "on", "pump_id": "P2"}
    )
    light_state = client.post(
        "/api/commands/set_light_state",
        json={"state": "off", "light_id": "zone_2"},
    )
    color = client.post(
        "/api/commands/set_light_color",
        json={"color": "#00ff00", "light_id": "zone_2"},
    )
    brightness = client.post(
        "/api/commands/set_light_brightness",
        json={"brightness": 70, "light_id": "zone_2"},
    )
    mode = client.post(
        "/api/commands/set_light_mode",
        json={"mode": "OFF", "light_id": "zone_2"},
    )

    assert [
        response.status_code
        for response in (pump, light_state, color, brightness, mode)
    ] == [
        200,
        200,
        200,
        200,
        200,
    ]
    assert smarttub_client.pump_calls == [(True, "P2")]
    assert smarttub_client.light_state_calls == [(False, "zone_2")]
    assert smarttub_client.light_color_calls == [("#00ff00", "zone_2")]
    assert smarttub_client.light_brightness_calls == [(70, "zone_2")]
    assert smarttub_client.light_mode_calls == [("OFF", "zone_2")]


def test_light_mode_commands_are_limited_to_discovered_modes(tmp_path):
    store = DiscoveryResultStore(tmp_path / "discovered_items.yaml")
    store.save_light_modes(
        {
            "spas": {
                "spa-test": {
                    "lights": [{"id": "zone_2", "detected_modes": ["OFF", "WHITE"]}]
                }
            }
        }
    )
    client, smarttub_client = _client(
        discovery_result_store=store, device_id="spa-test"
    )

    accepted = client.post(
        "/api/commands/set_light_mode",
        json={"mode": "white", "light_id": "zone_2"},
    )
    rejected = client.post(
        "/api/commands/set_light_mode",
        json={"mode": "PURPLE", "light_id": "zone_2"},
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 422
    assert smarttub_client.light_mode_calls == [("WHITE", "zone_2")]


def test_component_commands_require_an_explicit_component_id():
    client, _ = _client()

    response = client.post("/api/commands/set_pump_state", json={"state": "on"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "pump_id"]


def test_command_router_uses_the_serialized_command_manager_when_available():
    class CommandManager:
        def __init__(self) -> None:
            self.calls = []

        async def execute_command(self, path, payload) -> None:
            self.calls.append((path, payload))

    command_manager = CommandManager()
    client, smarttub_client = _client(command_manager)

    response = client.post("/api/commands/set_temperature", json={"temperature": 37.5})

    assert response.status_code == 200
    assert command_manager.calls == [
        ("heater/target_temperature_writetopic", {"temperature": 37.5})
    ]
    assert smarttub_client.temperature is None


def test_unverified_temperature_is_not_reported_as_a_failed_command():
    class CommandManager:
        @staticmethod
        async def execute_command(path, payload):
            return CommandResult(
                "temperature-command",
                path,
                CommandStatus.UNKNOWN,
                "Command was sent but its result could not be verified",
            )

    client, _ = _client(command_manager=CommandManager())

    response = client.post("/api/commands/set_temperature", json={"temperature": 26})

    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert response.json()["message"] == "Temperature command sent for 26.0°C"


def test_component_commands_preserve_ids_through_the_serialized_queue():
    class CommandManager:
        def __init__(self) -> None:
            self.calls = []

        async def execute_command(self, path, payload) -> None:
            self.calls.append((path, payload))

    command_manager = CommandManager()
    client, _ = _client(command_manager)

    response = client.post(
        "/api/commands/set_light_state",
        json={"state": "on", "light_id": "zone_3"},
    )

    assert response.status_code == 200
    assert command_manager.calls == [
        ("lights/state_writetopic", {"state": "on", "light_id": "zone_3"})
    ]


def test_command_history_comes_from_the_command_manager():
    class CommandManager:
        @staticmethod
        def get_command_history():
            return [
                {
                    "timestamp": "2026-08-21T12:00:00+00:00",
                    "command": "heater/target_temperature_writetopic",
                    "status": "success",
                    "message": "Command executed",
                }
            ]

    client, _ = _client(CommandManager())

    response = client.get("/api/commands/history")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["commands"][0]["command"] == (
        "heater/target_temperature_writetopic"
    )


def test_command_request_model_returns_a_validation_error_not_a_server_error():
    client, _ = _client()

    response = client.post("/api/commands/set_temperature", json={})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "temperature"]


def test_http_temperature_uses_detected_capability_bounds():
    capability_detector = SimpleNamespace(
        get_cached_capabilities=lambda _spa_id: SimpleNamespace(
            heater_temperature_range={"min": 20.0, "max": 40.0}
        )
    )
    client, smarttub_client = _client(
        capability_detector=capability_detector, device_id="spa-test"
    )

    response = client.post("/api/commands/set_temperature", json={"temperature": 40.5})

    assert response.status_code == 422
    assert response.headers["x-command-error-code"] == "validation_error"
    assert smarttub_client.temperature is None


def test_command_errors_do_not_disclose_internal_exception_details(caplog):
    class CommandManager:
        @staticmethod
        async def execute_command(path, payload) -> None:
            raise RuntimeError("credential=not-for-clients")

    client, _ = _client(command_manager=CommandManager())

    response = client.post("/api/commands/set_temperature", json={"temperature": 37.5})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "credential=not-for-clients" not in response.text
    assert "credential=not-for-clients" in caplog.text


def test_expected_cloud_command_errors_return_service_unavailable():
    class CommandManager:
        @staticmethod
        async def execute_command(path, payload) -> None:
            raise CloudCommandError("internal cloud response")

    client, _ = _client(command_manager=CommandManager())

    response = client.post("/api/commands/set_temperature", json={"temperature": 37.5})

    assert response.status_code == 503
    assert response.json() == {"detail": "SmartTub command failed"}
    assert "internal cloud response" not in response.text


def test_state_errors_do_not_disclose_internal_exception_details(caplog):
    class BrokenStateManager:
        _last_snapshot = None

        @staticmethod
        def get_latest_snapshot():
            raise RuntimeError("credential=not-for-clients")

        @staticmethod
        def get_safe_fallback_state():
            raise RuntimeError("credential=not-for-clients")

    client, _ = _client(state_manager=BrokenStateManager())

    response = client.get("/api/state")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "credential=not-for-clients" not in response.text
    assert "credential=not-for-clients" in caplog.text


def test_controls_use_the_shared_json_command_client():
    client, _ = _client()

    controls = client.get("/controls")
    script = client.get("/static/ui.js")
    stylesheet = client.get("/static/app.css")

    assert controls.status_code == 200
    assert "hx-post=" not in controls.text
    assert "Whirlpool-Steuerung" in controls.text
    assert "font-awesome" not in controls.text
    assert "Einschalten" not in controls.text
    assert script.status_code == 200
    assert "data-command-form" in script.text
    assert 'Content-Type": "application/json"' in script.text
    assert stylesheet.status_code == 200
    assert "--st-primary" in stylesheet.text


def test_controls_render_observed_target_temperature_and_capability_bounds():
    class StateManager:
        @staticmethod
        def get_latest_snapshot():
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "components": {
                    "spa": {"state": "ready"},
                    "heater": {"state": "off", "target_temperature": 38.5},
                    "pumps": [],
                    "lights": [],
                },
            }

        @staticmethod
        def get_safe_fallback_state():
            raise AssertionError("A current state is available")

    class CapabilityDetector:
        @staticmethod
        def get_cached_profiles():
            return {
                "spa-test": {
                    "supported_features": {"heater": True},
                    "heater": {
                        "temperature_range": {"min": 18.0, "max": 40.0},
                        "modes": ["AUTO"],
                    },
                }
            }

    client, _ = _client(
        state_manager=StateManager(),
        capability_detector=CapabilityDetector(),
        device_id="spa-test",
    )

    response = client.get("/controls")

    assert response.status_code == 200
    assert 'id="temperature"' in response.text
    assert 'min="18.0"' in response.text
    assert 'max="40.0"' in response.text
    assert 'value="38.5"' in response.text
    assert 'value="37.0"' not in response.text


def test_controls_render_one_targeted_card_per_pump_and_light():
    class StateManager:
        @staticmethod
        def get_latest_snapshot():
            return {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "components": {
                    "spa": {"state": "ready"},
                    "heater": {"state": "off"},
                    "pumps": [
                        {"id": "P1", "type": "jet"},
                        {"id": "P2", "type": "circulation"},
                    ],
                    "lights": [
                        {
                            "id": "zone_2",
                            "type": "exterior",
                            "color": "#00ff00",
                            "brightness": 70,
                        },
                        {
                            "id": "zone_1",
                            "type": "interior",
                            "color": "#ffffff",
                            "brightness": 50,
                        },
                    ],
                },
            }

        @staticmethod
        def get_safe_fallback_state():
            raise AssertionError("A current state is available")

    class CapabilityDetector:
        @staticmethod
        def get_cached_profiles():
            return {
                "spa-test": {
                    "supported_features": {"pump": True, "light": True},
                }
            }

    client, _ = _client(
        state_manager=StateManager(), capability_detector=CapabilityDetector()
    )

    response = client.get("/controls")

    assert response.status_code == 200
    assert '"pump_id": "P1"' in response.text
    assert '"pump_id": "P2"' in response.text
    assert 'name="light_id" value="zone_1"' in response.text
    assert 'name="light_id" value="zone_2"' in response.text
    assert response.text.index("Licht Zone 1") < response.text.index("Licht Zone 2")
    _assert_shared_component_headings(response.text)
    assert 'name="spa_id"' not in response.text

    overview = client.get("/")

    assert overview.status_code == 200
    _assert_shared_component_headings(overview.text)


def test_controls_render_discovered_light_modes(monkeypatch):
    class StateManager:
        @staticmethod
        def get_latest_snapshot():
            return {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "components": {
                    "spa": {"state": "ready"},
                    "heater": {"state": "off"},
                    "pumps": [],
                    "lights": [
                        {
                            "id": "zone_2",
                            "zone": 2,
                            "type": "exterior",
                            "mode": "WHITE",
                            "color": "#ffffff",
                            "brightness": 50,
                        }
                    ],
                },
            }

        @staticmethod
        def get_safe_fallback_state():
            raise AssertionError("A current state is available")

    class CapabilityDetector:
        @staticmethod
        def get_cached_profiles():
            return {
                "spa-test": {
                    "supported_features": {"pump": False, "light": True},
                }
            }

    async def load_discovered_items():
        return {
            "spa-test": {
                "lights": [
                    {
                        "id": "zone_2",
                        "detected_modes": ["WHITE", "LOW_SPEED_WHEEL"],
                    }
                ]
            }
        }

    monkeypatch.setattr(
        "src.web.view_models._load_discovered_items",
        load_discovered_items,
    )
    client, _ = _client(
        state_manager=StateManager(), capability_detector=CapabilityDetector()
    )

    response = client.get("/controls")

    assert response.status_code == 200
    assert 'action="/api/commands/set_light_mode"' in response.text
    assert "data-light-mode-select" in response.text
    assert "Lichtmodus setzen" not in response.text
    assert 'value="OFF"' in response.text
    assert 'value="LOW_SPEED_WHEEL"' in response.text


def test_pages_render_the_shared_german_navigation():
    client, _ = _client()

    for path, active_href, active_label in (
        ("/", "/", "Übersicht"),
        ("/controls", "/controls", "Steuerung"),
        ("/discovery", "/discovery", "Erkennung"),
    ):
        response = client.get(path)

        assert response.status_code == 200
        assert "SmartTub MQTT Bridge" in response.text
        assert "Whirlpool: wird bestimmt" in response.text
        assert f'href="{active_href}"' in response.text
        assert f'aria-current="page">{active_label}</a>' in response.text
        assert "data-navigation-toggle" in response.text


def test_pages_use_the_shared_base_template_and_local_browser_script():
    client, _ = _client()

    response = client.get("/controls")
    stylesheet = client.get("/static/bootstrap.min.css")

    assert response.status_code == 200
    assert stylesheet.status_code == 200
    assert 'href="/static/bootstrap.min.css"' in response.text
    assert "cdn.jsdelivr.net" not in response.text
    assert 'src="/static/ui.js"' in response.text
    assert "bootstrap.bundle.min.js" not in response.text


def test_dashboard_refreshes_server_state_without_reloading_the_page():
    client, _ = _client(web_ui_refresh_seconds=17)

    overview = client.get("/")
    script = client.get("/static/ui.js")

    assert overview.status_code == 200
    assert 'id="state-notice"' in overview.text
    assert 'data-state-available="false"' in overview.text
    assert 'data-state-refresh-ms="17000"' in overview.text
    assert "refreshDashboardState" in script.text
    assert 'fetch("/api/state"' in script.text
    assert "updatePumpCards(components.pumps)" in script.text
    assert "updateLightCards(components.lights)" in script.text
    assert (
        'if (value === null || value === undefined || value === "") return "—"'
        in script.text
    )
    assert "window.location.reload" not in script.text


def test_discovery_router_uses_the_supplied_coordinator():
    client, _ = _client()

    response = client.get("/api/discovery/status")

    assert response.status_code == 200
    assert response.json() == {"status": "idle"}


def test_discovery_page_explains_modes_without_an_icon_cdn():
    client, _ = _client()

    response = client.get("/discovery")
    script = client.get("/static/discovery.js")
    stylesheet = client.get("/static/app.css")

    assert response.status_code == 200
    assert "Lichtmodi erkennen" in response.text
    assert "font-awesome" not in response.text
    assert 'type="radio"' in response.text
    assert 'name="discovery-mode"' in response.text
    assert 'class="card mode-card h-100"' in response.text
    assert 'role="radio"' not in response.text
    assert 'for="mode-yaml-only"' in response.text
    assert 'for="mode-quick"' in response.text
    assert 'for="mode-full"' in response.text
    assert 'id="mode-selection-error"' in response.text
    assert "onclick=" not in response.text
    assert "innerHTML" not in response.text
    assert 'src="/static/discovery.js"' in response.text
    assert 'id="results-status-summary"' in response.text
    assert 'id="results-restore-summary"' in response.text
    assert "Prüfergebnisse" in response.text
    assert script.status_code == 200
    assert (
        "Der vollständige Durchlauf verändert nacheinander die Lichtmodi" in script.text
    )
    assert "createModeResultsDetails" in script.text
    assert 'querySelectorAll(".mode-input")' in script.text
    assert 'addEventListener("keydown"' not in script.text
    assert "setModeSelectionError" in script.text
    assert "innerHTML" not in script.text
    assert ".mode-input:focus-visible + .mode-card" in stylesheet.text
    assert ".mode-selection.has-error .mode-card" in stylesheet.text


def test_discovery_status_explains_when_the_service_is_unavailable():
    client, _ = _client(discovery_coordinator=None)

    response = client.get("/api/discovery/status")

    assert response.status_code == 503
    assert response.json() == {"detail": "Discovery coordinator not available"}


def test_discovery_errors_do_not_disclose_internal_exception_details(caplog):
    class BrokenCoordinator:
        @staticmethod
        async def get_status():
            raise RuntimeError("credential=not-for-clients")

    client, _ = _client(discovery_coordinator=BrokenCoordinator())

    response = client.get("/api/discovery/status")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "credential=not-for-clients" not in response.text
    assert "credential=not-for-clients" in caplog.text


def test_discovery_status_hides_coordinator_error_details(caplog):
    class FailedCoordinator:
        @staticmethod
        async def get_status():
            return {"success": False, "error": "credential=not-for-clients"}

    client, _ = _client(discovery_coordinator=FailedCoordinator())

    response = client.get("/api/discovery/status")

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "Discovery status unavailable",
    }
    assert "credential=not-for-clients" not in response.text
    assert "credential=not-for-clients" in caplog.text
