"""Version information for smarttub-mqtt and dependencies."""

import importlib.metadata

__version__ = "0.4.0"


def get_smarttub_mqtt_version() -> str:
    """Return smarttub-mqtt version."""
    try:
        return importlib.metadata.version("smarttub-mqtt")
    except importlib.metadata.PackageNotFoundError:
        # Source checkouts and build isolation do not always have metadata.
        return __version__


def get_python_smarttub_version() -> str:
    """Get the version of python-smarttub."""
    try:
        return importlib.metadata.version("python-smarttub")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def get_version_info() -> dict[str, str]:
    """Get version information for all components."""
    return {
        "smarttub_mqtt": get_smarttub_mqtt_version(),
        "python_smarttub": get_python_smarttub_version(),
    }
