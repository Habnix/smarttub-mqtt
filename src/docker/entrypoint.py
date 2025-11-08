#!/usr/bin/env python3
"""
Docker entrypoint for SmartTub-MQTT.

Handles:
- Environment variable validation
- Configuration file checks
- Graceful shutdown on SIGTERM/SIGINT
- Health check endpoint startup
- Proper logging initialization
"""

import os
import sys
import signal
import logging
from pathlib import Path
from typing import NoReturn

# Setup basic logging for entrypoint
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("smarttub.core")


class EntrypointError(Exception):
    """Fatal error during container initialization."""
    pass


def validate_environment() -> dict[str, str]:
    """
    Validate required environment variables.
    
    Returns:
        Dictionary of validated environment variables
        
    Raises:
        EntrypointError: If required variables are missing or invalid
    """
    logger.info("Validating environment variables...")
    
    required_vars = {
        "SMARTTUB_EMAIL": os.getenv("SMARTTUB_EMAIL"),
        "MQTT_BROKER_URL": os.getenv("MQTT_BROKER_URL"),
    }
    
    # Check for password OR token
    password = os.getenv("SMARTTUB_PASSWORD")
    token = os.getenv("SMARTTUB_TOKEN")
    
    if not password and not token:
        raise EntrypointError(
            "Either SMARTTUB_PASSWORD or SMARTTUB_TOKEN must be set"
        )
    
    # Check required variables
    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        raise EntrypointError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    
    # Validate paths
    config_path = os.getenv("CONFIG_PATH", "/config/smarttub.yaml")
    log_dir = os.getenv("LOG_DIR", "/logs")  # Changed from /log to /logs to match docker-compose.yml
    
    logger.info(f"  ✓ SMARTTUB_EMAIL: {required_vars['SMARTTUB_EMAIL']}")
    logger.info(f"  ✓ SMARTTUB_PASSWORD/TOKEN: {'***' if password or token else 'NOT SET'}")
    logger.info(f"  ✓ MQTT_BROKER_URL: {required_vars['MQTT_BROKER_URL']}")
    logger.info(f"  ✓ CONFIG_PATH: {config_path}")
    logger.info(f"  ✓ LOG_DIR: {log_dir}")
    
    return {
        **required_vars,
        "SMARTTUB_PASSWORD": password,
        "SMARTTUB_TOKEN": token,
        "CONFIG_PATH": config_path,
        "LOG_DIR": log_dir,
    }


def validate_directories(env: dict[str, str]) -> None:
    """
    Validate and create required directories.
    
    Args:
        env: Environment variables dictionary
        
    Raises:
        EntrypointError: If directories cannot be created or accessed
    """
    logger.info("Validating directories...")
    
    # Check log directory
    log_dir = Path(env["LOG_DIR"])
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        # Test write access
        test_file = log_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.info(f"  ✓ Log directory writable: {log_dir}")
    except Exception as e:
        raise EntrypointError(f"Cannot write to log directory {log_dir}: {e}")
    
    # Check config directory
    config_path = Path(env["CONFIG_PATH"])
    config_dir = config_path.parent
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"  ✓ Config directory exists: {config_dir}")
    except Exception as e:
        raise EntrypointError(f"Cannot create config directory {config_dir}: {e}")
    
    # Check if config file exists (optional - will be created by discovery)
    if config_path.exists():
        logger.info(f"  ✓ Config file found: {config_path}")
    else:
        logger.info(f"  ℹ Config file will be created: {config_path}")
        # Create minimal config file with dummy values (will be overridden by .env)
        try:
            minimal_config = """# Auto-generated minimal config (values overridden by .env)
smarttub:
  email: "will-be-overridden@example.com"
  password: "will-be-overridden"

mqtt:
  broker_url: "localhost:1883"

web:
  host: "0.0.0.0"
  port: 8080

logging:
  level: "info"
"""
            config_path.write_text(minimal_config, encoding="utf-8")
            logger.info(f"  ✓ Created minimal config file: {config_path}")
        except Exception as e:
            logger.warning(f"  ⚠ Could not create config file: {e} (will try to continue)")



def setup_signal_handlers() -> None:
    """Setup graceful shutdown handlers for SIGTERM and SIGINT."""
    
    def shutdown_handler(signum: int, frame) -> NoReturn:
        """Handle shutdown signals gracefully."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        
        # Exit cleanly - main app will handle cleanup
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    logger.info("Signal handlers configured (SIGTERM, SIGINT)")


def check_discovery_mode() -> bool:
    """
    Check if discovery mode is enabled.
    
    Returns:
        True if CHECK_SMARTTUB=true, False otherwise
    """
    check_smarttub = os.getenv("CHECK_SMARTTUB", "false").lower()
    return check_smarttub in ("true", "1", "yes")


def main() -> NoReturn:
    """
    Docker entrypoint main function.
    
    Performs initialization and starts the main application.
    """
    logger.info("=" * 60)
    logger.info("SmartTub-MQTT Container Starting")
    logger.info("=" * 60)
    
    try:
        # Step 1: Validate environment
        env = validate_environment()
        
        # Step 2: Validate directories
        validate_directories(env)
        
        # Step 3: Setup signal handlers
        setup_signal_handlers()
        
        # Step 4: Check discovery mode
        discovery_mode = check_discovery_mode()
        if discovery_mode:
            logger.info("Discovery mode enabled (CHECK_SMARTTUB=true)")
        else:
            logger.info("Normal operation mode (CHECK_SMARTTUB=false)")
        
        logger.info("=" * 60)
        logger.info("Initialization complete, starting main application...")
        logger.info("=" * 60)
        
        # Import and run main application
        # (Import here to avoid circular dependencies and allow early validation)
        from src.cli.run import main as app_main
        
        # Execute main application
        sys.exit(app_main())
        
    except EntrypointError as e:
        logger.error(f"Entrypoint validation failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unexpected error during initialization: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
