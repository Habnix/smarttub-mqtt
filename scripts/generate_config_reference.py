"""Generate the reviewed configuration reference from its registry."""

from pathlib import Path

from src.core.config_env import render_env_override_reference
from src.core.config_registry import render_reviewed_configuration_reference

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "configuration-reference.md"


def main() -> None:
    content = (
        render_reviewed_configuration_reference()
        + "\n"
        + render_env_override_reference()
    )
    TARGET.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
