"""Log rotation with ZIP compression for smarttub-mqtt.

This module provides a custom rotating file handler that:
- Rotates logs when they reach a configured size (default 5MB)
- Compresses rotated logs to ZIP format
- Keeps only ONE ZIP per log type (deletes old ZIPs before creating new)
- Manages three separate log files: mqtt.log, webui.log, smarttub.log
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from logging.handlers import RotatingFileHandler as StdRotatingFileHandler


class ZipRotatingFileHandler(StdRotatingFileHandler):
    """Rotating file handler that compresses rotated logs to ZIP and keeps only one ZIP per log type.

    When a log file reaches maxBytes:
    1. Close the current log file
    2. Delete any existing .zip for this log type
    3. Create a new .zip containing the rotated log
    4. Delete the rotated log file
    5. Start fresh log file

    This ensures only ONE .zip exists per log type at any time.
    """

    def __init__(
        self,
        filename: str | Path,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 1,
        encoding: str | None = None,
        delay: bool = False,
        compress: bool = True,
    ) -> None:
        """Initialize the ZIP rotating file handler.

        Args:
            filename: Path to the log file
            mode: File mode (default 'a' for append)
            maxBytes: Maximum file size in bytes before rotation
            backupCount: Not used (we always keep exactly 1 ZIP)
            encoding: Text encoding for log file
            delay: Delay file opening until first emit
            compress: Whether to compress rotated logs (default True)
        """
        # Force backupCount to 1 since we only keep one ZIP
        super().__init__(
            filename, mode, maxBytes, backupCount=1, encoding=encoding, delay=delay
        )
        self.compress = compress
        self._log_path = Path(filename)

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        """Determine if rollover should occur, with protection against bad file descriptors.
        
        Override parent method to add error handling for closed/invalid file descriptors
        that can occur in Docker/multi-threaded environments.
        """
        if self.stream is None:
            # Stream not yet opened
            self.stream = self._open()
        
        if self.maxBytes > 0:
            # Check if file size exceeds limit
            try:
                self.stream.seek(0, 2)  # Go to end of file
                if self.stream.tell() + len(self.format(record)) >= self.maxBytes:
                    return True
            except (OSError, ValueError) as e:
                # Handle bad file descriptor or closed stream
                # Log to stderr to avoid recursion
                import sys
                print(f"WARNING: Log rotation check failed ({e}), forcing rollover", file=sys.stderr)
                # Force rollover to recover from invalid state
                return True
        
        return False
    
    def doRollover(self) -> None:
        """Rotate the log file and compress to ZIP, removing old ZIPs first."""
        # Safely close the stream with error handling
        if self.stream:
            try:
                self.stream.close()
            except (OSError, ValueError):
                # Stream already closed or invalid
                pass
            finally:
                self.stream = None  # type: ignore

        # Get paths
        base_name = self._log_path.stem  # e.g., "mqtt" from "mqtt.log"
        log_dir = self._log_path.parent
        rotated_log = self._log_path.with_suffix(f"{self._log_path.suffix}.1")
        zip_path = log_dir / f"{base_name}.zip"

        # Rename current log to .log.1
        if self._log_path.exists():
            if rotated_log.exists():
                rotated_log.unlink()
            self._log_path.rename(rotated_log)

        # Compress if enabled
        if self.compress and rotated_log.exists():
            # Delete old ZIP if it exists (ensures only ONE ZIP per type)
            if zip_path.exists():
                zip_path.unlink()

            # Create new ZIP
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    # Add the rotated log with original name inside ZIP
                    zf.write(rotated_log, arcname=self._log_path.name)

                # Delete the rotated log file after successful ZIP
                rotated_log.unlink()
            except Exception as e:
                # If ZIP fails, keep the rotated log
                logging.error(f"Failed to compress log {rotated_log}: {e}")

        # Open fresh log file
        if not self.delay:
            self.stream = self._open()


def setup_file_logging(
    log_dir: str | Path,
    log_max_size_mb: int = 5,
    log_max_files: int = 5,
    log_compress: bool = True,
    log_level: int = logging.INFO,
) -> dict[str, ZipRotatingFileHandler]:
    """Set up file logging with rotation and ZIP compression for all log types.

    Creates three separate log files:
    - mqtt.log: MQTT broker and connection logs
    - webui.log: Web UI and REST API logs
    - smarttub.log: SmartTub API and core logic logs

    Args:
        log_dir: Directory for log files
        log_max_size_mb: Maximum size per log file in MB
        log_max_files: Ignored (we always keep 1 ZIP per type)
        log_compress: Whether to compress rotated logs
        log_level: Minimum log level

    Returns:
        Dictionary mapping log type to handler instance
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    max_bytes = log_max_size_mb * 1024 * 1024  # Convert MB to bytes

    handlers: dict[str, ZipRotatingFileHandler] = {}
    log_types = ["mqtt", "webui", "smarttub"]

    for log_type in log_types:
        log_file = log_path / f"{log_type}.log"
        handler = ZipRotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=1,  # Not used, but required by API
            encoding="utf-8",
            compress=log_compress,
        )
        handler.setLevel(log_level)

        # Use simple formatter for file logs
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        handlers[log_type] = handler

    return handlers


__all__ = ["ZipRotatingFileHandler", "setup_file_logging"]
