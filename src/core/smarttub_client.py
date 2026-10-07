from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.command_models import CommandStatus
from src.core.config_loader import AppConfig
from src.core.smarttub_controller import SmartTubController
from src.core.smarttub_gateway import SmartTubGateway
from src.core.smarttub_state_reader import SmartTubStateReader
from src.core.state_models import StateSnapshot

logger = logging.getLogger("smarttub.api")


class SmartTubClient:
    """Client wrapper for SmartTub API with polling and error handling."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._smarttub_api: Any | None = None
        self._account: Any | None = None
        self._spas: list[Any] = []
        self._last_error: Exception | None = None
        self.gateway = SmartTubGateway()
        self._state_reader = SmartTubStateReader(self)
        self._controller = SmartTubController(self)

    async def initialize(self) -> None:
        """Initialize the SmartTub API connection."""
        try:
            # Import here to avoid import errors if library not installed
            from smarttub import SmartTub  # type: ignore

            self._smarttub_api = SmartTub()
            await self._smarttub_api.login(
                self.config.smarttub.email, self.config.smarttub.password
            )

            self._account = await self._smarttub_api.get_account()
            available_spas = await self._account.get_spas()
            self._select_configured_spa(available_spas)

            logger.info(
                "Connected to SmartTub account with %d available spa(s); using spa %s",
                len(available_spas),
                self.config.smarttub.device_id,
            )
            self._last_error = None

        except Exception as e:
            logger.error(f"Failed to initialize SmartTub client: {e}")
            self._last_error = e
            raise

    def _select_configured_spa(self, available_spas: list[Any]) -> None:
        """Select exactly one spa for this bridge instance.

        MQTT state and command topics are scoped to one device. Selecting the
        device here prevents a command sent to another spa topic from being
        applied to the first spa returned by the upstream API.
        """
        if not available_spas:
            raise RuntimeError("No spas found in the SmartTub account")

        configured_id = self.config.smarttub.device_id
        if configured_id is None:
            selected_spa = available_spas[0]
            self.config.smarttub.device_id = str(selected_spa.id)
            logger.info(
                "Auto-detected SmartTub device ID: %s", self.config.smarttub.device_id
            )
        else:
            selected_spa = next(
                (spa for spa in available_spas if str(spa.id) == str(configured_id)),
                None,
            )
            if selected_spa is None:
                available_ids = ", ".join(str(spa.id) for spa in available_spas)
                raise ValueError(
                    f"Configured SMARTTUB_DEVICE_ID {configured_id!r} was not found "
                    f"(available: {available_ids})"
                )

        self._spas = [selected_spa]

    async def get_state_snapshot(self) -> StateSnapshot:
        """Return the current state through the dedicated state reader."""
        return await self._state_reader.get_state_snapshot()

    def _get_safe_fallback_snapshot(self) -> StateSnapshot:
        """Return an unavailable envelope without invented component values."""
        timestamp = datetime.now(UTC).isoformat()
        return {
            "timestamp": timestamp,
            "quality": {
                "status": "unavailable",
                "observed_at": None,
                "last_success_at": None,
                "checked_at": timestamp,
            },
            "components": {},
        }

    @staticmethod
    def _enum_name(value: Any) -> Any:
        """Return an enum name while keeping primitive API values unchanged."""
        return getattr(value, "name", value)

    @staticmethod
    def _filtration_modes(filtration: Any) -> list[str]:
        """Return the primary filtration modes supported by the installed API."""
        enum_type = getattr(type(filtration), "PrimaryFiltrationMode", None)
        if enum_type is None:
            return ["NORMAL", "NANO_MODE", "ECO_MODE"]
        return [getattr(mode, "name", str(mode)) for mode in enum_type]

    async def reconnect(self) -> bool:
        """Attempt to reconnect to SmartTub API.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            await self.initialize()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def log_spa_debug_info(self) -> None:
        """Log diagnostic information about connected Spa objects.

        This method inspects the Spa objects and logs available attributes and
        callable methods (filtered to likely control methods). It is intended
        to be run only when logging.level is debug to help diagnose available
        APIs on the upstream python-smarttub library / device.
        """
        try:
            if not self._spas:
                logger.debug("log-spa-debug-info: no spas available to inspect")
                return

            import inspect

            for spa in self._spas:
                spa_id = getattr(spa, "id", None)
                try:
                    attrs = [a for a in dir(spa) if not a.startswith("_")]
                    methods = []
                    for a in attrs:
                        try:
                            val = getattr(spa, a)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug(
                                "Could not inspect spa attribute %s: %s", a, exc
                            )
                            continue
                        if callable(val):
                            # try to get signature when possible, but ignore failures
                            sig = None
                            try:
                                sig = str(inspect.signature(val))
                            except Exception:  # noqa: BLE001
                                sig = None
                            methods.append({"name": a, "signature": sig})

                    logger.debug(
                        "spa-debug-info",
                        extra={
                            "spa_id": spa_id,
                            "attributes_count": len(attrs),
                            "methods_sample": methods[:20],
                        },
                    )

                    # Also inspect child components (pumps/lights) if available
                    try:
                        pumps = await spa.get_pumps()
                        if pumps and isinstance(pumps, dict) and "pumps" in pumps:
                            for p in pumps.get("pumps", [])[:10]:
                                try:
                                    # If object, list its callables
                                    if not isinstance(p, dict):
                                        pm = [
                                            x
                                            for x in dir(p)
                                            if not x.startswith("_")
                                            and callable(getattr(p, x, None))
                                        ]
                                        logger.debug(
                                            "spa-pump-debug",
                                            extra={
                                                "spa_id": spa_id,
                                                "pump_id": getattr(p, "id", None),
                                                "pump_methods": pm[:20],
                                            },
                                        )
                                except Exception as exc:  # noqa: BLE001
                                    logger.debug(
                                        "Could not inspect pump methods: %s", exc
                                    )
                                    continue
                    except Exception:  # noqa: BLE001
                        # best-effort only
                        logger.debug(
                            "spa-debug-info: could not inspect pumps for spa",
                            extra={"spa_id": spa_id},
                        )

                except Exception as e:
                    logger.debug(f"spa-debug-inspect-failed: {e}", exc_info=True)

        except Exception as e:
            logger.debug(f"log_spa_debug_info failed: {e}", exc_info=True)

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to SmartTub API."""
        return self._smarttub_api is not None and self._last_error is None

    @property
    def spas(self) -> list[Any]:
        """Get the single spa selected for this bridge instance."""
        return self._spas.copy()

    # Command methods for controlling the spa
    # Control operations stay on the public client facade for compatibility.
    async def set_temperature(self, temperature_c: float) -> CommandStatus:
        return await self._controller.set_temperature(temperature_c)

    async def set_heat_mode(self, mode: str) -> None:
        await self._controller.set_heat_mode(mode)

    async def set_primary_filtration_mode(self, mode: str) -> None:
        await self._controller.set_primary_filtration_mode(mode)

    async def set_pump_state(
        self, enabled: bool, pump_id: str | None = None
    ) -> CommandStatus:
        return await self._controller.set_pump_state(enabled, pump_id=pump_id)

    async def set_light_state(self, enabled: bool, light_id: str | None = None) -> None:
        await self._controller.set_light_state(enabled, light_id=light_id)

    async def set_light_mode(self, mode: str, light_id: str | None = None) -> None:
        await self._controller.set_light_mode(mode, light_id=light_id)

    async def set_light_color(self, color: str, light_id: str | None = None) -> None:
        await self._controller.set_light_color(color, light_id=light_id)

    async def set_light_brightness(
        self, brightness: int, light_id: str | None = None
    ) -> None:
        await self._controller.set_light_brightness(brightness, light_id=light_id)

    # Preserve the old private helper surface for integrations that used it.
    def _parse_rgb_color(self, color: str) -> tuple[int, int, int] | None:
        return self._controller._parse_rgb_color(color)

    def _clamp_rgb(self, value: int) -> int:
        return self._controller._clamp_rgb(value)

    def _get_white_calibration(self, zone: int | None) -> tuple[int, int, int]:
        return self._controller._get_white_calibration(zone)
