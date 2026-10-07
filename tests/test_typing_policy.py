"""Regression tests for the staged MyPy strictness ratchet."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRICT_CORE_MODULES = {
    "src.core.command_models",
    "src.core.command_validation",
    "src.core.config_env",
    "src.core.config_errors",
    "src.core.config_loader",
    "src.core.config_parsing",
    "src.core.config_registry",
    "src.core.config_sources",
    "src.core.discovery_repository",
    "src.core.log_safety",
    "src.core.pump_model",
    "src.core.runtime_health",
    "src.core.smarttub_controller",
    "src.core.smarttub_gateway",
    "src.core.state_manager",
    "src.core.state_models",
    "src.core.state_publisher",
}
STRICT_MQTT_MODULES = {
    "src.mqtt.message",
    "src.mqtt.publisher",
    "src.mqtt.topic_encoders",
}


def test_mypy_policy_checks_untyped_bodies_and_has_strict_core_ratchet():
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    mypy = config["tool"]["mypy"]
    strict = mypy["overrides"][0]

    assert mypy["check_untyped_defs"] is True
    assert mypy["warn_unused_configs"] is True
    assert "ignore_missing_imports" not in mypy
    assert STRICT_CORE_MODULES <= set(strict["module"])
    assert STRICT_MQTT_MODULES <= set(strict["module"])
    assert strict["disallow_untyped_defs"] is True
    assert strict["disallow_incomplete_defs"] is True
    assert strict["disallow_any_generics"] is True
    assert strict["warn_return_any"] is True


def test_ci_uses_the_versioned_mypy_policy_without_weaker_cli_overrides():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    quality_script = (ROOT / "scripts" / "quality-check.sh").read_text(encoding="utf-8")

    assert "./scripts/quality-check.sh" in workflow
    assert (
        '"$python_bin" -m mypy --cache-dir "$quality_artifacts/mypy" src/'
        in quality_script
    )
    assert "--ignore-missing-imports" not in quality_script
    assert "--no-check-untyped-defs" not in quality_script
