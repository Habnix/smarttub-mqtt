"""Version information for smarttub-mqtt and dependencies."""

import importlib.metadata
from typing import Dict


def get_smarttub_mqtt_version() -> str:
    """Return smarttub-mqtt version."""
    try:
        return importlib.metadata.version("smarttub-mqtt")
    except Exception:
        # Fallback for development/uninstalled package
        return "0.3.2-dev"


def get_python_smarttub_version() -> str:
    """Get the version of python-smarttub."""
    try:
        return importlib.metadata.version("python-smarttub")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def get_version_info() -> Dict[str, str]:
    """Get version information for all components."""
    return {
        "smarttub_mqtt": get_smarttub_mqtt_version(),
        "python_smarttub": get_python_smarttub_version(),
    }
