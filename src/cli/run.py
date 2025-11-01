from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import structlog

try:
    import uvicorn
    HAS_UVICORN = True
except ImportError:
    HAS_UVICORN = False
    uvicorn = None  # type: ignore

from src.core import config_loader
from src.core.smarttub_client import SmartTubClient
from src.core.state_manager import StateManager
from src.core.capability_detector import CapabilityDetector
from src.core.item_prober import ItemProber
from src.core.error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity  # T058
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


logger = structlog.get_logger(__name__)

_DEFAULT_SIGNALS: tuple[signal.Signals, ...] = tuple(
    getattr(signal, name)
    for name in ("SIGINT", "SIGTERM")
    if hasattr(signal, name)
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
    return parser.parse_args(argv)


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


async def _polling_loop(
    state_manager: StateManager, 
    interval_seconds: int, 
    shutdown_event: asyncio.Event,
    broker: MQTTBrokerClient = None,
    error_tracker: ErrorTracker = None
) -> None:
    """Periodically poll SmartTub state and publish to MQTT."""
    logger.info("starting-smarttub-polling", interval_seconds=interval_seconds)
    
    iteration_count = 0
    
    while not shutdown_event.is_set():
        try:
            await state_manager.sync_state()
            iteration_count += 1
            
            # Publish error meta-topic every 10 iterations (T058)
            if error_tracker and broker and iteration_count % 10 == 0:
                try:
                    broker.publish_meta_errors()
                except Exception as e:
                    logger.debug(f"Failed to publish error meta-topic: {e}")
                    
        except Exception as e:
            logger.error("polling-error", error=str(e))
            # Track state sync error (T058)
            if error_tracker:
                error_tracker.track_error(
                    category=ErrorCategory.STATE_SYNC,
                    message=f"State sync failed: {str(e)}",
                    severity=ErrorSeverity.ERROR,
                    error_code="STATE_SYNC_FAILED"
                )
        
        # Wait for next polling interval or shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            # Timeout means continue polling
            continue
        
        # If we get here, shutdown was requested
        break
    
    logger.info("stopped-smarttub-polling")


async def _capability_refresh_loop(capability_detector: CapabilityDetector, interval_seconds: int, shutdown_event: asyncio.Event) -> None:
    """Periodically refresh SmartTub capabilities."""
    logger.info("starting-capability-refresh", interval_seconds=interval_seconds)
    
    while not shutdown_event.is_set():
        try:
            await capability_detector.refresh_all_capabilities()
        except Exception as e:
            logger.error("capability-refresh-error", error=str(e))
        
        # Wait for next refresh interval or shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
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
            logger.debug("signal-handler-unavailable", signal=getattr(sig, "name", str(sig)))
            continue
        installed.append(sig)

    try:
        yield
    finally:
        for sig in installed:
            with contextlib.suppress(Exception):
                loop.remove_signal_handler(sig)


async def _async_main(
    config_path: Optional[Path | str] = None,
    *,
    discover: bool = False,
    show_discovery: bool = False,
    shutdown_event: Optional[asyncio.Event] = None,
    register_signal_handlers: bool = True,
) -> int:
    loop = asyncio.get_running_loop()
    cleanup_stack = contextlib.ExitStack()
    broker: MQTTBrokerClient | None = None
    smarttub_client: SmartTubClient | None = None
    state_manager: StateManager | None = None
    capability_detector: CapabilityDetector | None = None
    polling_task: asyncio.Task | None = None
    capability_refresh_task: asyncio.Task | None = None
    command_queue_task: asyncio.Task | None = None
    web_server_task: asyncio.Task | None = None
    event = shutdown_event or asyncio.Event()

    try:
        config = config_loader.load_config(config_path)
        
        # Initialize Error Tracker (T058)
        error_tracker = ErrorTracker(max_errors=100)
        logger.info("Error tracker initialized")
        
        broker = MQTTBrokerClient(config, logger=structlog.get_logger("smarttub.mqtt.broker"), error_tracker=error_tracker)
        configure_log_bridge(config, broker)
        broker.connect()

        # Publish initial status
        broker.publish(f"{config.mqtt.base_topic}/status", "starting", retain=True)

        # Discovery gating: check CHECK_SMARTTUB flag (skip when running CLI discovery/show modes)
        if not discover and not show_discovery and not getattr(config, "check_smarttub", True):
            broker.publish(f"{config.mqtt.base_topic}/status", "check_smarttub_disabled", retain=True)
            logger.info("CHECK_SMARTTUB is disabled; discovery and API will not run.")
            return 0

        # Initialize SmartTub integration
        smarttub_client = SmartTubClient(config)
        topic_mapper = MQTTTopicMapper(config, broker)
        state_manager = StateManager(smarttub_client, topic_mapper)
        capability_detector = CapabilityDetector(config, smarttub_client, topic_mapper)
        command_manager = CommandManager(config, smarttub_client, broker)

        # Initialize SmartTub client before using it
        await smarttub_client.initialize()

        # Run initial discovery if CHECK_SMARTTUB is enabled (but not in CLI discovery mode)
        if getattr(config, "check_smarttub", True) and not discover and not show_discovery:
            logger.info("Running initial discovery (CHECK_SMARTTUB=true)")
            try:
                from src.core.item_prober import ItemProber
                item_prober = ItemProber(config, smarttub_client, topic_mapper, error_tracker=error_tracker)
                await item_prober.probe_all()
                logger.info("Initial discovery completed successfully")
            except Exception as e:
                logger.error(f"Initial discovery failed: {e}")
                # Track startup discovery error (T058)
                error_tracker.track_error(
                    category=ErrorCategory.DISCOVERY,
                    message=f"Initial discovery failed: {str(e)}",
                    severity=ErrorSeverity.WARNING,
                    error_code="STARTUP_DISCOVERY_FAILED"
                )
                # Continue anyway - don't fail the startup

        # Handle discovery-only mode
        if discover:
            logger.info("Running discovery mode")
            try:
                from src.core.item_prober import ItemProber
                item_prober = ItemProber(config, smarttub_client, topic_mapper, error_tracker=error_tracker)
                discovery_results = await item_prober.probe_all()
                
                logger.info("Discovery completed successfully")
                return 0
            except Exception as e:
                logger.error(f"Discovery failed: {e}")
                error_tracker.track_error(
                    category=ErrorCategory.DISCOVERY,
                    message=f"CLI discovery failed: {str(e)}",
                    severity=ErrorSeverity.ERROR,
                    error_code="CLI_DISCOVERY_FAILED"
                )
                return 1

        # Handle show-discovery mode
        if show_discovery:
            logger.info("Showing discovery results")
            try:
                discovery_file = Path("/config/discovered_items.yaml")
                if discovery_file.exists():
                    content = discovery_file.read_text()
                    print(content)
                else:
                    print("No discovery file found at /config/discovered_items.yaml")
                    return 1
                return 0
            except Exception as e:
                logger.error(f"Failed to show discovery: {e}")
                return 1

        # Publish connected status
        broker.publish(f"{config.mqtt.base_topic}/status", "connected", retain=True)

        # Set event loop for command manager before subscribing
        command_manager.set_event_loop(asyncio.get_event_loop())
        
        # Set state manager for immediate state updates after commands
        command_manager.set_state_manager(state_manager)
        
        command_manager.subscribe_commands()

        # Start Web UI if enabled (T056)
        if config.web.enabled and HAS_WEB and HAS_UVICORN:
            logger.info("Starting Web UI", extra={"host": config.web.host, "port": config.web.port, "auth_enabled": config.web.auth_enabled})
            try:
                # Create FastAPI app with error_tracker (T058)
                app = create_app(config, state_manager, smarttub_client, capability_detector, error_tracker)
                
                # Start uvicorn server in background
                uvicorn_config = uvicorn.Config(
                    app,
                    host=config.web.host,
                    port=config.web.port,
                    log_level="info",
                    access_log=True
                )
                server = uvicorn.Server(uvicorn_config)
                
                async def run_server():
                    await server.serve()
                
                web_server_task = loop.create_task(run_server())
                logger.info("Web UI started successfully", extra={"url": f"http://{config.web.host}:{config.web.port}"})
            except Exception as e:
                logger.error(f"Failed to start Web UI: {e}", exc_info=True)
                error_tracker.track_error(
                    category=ErrorCategory.WEB_UI,
                    message=f"Failed to start Web UI: {str(e)}",
                    severity=ErrorSeverity.ERROR,
                    error_code="WEBUI_START_FAILED"
                )
                web_server_task = None
        elif not config.web.enabled:
            logger.info("Web UI is disabled in configuration")
        elif not HAS_WEB:
            logger.warning("Web UI dependencies not available - install FastAPI and Jinja2")
        elif not HAS_UVICORN:
            logger.warning("uvicorn not available - cannot start Web UI")

    # NOTE: Automatic disabling of CHECK_SMARTTUB is commented out
    # so the program keeps running and can continue to receive MQTT commands.
    # if getattr(config, "check_smarttub", True):
    #     try:
    #         env_file = Path("/config/.env")
    #         if env_file.exists():
    #             content = env_file.read_text()
    #             # Replace CHECK_SMARTTUB=true with CHECK_SMARTTUB=false
    #             updated_content = content.replace("CHECK_SMARTTUB=true", "CHECK_SMARTTUB=false")
    #             if updated_content != content:  # Only write if something changed
    #                 env_file.write_text(updated_content)
    #                 logger.info("CHECK_SMARTTUB was automatically set to false after successful discovery")
    #     except Exception as e:
    #         logger.warning(f"Error while automatically setting CHECK_SMARTTUB: {e}")

        # Register signal handlers if requested
        if register_signal_handlers:
            cleanup_stack.enter_context(
                _signal_handler_context(loop, event, _DEFAULT_SIGNALS)
            )

        # Start polling loop if CHECK_SMARTTUB is enabled
        if getattr(config, "check_smarttub", True):
            polling_task = loop.create_task(
                _polling_loop(
                    state_manager, 
                    config.smarttub.polling_interval_seconds, 
                    event,
                    broker,
                    error_tracker
                )
            )
            logger.info("Started SmartTub polling task")

        # Start capability refresh loop
        capability_refresh_task = loop.create_task(
            _capability_refresh_loop(capability_detector, config.smarttub.polling_interval_seconds * 5, event)
        )
        logger.info("Started capability refresh task")

        # Start command queue processor
        command_queue_task = loop.create_task(
            command_manager.process_command_queue()
        )
        logger.info("Started command queue processor task")

        # Wait for shutdown event
        await event.wait()
        logger.info("Shutdown event received, cleaning up...")

        # Return success
        return 0

    except asyncio.CancelledError:
        event.set()
        raise
    finally:
        event.set()
        
        # Cancel web server
        if web_server_task is not None:
            web_server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await web_server_task
        
        # Cancel polling task
        if polling_task is not None:
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling_task
        
        # Cancel capability refresh task
        if capability_refresh_task is not None:
            capability_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await capability_refresh_task
        
        # Cancel command queue task
        if command_queue_task is not None:
            command_queue_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await command_queue_task
        
        with contextlib.suppress(Exception):
            cleanup_stack.close()
        if broker is not None:
            with contextlib.suppress(Exception):
                broker.disconnect()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        return asyncio.run(_async_main(
            config_path=args.config,
            discover=args.discover,
            show_discovery=args.show_discovery
        ))
    except config_loader.ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 2


__all__ = ["_async_main", "main"]


if __name__ == "__main__":
    sys.exit(main())