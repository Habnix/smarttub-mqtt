from __future__ import annotations

import copy
import inspect
import types
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

import pytest

from src.core.config_loader import (
    AppConfig,
    DockerConfig,
    LoggingConfig,
    MQTTConfig,
    MQTTTLSConfig,
    ObservabilityConfig,
    SafetyConfig,
    SmartTubConfig,
    WebConfig,
    WebUIConfig,
)


try:  # pragma: no cover - library availability depends on environment
    from smarttub.api import LoginFailed as SmartTubLoginFailed  # type: ignore
except Exception:  # pragma: no cover - fallback when dependency missing

    class SmartTubLoginFailed(RuntimeError):
        pass


@dataclass
class PublishedMessage:
    topic: str
    payload: Any
    qos: int
    retain: bool


@dataclass
class FakePublishResult:
    mid: int
    rc: int = 0

    def wait_for_publish(self) -> bool:
        return True


class FakeMQTTClient:
    def __init__(self) -> None:
        self.connected: bool = False
        self.loop_running: bool = False
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.logger = None
        self.reconnect_settings: Tuple[int, int] | None = None
        self.tls_ca_cert_path: Optional[str] = None
        self.published_messages: list[PublishedMessage] = []
        self.publish_mid: int = 0
        self.connect_args: Tuple[str, int, int] | None = None
        self.reconnect_calls: list[Tuple[str, int, int]] = []
        self.disconnect_calls: int = 0
        self.enable_logger_calls: int = 0
        self.on_connect = None
        self.on_disconnect = None
        self.publish_hook: Callable[[str, Any, int, bool], Any] | None = None

    # ------------------------------------------------------------------
    # paho.mqtt style API
    # ------------------------------------------------------------------
    def enable_logger(self, logger: Any) -> None:
        self.logger = logger
        self.enable_logger_calls += 1

    def username_pw_set(
        self, username: str | None, password: str | None = None
    ) -> None:
        self.username = username
        self.password = password

    def tls_set(self, *, ca_certs: str | None = None, **_: Any) -> None:
        self.tls_ca_cert_path = ca_certs

    def reconnect_delay_set(self, *, min_delay: int, max_delay: int) -> None:
        self.reconnect_settings = (min_delay, max_delay)

    def connect(self, host: str, port: int, keepalive: int = 60) -> None:
        self.connected = True
        self.connect_args = (host, port, keepalive)
        if self.on_connect is not None:
            self.on_connect(
                self, None, None, types.SimpleNamespace(is_failure=False, value=0), None
            )  # type: ignore[name-defined]

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.connected = False
        self.disconnect_calls += 1
        if self.on_disconnect is not None:
            self.on_disconnect(
                self,
                None,
                types.SimpleNamespace(is_disconnect_packet_from_server=False),  # type: ignore[name-defined]
                types.SimpleNamespace(is_failure=False, value=0),
                None,
            )

    def loop_start(self) -> None:
        self.loop_running = True

    def loop_stop(self) -> None:
        self.loop_running = False

    def reconnect(self) -> None:
        if self.connect_args is None:
            raise RuntimeError("connect must be called before reconnect")
        self.reconnect_calls.append(self.connect_args)

    def publish(
        self, topic: str, payload: Any = None, qos: int = 0, retain: bool = False
    ) -> FakePublishResult:
        if self.publish_hook is not None:
            return self.publish_hook(topic, payload, qos, retain)
        self.publish_mid += 1
        message = PublishedMessage(topic=topic, payload=payload, qos=qos, retain=retain)
        self.published_messages.append(message)
        return FakePublishResult(mid=self.publish_mid)


class FakeSpa:
    def __init__(
        self,
        spa_id: str = "spa-1",
        *,
        name: Optional[str] = None,
        status: Optional[dict[str, Any]] = None,
        full_status: Optional[dict[str, Any]] = None,
        pumps: Optional[Iterable[dict[str, Any]]] = None,
        lights: Optional[Iterable[dict[str, Any]]] = None,
        errors: Optional[Iterable[dict[str, Any]]] = None,
        reminders: Optional[Iterable[dict[str, Any]]] = None,
        debug_status: Optional[dict[str, Any]] = None,
    ) -> None:
        self.id = spa_id
        self.name = name or spa_id
        self._status = status or {"state": "READY"}
        self._full_status = full_status
        self._pumps = [copy.deepcopy(item) for item in pumps or []]
        self._lights = [copy.deepcopy(item) for item in lights or []]
        self._errors = [copy.deepcopy(item) for item in errors or []]
        self._reminders = [copy.deepcopy(item) for item in reminders or []]
        self._debug_status = (
            copy.deepcopy(debug_status) if debug_status is not None else None
        )
        self.requests: list[tuple[str, str, Any]] = []
        self._request_handlers: Dict[tuple[str, str], Callable[[Any], Any] | Any] = {}

    # ------------------------------------------------------------------
    # SmartTub API surface
    # ------------------------------------------------------------------
    async def request(self, method: str, resource: str, body: Any | None = None) -> Any:
        key = (method.upper(), resource)
        self.requests.append((method.upper(), resource, copy.deepcopy(body)))
        handler = self._request_handlers.get(key)
        if handler is None:
            return None
        result = handler(body) if callable(handler) else handler
        if inspect.isawaitable(result):
            result = await result  # type: ignore[assignment]
        return copy.deepcopy(result)

    async def get_status(self) -> dict[str, Any]:
        return copy.deepcopy(self._status)

    async def get_status_full(self) -> dict[str, Any]:
        source = self._full_status or self._status
        return copy.deepcopy(source)

    async def get_pumps(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._pumps]

    async def get_lights(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._lights]

    async def get_errors(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._errors]

    async def get_reminders(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._reminders]

    async def get_debug_status(self) -> dict[str, Any]:
        return copy.deepcopy(self._debug_status or {})

    # ------------------------------------------------------------------
    # Mutation helpers for tests
    # ------------------------------------------------------------------
    def set_status(self, status: dict[str, Any]) -> None:
        self._status = copy.deepcopy(status)

    def set_full_status(self, status: dict[str, Any]) -> None:
        self._full_status = copy.deepcopy(status)

    def set_pumps(self, pumps: Iterable[dict[str, Any]]) -> None:
        self._pumps = [copy.deepcopy(item) for item in pumps]

    def set_lights(self, lights: Iterable[dict[str, Any]]) -> None:
        self._lights = [copy.deepcopy(item) for item in lights]

    def set_errors(self, errors: Iterable[dict[str, Any]]) -> None:
        self._errors = [copy.deepcopy(item) for item in errors]

    def set_reminders(self, reminders: Iterable[dict[str, Any]]) -> None:
        self._reminders = [copy.deepcopy(item) for item in reminders]

    def set_debug_status(self, status: dict[str, Any]) -> None:
        self._debug_status = copy.deepcopy(status)

    def set_request_handler(
        self, method: str, resource: str, handler: Callable[[Any], Any] | Any
    ) -> None:
        self._request_handlers[(method.upper(), resource)] = handler


class FakeAccount:
    def __init__(
        self, account_id: str = "account-1", spas: Optional[Iterable[FakeSpa]] = None
    ) -> None:
        self.id = account_id
        self.email = f"{account_id}@example.com"
        self.properties: dict[str, Any] = {"id": account_id, "email": self.email}
        self._spas: dict[str, FakeSpa] = {}
        for spa in spas or []:
            self.add_spa(spa)

    async def get_spas(self) -> list[FakeSpa]:
        return list(self._spas.values())

    async def get_spa(self, spa_id: str) -> FakeSpa:
        return self._spas[spa_id]

    def add_spa(self, spa: FakeSpa) -> None:
        self._spas[spa.id] = spa


class FakeSmartTub:
    def __init__(self, account: Optional[FakeAccount] = None) -> None:
        self._account = account or FakeAccount(spas=[FakeSpa()])
        self.logged_in: bool = False
        self.login_credentials: list[tuple[str, str]] = []
        self.should_fail_login: bool = False

    async def login(self, username: str, password: str) -> None:
        self.login_credentials.append((username, password))
        if self.should_fail_login:
            raise SmartTubLoginFailed("login rejected by FakeSmartTub")
        self.logged_in = True

    async def get_account(self) -> FakeAccount:
        if not self.logged_in:
            raise RuntimeError("SmartTub session not authenticated")
        return self._account

    def set_account(self, account: FakeAccount) -> None:
        self._account = account

    def add_spa(self, spa: FakeSpa) -> FakeSpa:
        self._account.add_spa(spa)
        return spa


def _build_base_app_config() -> AppConfig:
    smarttub = SmartTubConfig(
        email="user@example.com",
        password="secret",
        device_id="device-123",
        token=None,
        polling_interval_seconds=30,
        max_retries=2,
        retry_backoff_seconds=5,
    )

    mqtt_cfg = MQTTConfig(
        broker_url="mqtt://localhost:1883",
        username="mqtt-user",
        password="mqtt-pass",
        client_id="smarttub-mqtt-client",
        base_topic="smarttub-mqtt",
        qos=1,
        retain=True,
        tls=MQTTTLSConfig(enabled=False, ca_cert_path=""),
    )

    config = AppConfig(
        smarttub=smarttub,
        mqtt=mqtt_cfg,
        web=WebConfig(),
        logging=LoggingConfig(),
        observability=ObservabilityConfig(),
        web_ui=WebUIConfig(),
        safety=SafetyConfig(),
        docker=DockerConfig(),
    )

    # Tests expect reconnect tuning fields to exist on the config.
    config.mqtt.reconnect_min_seconds = 1
    config.mqtt.reconnect_max_seconds = 8
    config.mqtt.keepalive_seconds = 60

    return config


def _apply_section_overrides(config: AppConfig, section: str, override: Any) -> None:
    target = getattr(config, section)
    if isinstance(override, dict):
        for key, value in override.items():
            setattr(target, key, value)
    else:
        setattr(config, section, override)


def _apply_dotted_overrides(config: AppConfig, overrides: Dict[str, Any]) -> None:
    for path, value in overrides.items():
        segments = path.split(".")
        current: Any = config
        for segment in segments[:-1]:
            current = getattr(current, segment)
        setattr(current, segments[-1], value)


@pytest.fixture
def app_config_factory() -> Callable[..., AppConfig]:
    def factory(
        *, overrides: Optional[Dict[str, Any]] = None, **sections: Any
    ) -> AppConfig:
        config = _build_base_app_config()

        for section, override in sections.items():
            _apply_section_overrides(config, section, override)

        if overrides:
            _apply_dotted_overrides(config, overrides)

        return config

    return factory


@pytest.fixture
def fake_mqtt_client() -> FakeMQTTClient:
    return FakeMQTTClient()


@pytest.fixture
def fake_smarttub() -> FakeSmartTub:
    return FakeSmartTub()


@pytest.fixture
def smarttub_spa_factory() -> Callable[..., FakeSpa]:
    def factory(**kwargs: Any) -> FakeSpa:
        return FakeSpa(**kwargs)

    return factory


@pytest.fixture
def config_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def apply(**env: Any) -> None:
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, str(value))

    return apply


@pytest.fixture
def reset_structlog() -> Iterable[None]:
    import structlog

    structlog.reset_defaults()
    yield
    structlog.reset_defaults()
