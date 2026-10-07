"""Regression tests for MQTT command-topic routing."""

from src.mqtt.command_router import CommandRouter


def test_routes_per_pump_command_and_injects_pump_id():
    router = CommandRouter("smarttub-mqtt")

    route = router.resolve(
        "smarttub-mqtt/spa-test/pumps/P1/state_writetopic",
        "on",
        {"pumps/state_writetopic"},
    )

    assert route.spa_id == "spa-test"
    assert route.handler_key == "pumps/state_writetopic"
    assert route.data == {"state": "on", "pump_id": "P1"}


def test_routes_direct_filtration_command_as_json():
    router = CommandRouter("smarttub-mqtt")

    route = router.resolve(
        "smarttub-mqtt/spa-test/filtration/mode_writetopic",
        '{"mode":"ECO_MODE"}',
        {"filtration/mode_writetopic"},
    )

    assert route.spa_id == "spa-test"
    assert route.handler_key == "filtration/mode_writetopic"
    assert route.data == {"mode": "ECO_MODE"}


def test_decodes_mqtt_bytes_for_per_pump_command():
    router = CommandRouter("smarttub-mqtt")

    route = router.resolve(
        "smarttub-mqtt/spa-test/pumps/P1/state_writetopic",
        b"ON",
        {"pumps/state_writetopic"},
    )

    assert route.data == {"state": "on", "pump_id": "P1"}
