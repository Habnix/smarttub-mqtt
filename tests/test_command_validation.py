"""Contract tests for transport-neutral command normalization."""

import pytest

from src.core.command_models import CommandValidationError, UnsupportedCommandError
from src.core.command_validation import CommandValidator


@pytest.mark.parametrize(
    ("path", "http_data", "mqtt_data", "expected"),
    [
        (
            "heater/target_temperature_writetopic",
            {"temperature": 37.5},
            "37.5",
            {"temperature": 37.5},
        ),
        (
            "heater/mode_writetopic",
            {"mode": " auto "},
            "AUTO",
            {"mode": "AUTO"},
        ),
        (
            "pumps/state_writetopic",
            {"state": "ON", "pump_id": " P1 "},
            {"state": "on", "pump_id": "P1"},
            {"state": "on", "pump_id": "P1"},
        ),
        (
            "lights/brightness_writetopic",
            {"brightness": 50, "light_id": "zone_1"},
            {"value": "50", "light_id": "zone_1"},
            {"brightness": 50, "light_id": "zone_1"},
        ),
    ],
)
def test_http_and_mqtt_payloads_produce_the_same_domain_command(
    path, http_data, mqtt_data, expected
):
    validator = CommandValidator()

    assert validator.normalize(path, http_data) == expected
    assert validator.normalize(path, mqtt_data) == expected


def test_observed_temperature_range_is_enforced_without_a_model_default():
    validator = CommandValidator(lambda: {"min": 20.0, "max": 40.0})

    assert validator.normalize(
        "heater/target_temperature_writetopic", {"temperature": 40}
    ) == {"temperature": 40.0}
    with pytest.raises(CommandValidationError, match="at most 40") as exc_info:
        validator.normalize(
            "heater/target_temperature_writetopic", {"temperature": 40.5}
        )
    assert exc_info.value.code == "validation_error"


@pytest.mark.parametrize("value", [True, "nan", "inf", object()])
def test_invalid_temperature_is_rejected_before_dispatch(value):
    with pytest.raises(CommandValidationError):
        CommandValidator().normalize(
            "heater/target_temperature_writetopic", {"temperature": value}
        )


def test_unknown_light_mode_uses_a_stable_domain_error_code():
    with pytest.raises(UnsupportedCommandError) as exc_info:
        CommandValidator().normalize(
            "lights/mode_writetopic",
            {"mode": "not-a-mode", "light_id": "zone_1"},
        )

    assert exc_info.value.code == "unsupported_command"
