# MyPy-Fehlerliste

Diese Liste dokumentiert den ursprünglichen MyPy-Bestand und den inzwischen abgeschlossenen Abbau. Sie bleibt als nachvollziehbare Fehlerhistorie erhalten.

- Erfasst am: 16.08.2026
- Befehl: `mypy src/ --ignore-missing-imports --show-error-codes`
- Ausgangsstand: 90 Fehler in 17 Dateien
- Aktueller Stand: 0 Fehler in 35 geprüften Quelldateien
- Hinweise von MyPy (`note:`) sind nicht als eigene Fehler gezählt.
- Ergebnis: Alle 90 ursprünglichen Fehler wurden behoben. Hinweise von MyPy zu untypisierten Funktionskörpern bleiben reine Hinweise.

## Empfohlene Reihenfolge

1. Gemeinsame Typmodelle und Rückgabewerte (`StateSnapshot`, `Collection[str]`, MQTT-Daten).
2. Falsche oder fehlende Typimporte (`Callable`, `Any`, `Optional`).
3. Async-Signaturen und `await`.
4. Web-, Discovery- und Entry-Point-Signaturen.
5. Restliche dynamische Daten aus Konfiguration und Discovery.

## `src/core/smarttub_state_reader.py` — 12 Fehler

- [x] `:60` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:71` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:91` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:110` — Value of type `Collection[str]` is not indexable `[index]`
- [x] `:118` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:121` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:135` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:209` — Value of type `Collection[str]` is not indexable `[index]`
- [x] `:217` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:220` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:227` — Unsupported target for indexed assignment (`Collection[str]`) `[index]`
- [x] `:234` — Incompatible return value type (got `dict[str, Collection[str]]`, expected `StateSnapshot`) `[return-value]`

## `src/core/error_tracker.py` — 5 Fehler

- [x] `:93` — Function `builtins.callable` is not valid as a type `[valid-type]`
- [x] `:155` — Function `builtins.callable` is not valid as a type `[valid-type]`
- [x] `:183` — `callable?` not callable `[misc]`
- [x] `:189` — `callable?` not callable `[misc]`
- [x] `:212` — Function `builtins.callable` is not valid as a type `[valid-type]`

## `src/core/config_loader.py` — 1 Fehler

- [x] `:140` — Argument 1 to `from_dict` of `MQTTTLSConfig` has incompatible type `Any | dict[Any, Any] | None`; expected `Mapping[str, Any]` `[arg-type]`

## `src/core/smarttub_client.py` — 3 Fehler

- [x] `:34` — `None` has no attribute `login` `[attr-defined]`
- [x] `:38` — `None` has no attribute `get_account` `[attr-defined]`
- [x] `:39` — `None` has no attribute `get_spas` `[attr-defined]`

## `src/core/state_publisher.py` — 1 Fehler

- [x] `:19` — Argument 1 to `publish_state_snapshot` of `MQTTTopicMapper` has incompatible type `StateSnapshot | dict[str, Any]`; expected `dict[str, Any]` `[arg-type]`

## `src/core/state_manager.py` — 3 Fehler

- [x] `:176` — Incompatible return value type (got `Coroutine[Any, Any, bool]`, expected `bool`) `[return-value]`
- [x] `:203` — Argument 3 to `_verify_command_success` of `StateManager` has incompatible type `StateSnapshot`; expected `dict[str, Any]` `[arg-type]`
- [x] `:293` — Incompatible types in assignment (expression has type `dict[str, Any]`, variable has type `StateSnapshot | None`) `[assignment]`

## `src/mqtt/command_manager.py` — 2 Fehler

- [x] `:176` — Incompatible default for parameter `pump_id` (default has type `None`, parameter has type `str`) `[assignment]`
- [x] `:176` — Incompatible default for parameter `light_id` (default has type `None`, parameter has type `str`) `[assignment]`

## `src/core/item_prober.py` — 11 Fehler

- [x] `:170` — Need type annotation for `snapshot` `[var-annotated]`
- [x] `:214` — Item `str` of `list[Any] | Any | str` has no attribute `append` `[union-attr]`
- [x] `:214` — Invalid index type `str` for `str`; expected `SupportsIndex | slice[...]` `[index]`
- [x] `:1077` — Argument 5 to `_test_light_mode` has incompatible type `Any | None`; expected `int` `[arg-type]`
- [x] `:1125` — Argument 5 to `_test_light_mode` has incompatible type `Any | None`; expected `int` `[arg-type]`
- [x] `:1166` — Argument 2 to `_test_rgb_color_capability` has incompatible type `Any | None`; expected `int` `[arg-type]`
- [x] `:1274` — Unsupported target for indexed assignment (`object`) `[index]`
- [x] `:1286` — Unsupported operand types for `>` (`int` and `object`) `[operator]`
- [x] `:1289` — Unsupported target for indexed assignment (`object`) `[index]`
- [x] `:1306` — Unsupported target for indexed assignment (`object`) `[index]`
- [x] `:1534` — Item `None` of `Any | None` has no attribute `name` `[union-attr]`

## `src/core/discovery_state.py` — 5 Fehler

- [x] `:330` — Argument 1 to `append` of `list` has incompatible type `Future[None]`; expected `Coroutine[Any, Any, Any]` `[arg-type]`
- [x] `:368` — Incompatible types in assignment (expression has type `int`, target has type `str`) `[assignment]`
- [x] `:370` — Incompatible types in assignment (expression has type `int`, target has type `str`) `[assignment]`
- [x] `:372` — Incompatible types in assignment (expression has type `int`, target has type `str`) `[assignment]`
- [x] `:374` — Incompatible types in assignment (expression has type `int`, target has type `str`) `[assignment]`

## `src/mqtt/log_bridge.py` — 7 Fehler

- [x] `:63` — Argument 2 to `TimeStamper.__call__` has incompatible type `None`; expected `str` `[arg-type]`
- [x] `:69` — Incompatible default for parameter `result` (default has type `None`, parameter has type `dict[str, Any]`) `[assignment]`
- [x] `:84` — Argument 2 to `TimeStamper.__call__` has incompatible type `None`; expected `str` `[arg-type]`
- [x] `:94` — Incompatible default for parameter `error_details` (default has type `None`, parameter has type `dict[str, Any]`) `[assignment]`
- [x] `:111` — Argument 2 to `TimeStamper.__call__` has incompatible type `None`; expected `str` `[arg-type]`
- [x] `:132` — Argument 2 to `TimeStamper.__call__` has incompatible type `None`; expected `str` `[arg-type]`
- [x] `:195` — List item 3 has incompatible type `_MQTTForwarder`; expected the configured processor callable type `[list-item]`

## `src/core/background_discovery.py` — 7 Fehler

- [x] `:173` — Argument 1 to `wait_for` has incompatible type `Task[Any] | None`; expected `Future[Any] | Awaitable[Any]` `[arg-type]`
- [x] `:176` — Item `None` of `Task[Any] | None` has no attribute `cancel` `[union-attr]`
- [x] `:178` — Incompatible types in `await` (actual type `Task[Any] | None`, expected `Awaitable[Any]`) `[misc]`
- [x] `:219` — Need type annotation for `results` `[var-annotated]`
- [x] `:258` — Incompatible types in assignment (expression has type `object`, variable has type `list[Any]`) `[assignment]`
- [x] `:315` — Argument `wait_time` to `_test_light_mode` has incompatible type `object`; expected `int` `[arg-type]`
- [x] `:522` — Need type annotation for `existing_data` `[var-annotated]`

## `src/mqtt/broker_client.py` — 5 Fehler

- [x] `:31` — Cannot assign to a type `[misc]`
- [x] `:32` — Cannot assign to a type `[misc]`
- [x] `:79` — `Client` has no attribute `connect` `[attr-defined]`
- [x] `:91` — `Client` has no attribute `disconnect` `[attr-defined]`
- [x] `:111` — `Client` has no attribute `disconnect` `[attr-defined]`

## `src/core/discovery_coordinator.py` — 1 Fehler

- [x] `:89` — Argument 1 to `subscribe` of `DiscoveryStateManager` has incompatible type `Callable[[DiscoveryState], Coroutine[Any, Any, Any]]`; expected `Callable[[DiscoveryState], None]` `[arg-type]`

## `src/mqtt/discovery_handler.py` — 2 Fehler

- [x] `:44` — Function `builtins.any` is not valid as a type `[valid-type]`
- [x] `:114` — `any?` has no attribute `publish_sync` `[attr-defined]`

## `src/web/app.py` — 19 Fehler

- [x] `:31` — Incompatible default for parameter `smarttub_client` (default has type `None`, parameter has type `SmartTubClient`) `[assignment]`
- [x] `:32` — Incompatible default for parameter `capability_detector` (default has type `None`, parameter has type `CapabilityDetector`) `[assignment]`
- [x] `:99` — Incompatible return value type (got `StateSnapshot`, expected `dict[str, Any]`) `[return-value]`
- [x] `:159` — Incompatible types in assignment (expression has type `dict[str, Any]`, variable has type `StateSnapshot | None`) `[assignment]`
- [x] `:177` — `AppConfig` has no attribute `config_dir` `[attr-defined]`
- [x] `:187` — Argument 1 to `TemplateResponse` has incompatible type `str`; expected `Request[State]` `[arg-type]`
- [x] `:188` — Argument 2 to `TemplateResponse` has incompatible template/context type `[arg-type]`
- [x] `:201` — Argument 1 to `TemplateResponse` has incompatible type `str`; expected `Request[State]` `[arg-type]`
- [x] `:201` — Argument 2 to `TemplateResponse` has incompatible template/context type `[arg-type]`
- [x] `:699` — Argument 1 to `TemplateResponse` has incompatible type `str`; expected `Request[State]` `[arg-type]`
- [x] `:699` — Argument 2 to `TemplateResponse` has incompatible template/context type `[arg-type]`
- [x] `:703` — Argument 1 to `TemplateResponse` has incompatible type `str`; expected `Request[State]` `[arg-type]`
- [x] `:703` — Argument 2 to `TemplateResponse` has incompatible template/context type `[arg-type]`
- [x] `:721` — Argument 1 to `TemplateResponse` has incompatible type `str`; expected `Request[State]` `[arg-type]`
- [x] `:722` — Argument 2 to `TemplateResponse` has incompatible template/context type `[arg-type]`
- [x] `:730` — Argument 1 to `TemplateResponse` has incompatible type `str`; expected `Request[State]` `[arg-type]`
- [x] `:730` — Argument 2 to `TemplateResponse` has incompatible template/context type `[arg-type]`
- [x] `:738` — Incompatible default for parameter `smarttub_client` (default has type `None`, parameter has type `SmartTubClient`) `[assignment]`
- [x] `:739` — Incompatible default for parameter `capability_detector` (default has type `None`, parameter has type `CapabilityDetector`) `[assignment]`

## `src/cli/run.py` — 2 Fehler

- [x] `:78` — Incompatible default for parameter `broker` (default has type `None`, parameter has type `MQTTBrokerClient`) `[assignment]`
- [x] `:79` — Incompatible default for parameter `error_tracker` (default has type `None`, parameter has type `ErrorTracker`) `[assignment]`

## `src/docker/entrypoint.py` — 4 Fehler

- [x] `:84` — Unpacked dict entry 0 has incompatible type `dict[str, str | None]`; expected `SupportsKeysAndGetItem[str, str]` `[dict-item]`
- [x] `:85` — Dict entry 1 has incompatible type `str: str | None`; expected `str: str` `[dict-item]`
- [x] `:86` — Dict entry 2 has incompatible type `str: str | None`; expected `str: str` `[dict-item]`
- [x] `:87` — Dict entry 3 has incompatible type `str: str | None`; expected `str: str` `[dict-item]`

## Abschlusskriterium

- [x] Alle 90 Fehler behoben oder bewusst mit einer begründeten Ausnahme behandelt.
- [x] `mypy src/ --ignore-missing-imports --show-error-codes` ist fehlerfrei.
- [x] Ruff, Tests und Docker-Build bleiben erfolgreich.
