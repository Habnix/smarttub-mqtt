from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

try:
    import uvicorn

    HAS_UVICORN = True
except ImportError:
    HAS_UVICORN = False
    uvicorn = None  # type: ignore

from src.core import config_loader
from src.core.capability_detector import CapabilityDetector
from src.core.discovery_coordinator import DiscoveryCoordinator
from src.core.discovery_repository import DiscoveryRepository
from src.core.discovery_runtime import DiscoveryRuntime
from src.core.error_tracker import ErrorCategory, ErrorSeverity, ErrorTracker  # T058
from src.core.smarttub_client import SmartTubClient
from src.core.state_manager import StateManager
from src.core.version import get_smarttub_mqtt_version
from src.mqtt.broker_client import MQTTBrokerClient
from src.mqtt.command_manager import CommandManager
from src.mqtt.log_bridge import configure_log_bridge
from src.mqtt.topic_mapper import MQTTTopicMapper

try:
    from src.web.app import create_app

    HAS_WEB = True
except ImportError:
    HAS_WEB = False
    create_app = None  # type: ignore


logger = structlog.get_logger("smarttub.core")

_DEFAULT_SIGNALS: tuple[signal.Signals, ...] = tuple(
    getattr(signal, name) for name in ("SIGINT", "SIGTERM") if hasattr(signal, name)
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="smarttub-mqtt",
        description="Bridge SmartTub telemetry and control via MQTT.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Path to the configuration file (defaults to environment or ./config/smarttub.yaml).",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Run discovery/probing once and exit (writes ./config/discovered_items.yaml and publishes discovery result to MQTT).",
    )
    parser.add_argument(
        "--show-discovery",
        action="store_true",
        help="Print the contents of /config/discovered_items.yaml and exit (if present).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_smarttub_mqtt_version()}",
    )
    return parser.parse_args(argv)


async def _polling_loop(
    state_manager: StateManager,
    interval_seconds: int,
    shutdown_event: asyncio.Event,
    broker: MQTTBrokerClient | None = None,
    base_topic: str = "smarttub-mqtt",
    error_tracker: ErrorTracker | None = None,
) -> None:
    """Periodically poll SmartTub state and publish to MQTT."""
    logger.info("starting-smarttub-polling", interval_seconds=interval_seconds)

    iteration_count = 0

    while not shutdown_event.is_set():
        try:
            state_live = await state_manager.sync_state()
            iteration_count += 1
            if broker is not None:
                await _publish_runtime_status(
                    broker,
                    base_topic,
                    "connected" if state_live else "degraded",
                )

            # Meta-topic publishing is now handled automatically by MQTTClient
            # No manual intervention needed (background task publishes every 60s)

        except Exception as e:  # noqa: BLE001
            logger.error("polling-error", error=str(e))
            # Track state sync error (T058)
            if error_tracker:
                error_tracker.track_error(
                    category=ErrorCategory.STATE_SYNC,
                    message=f"State sync failed: {e!s}",
                    severity=ErrorSeverity.ERROR,
                    error_code="STATE_SYNC_FAILED",
                )

        # Wait for next polling interval or shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            # Timeout means continue polling
            continue

        # If we get here, shutdown was requested
        break

    logger.info("stopped-smarttub-polling")


async def _capability_refresh_loop(
    capability_detector: CapabilityDetector,
    interval_seconds: int,
    shutdown_event: asyncio.Event,
) -> None:
    """Periodically refresh SmartTub capabilities."""
    logger.info("starting-capability-refresh", interval_seconds=interval_seconds)

    while not shutdown_event.is_set():
        try:
            await capability_detector.refresh_all_capabilities()
        except Exception as e:  # noqa: BLE001
            logger.error("capability-refresh-error", error=str(e))

        # Wait for next refresh interval or shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            # Timeout means continue refreshing
            continue

        # If we get here, shutdown was requested
        break

    logger.info("stopped-capability-refresh")


@contextlib.contextmanager
def _signal_handler_context(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
    signals_to_handle: Iterable[signal.Signals],
) -> Iterator[None]:
    installed: list[signal.Signals] = []

    def _make_handler(sig: signal.Signals):
        def handler() -> None:
            if not shutdown_event.is_set():
                logger.info("shutdown-signal-received", signal=sig.name)
                shutdown_event.set()

        return handler

    for sig in signals_to_handle:
        try:
            loop.add_signal_handler(sig, _make_handler(sig))
        except (NotImplementedError, RuntimeError, ValueError):
            logger.debug(
                "signal-handler-unavailable", signal=getattr(sig, "name", str(sig))
            )
            continue
        installed.append(sig)

    try:
        yield
    finally:
        for sig in installed:
            with contextlib.suppress(Exception):
                loop.remove_signal_handler(sig)


@dataclass
class _ApplicationRuntime:
    """Initialized services shared by the application lifecycle."""

    config: config_loader.AppConfig
    error_tracker: ErrorTracker
    broker: MQTTBrokerClient
    smarttub_client: SmartTubClient
    topic_mapper: MQTTTopicMapper
    state_manager: StateManager
    capability_detector: CapabilityDetector
    command_manager: CommandManager


@dataclass
class _BackgroundTasks:
    """Named background tasks owned by one application lifecycle."""

    polling: asyncio.Task | None = None
    capability_refresh: asyncio.Task | None = None
    command_queue: asyncio.Task | None = None


async def _initialize_runtime(
    config: config_loader.AppConfig,
) -> _ApplicationRuntime:
    """Create and connect the services required by the application."""
    error_tracker = ErrorTracker(max_errors=100)
    logger.info("Error tracker initialized")

    broker = MQTTBrokerClient(
        config,
        logger=structlog.get_logger("smarttub.mqtt.broker"),
        error_tracker=error_tracker,
    )
    configure_log_bridge(config, broker)
    await broker.connect(allow_degraded=True)
    await _publish_runtime_status(broker, config.mqtt.base_topic, "starting")

    smarttub_client = SmartTubClient(config)
    discovery_repository = DiscoveryRepository()
    try:
        await discovery_repository.read_async()
    except (OSError, TypeError, yaml.YAMLError) as exc:
        logger.warning("Could not preload discovery data: %s", exc)
    topic_mapper = MQTTTopicMapper(config, broker, discovery_repository)
    state_manager = StateManager(smarttub_client, topic_mapper)
    capability_detector = CapabilityDetector(
        config,
        smarttub_client,
        topic_mapper,
        discovery_repository,
    )
    command_manager = CommandManager(
        config, smarttub_client, broker, capability_detector
    )

    try:
        await smarttub_client.initialize()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "smarttub-startup-degraded",
            reason=type(exc).__name__,
        )
    return _ApplicationRuntime(
        config=config,
        error_tracker=error_tracker,
        broker=broker,
        smarttub_client=smarttub_client,
        topic_mapper=topic_mapper,
        state_manager=state_manager,
        capability_detector=capability_detector,
        command_manager=command_manager,
    )


async def _publish_runtime_status(
    broker: MQTTBrokerClient, base_topic: str, status: str
) -> None:
    """Publish now when connected or buffer the retained status for recovery."""
    topic = f"{base_topic}/status"
    if getattr(broker, "is_connected", True):
        await broker.publish(topic, status, retain=True)
    else:
        broker.publish_sync(topic, status, qos=1, retain=True)


def _publish_initial_metadata(runtime: _ApplicationRuntime) -> None:
    """Publish global version metadata without changing startup behavior."""
    try:
        version_meta_messages = runtime.topic_mapper.publish_version_meta()
        runtime.topic_mapper.publish_messages(version_meta_messages)
        logger.info("Published global version metadata")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to publish version metadata: {exc}")


async def _detect_initial_capabilities(runtime: _ApplicationRuntime) -> None:
    """Detect capabilities for all spas, best effort during startup."""
    if not getattr(runtime.config, "check_smarttub", True):
        return

    logger.info("Starting initial capability detection")
    try:
        for spa in runtime.smarttub_client.spas:
            spa_id = str(spa.id)
            await runtime.capability_detector.detect_capabilities(spa_id)
            logger.info(f"Detected capabilities for spa {spa_id}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Initial capability detection failed: {exc}")


async def _cancel_task(task: asyncio.Task | None) -> None:
    """Cancel one background task and wait until it has stopped."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _shutdown_runtime(
    cleanup_stack: contextlib.ExitStack,
    broker: MQTTBrokerClient | None,
    web_server_task: asyncio.Task | None,
    polling_task: asyncio.Task | None,
    capability_refresh_task: asyncio.Task | None,
    command_queue_task: asyncio.Task | None,
    discovery_runtime: DiscoveryRuntime | None,
) -> None:
    """Stop background work and release external resources in one place."""
    for task in (
        web_server_task,
        polling_task,
        capability_refresh_task,
        command_queue_task,
    ):
        await _cancel_task(task)

    if discovery_runtime is not None:
        with contextlib.suppress(Exception):
            await discovery_runtime.stop()

    with contextlib.suppress(Exception):
        cleanup_stack.close()
    if broker is not None:
        with contextlib.suppress(Exception):
            await broker.disconnect()


def _start_web_ui(
    config: config_loader.AppConfig,
    state_manager: StateManager,
    broker: MQTTBrokerClient,
    smarttub_client: SmartTubClient,
    capability_detector: CapabilityDetector,
    error_tracker: ErrorTracker,
    discovery_coordinator: DiscoveryCoordinator | None,
    command_manager: CommandManager,
    loop: asyncio.AbstractEventLoop,
) -> asyncio.Task | None:
    """Create the optional Web UI and return its background server task."""
    web_server_task: asyncio.Task | None = None
    # Start Web UI if enabled (T056)
    if config.web.enabled and HAS_WEB and HAS_UVICORN:
        _warn_if_unprotected_web_binding(config)
        logger.info(
            "Starting Web UI",
            extra={
                "host": config.web.host,
                "port": config.web.port,
                "auth_enabled": config.web.auth_enabled,
            },
        )
        try:
            # Create FastAPI app with error_tracker (T058) and discovery_coordinator
            app = create_app(
                config,
                state_manager,
                smarttub_client,
                capability_detector,
                error_tracker,
                progress_tracker=None,
                discovery_coordinator=discovery_coordinator,
                command_manager=command_manager,
                mqtt_broker=broker,
            )

            # Start uvicorn server in background
            # Configure uvicorn to use our loggers (T066)
            uvicorn_config = uvicorn.Config(
                app,
                host=config.web.host,
                port=config.web.port,
                log_level="info",
                access_log=True,
                log_config=None,  # Disable uvicorn's default logging config
            )
            server = uvicorn.Server(uvicorn_config)

            async def run_server():
                # Configure uvicorn loggers to use our handlers (reuse existing handlers)
                import logging

                # Get existing webui logger's handlers
                webui_logger = logging.getLogger("smarttub.webui")

                # Configure uvicorn loggers to use same handlers as smarttub.webui
                for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
                    uv_logger = logging.getLogger(logger_name)
                    uv_logger.setLevel(logging.INFO)
                    uv_logger.propagate = False
                    uv_logger.handlers.clear()
                    # Copy all handlers from webui_logger
                    for handler in webui_logger.handlers:
                        uv_logger.addHandler(handler)

                await server.serve()

            web_server_task = loop.create_task(run_server())
            logger.info(
                "Web UI started successfully",
                extra={"url": f"http://{config.web.host}:{config.web.port}"},
            )
        except Exception as e:
            logger.exception("Failed to start Web UI")
            error_tracker.track_error(
                category=ErrorCategory.WEB_UI,
                message=f"Failed to start Web UI: {e!s}",
                severity=ErrorSeverity.ERROR,
                error_code="WEBUI_START_FAILED",
            )
            web_server_task = None
    elif not config.web.enabled:
        logger.info("Web UI is disabled in configuration")
    elif not HAS_WEB:
        logger.warning("Web UI dependencies not available - install FastAPI and Jinja2")
    elif not HAS_UVICORN:
        logger.warning("uvicorn not available - cannot start Web UI")
    return web_server_task


def _warn_if_unprotected_web_binding(config: config_loader.AppConfig) -> None:
    """Warn when command routes are exposed beyond loopback without auth."""
    # Detect the supported LAN default and warn when it is unauthenticated.
    broad_bindings = {
        "0.0.0.0",  # nosec B104
        "::",
        "[::]",
        "*",
    }
    if config.web.host in broad_bindings and not config.web.auth_enabled:
        logger.warning(
            "Web UI command endpoints are reachable without authentication; "
            "use only in a trusted home network, never expose this port to the "
            "internet, and use Basic Auth or an authenticated HTTPS/VPN proxy "
            "for less trusted networks",
            extra={
                "event": "web-ui-unprotected-network-binding",
                "host": config.web.host,
                "port": config.web.port,
            },
        )


def _start_background_tasks(
    config: config_loader.AppConfig,
    state_manager: StateManager,
    broker: MQTTBrokerClient,
    error_tracker: ErrorTracker,
    capability_detector: CapabilityDetector,
    command_manager: CommandManager,
    event: asyncio.Event,
    loop: asyncio.AbstractEventLoop,
) -> _BackgroundTasks:
    """Start polling, capability refresh, and command processing tasks."""
    polling_task: asyncio.Task | None = None
    capability_refresh_task: asyncio.Task | None = None
    command_queue_task: asyncio.Task | None = None
    # Start polling loop if CHECK_SMARTTUB is enabled
    if getattr(config, "check_smarttub", True):
        polling_task = loop.create_task(
            _polling_loop(
                state_manager,
                config.smarttub.polling_interval_seconds,
                event,
                broker,
                config.mqtt.base_topic,
                error_tracker,
            )
        )
        logger.info("Started SmartTub polling task")

    # Start capability refresh loop only when SmartTub polling is enabled.
    if getattr(config, "check_smarttub", True):
        capability_refresh_task = loop.create_task(
            _capability_refresh_loop(
                capability_detector,
                config.capability.refresh_interval_seconds,
                event,
            )
        )
        logger.info("Started capability refresh task")
    else:
        logger.info("Skipped capability refresh because CHECK_SMARTTUB is disabled")

    # Start command queue processor
    command_queue_task = loop.create_task(command_manager.process_command_queue())
    logger.info("Started command queue processor task")
    return _BackgroundTasks(
        polling=polling_task,
        capability_refresh=capability_refresh_task,
        command_queue=command_queue_task,
    )


def _should_start_discovery_runtime(
    config: config_loader.AppConfig, *, discover: bool, show_discovery: bool
) -> bool:
    """Return whether the regular application's discovery services should run.

    The explicit CLI discovery modes own their lifecycle. In the normal
    application, ``DiscoveryRuntime`` is the sole authority for startup
    discovery and applies ``DISCOVERY_MODE`` itself.
    """
    return (
        getattr(config, "check_smarttub", True) and not discover and not show_discovery
    )


class ApplicationLifecycle:
    """Own the application's startup, operating modes, and shutdown sequence."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        discover: bool = False,
        show_discovery: bool = False,
        shutdown_event: asyncio.Event | None = None,
        register_signal_handlers: bool = True,
    ) -> None:
        self._config_path = config_path
        self._discover = discover
        self._show_discovery = show_discovery
        self._shutdown_event = shutdown_event or asyncio.Event()
        self._register_signal_handlers = register_signal_handlers
        self._discovery_runtime: DiscoveryRuntime | None = None

    async def run(self) -> int:
        """Run the selected application mode and always release its resources."""
        loop = asyncio.get_running_loop()
        cleanup_stack = contextlib.ExitStack()
        broker: MQTTBrokerClient | None = None
        polling_task: asyncio.Task | None = None
        capability_refresh_task: asyncio.Task | None = None
        command_queue_task: asyncio.Task | None = None
        web_server_task: asyncio.Task | None = None

        try:
            config = config_loader.load_config(self._config_path)
            runtime = await _initialize_runtime(config)
            broker = runtime.broker

            _publish_initial_metadata(runtime)
            await _detect_initial_capabilities(runtime)

            discovery_coordinator = await self._start_discovery_runtime(runtime)

            if self._discover:
                return await self._run_discovery_mode(runtime)
            if self._show_discovery:
                return self._show_discovery_results()

            dependencies_ready = getattr(broker, "is_connected", True) and getattr(
                runtime.smarttub_client, "is_connected", True
            )
            await _publish_runtime_status(
                broker,
                config.mqtt.base_topic,
                "connected" if dependencies_ready else "degraded",
            )
            runtime.command_manager.set_event_loop(asyncio.get_event_loop())
            runtime.command_manager.set_state_manager(runtime.state_manager)
            await runtime.command_manager.subscribe_commands()

            web_server_task = _start_web_ui(
                config,
                runtime.state_manager,
                broker,
                runtime.smarttub_client,
                runtime.capability_detector,
                runtime.error_tracker,
                discovery_coordinator,
                runtime.command_manager,
                loop,
            )

            if self._register_signal_handlers:
                cleanup_stack.enter_context(
                    _signal_handler_context(
                        loop, self._shutdown_event, _DEFAULT_SIGNALS
                    )
                )

            background_tasks = _start_background_tasks(
                config,
                runtime.state_manager,
                broker,
                runtime.error_tracker,
                runtime.capability_detector,
                runtime.command_manager,
                self._shutdown_event,
                loop,
            )
            polling_task = background_tasks.polling
            capability_refresh_task = background_tasks.capability_refresh
            command_queue_task = background_tasks.command_queue

            await self._shutdown_event.wait()
            logger.info("Shutdown event received, cleaning up...")
            return 0

        except asyncio.CancelledError:
            self._shutdown_event.set()
            raise
        finally:
            self._shutdown_event.set()
            await _shutdown_runtime(
                cleanup_stack,
                broker,
                web_server_task,
                polling_task,
                capability_refresh_task,
                command_queue_task,
                self._discovery_runtime,
            )

    async def _start_discovery_runtime(
        self, runtime: _ApplicationRuntime
    ) -> DiscoveryCoordinator | None:
        """Start discovery for the regular application, when it is enabled."""
        if _should_start_discovery_runtime(
            runtime.config,
            discover=self._discover,
            show_discovery=self._show_discovery,
        ):
            self._discovery_runtime = DiscoveryRuntime(
                config=runtime.config,
                smarttub_client=runtime.smarttub_client,
                topic_mapper=runtime.topic_mapper,
                broker=runtime.broker,
                error_tracker=runtime.error_tracker,
                event_loop=asyncio.get_event_loop(),
            )
            await self._discovery_runtime.start()
            return self._discovery_runtime.coordinator

        if not self._discover and not self._show_discovery:
            await _publish_runtime_status(
                runtime.broker,
                runtime.config.mqtt.base_topic,
                "check_smarttub_disabled",
            )
            logger.info(
                "CHECK_SMARTTUB is disabled; discovery and API polling will not run."
            )
        return None

    async def _run_discovery_mode(self, runtime: _ApplicationRuntime) -> int:
        """Probe all available items once and exit with a meaningful status."""
        logger.info("Running discovery mode")
        try:
            from src.core.item_prober import ItemProber

            item_prober = ItemProber(
                runtime.config,
                runtime.smarttub_client,
                runtime.topic_mapper,
                error_tracker=runtime.error_tracker,
            )
            await item_prober.probe_all()
            logger.info("Discovery completed successfully")
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Discovery failed: {exc}")
            runtime.error_tracker.track_error(
                category=ErrorCategory.DISCOVERY,
                message=f"CLI discovery failed: {exc!s}",
                severity=ErrorSeverity.ERROR,
                error_code="CLI_DISCOVERY_FAILED",
            )
            return 1

    def _show_discovery_results(self) -> int:
        """Print saved discovery data and return a shell-compatible status."""
        logger.info("Showing discovery results")
        try:
            discovery_file = Path("/config/discovered_items.yaml")
            if not discovery_file.exists():
                print("No discovery file found at /config/discovered_items.yaml")
                return 1
            print(discovery_file.read_text())
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to show discovery: {exc}")
            return 1


async def _async_main(
    config_path: Path | str | None = None,
    *,
    discover: bool = False,
    show_discovery: bool = False,
    shutdown_event: asyncio.Event | None = None,
    register_signal_handlers: bool = True,
) -> int:
    """Backward-compatible asynchronous entrypoint for the application."""
    return await ApplicationLifecycle(
        config_path,
        discover=discover,
        show_discovery=show_discovery,
        shutdown_event=shutdown_event,
        register_signal_handlers=register_signal_handlers,
    ).run()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        return asyncio.run(
            _async_main(
                config_path=args.config,
                discover=args.discover,
                show_discovery=args.show_discovery,
            )
        )
    except config_loader.ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001
        import traceback

        print(f"Unexpected error: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2


__all__ = ["ApplicationLifecycle", "_async_main", "main"]


if __name__ == "__main__":
    sys.exit(main())
