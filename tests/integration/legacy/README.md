# Legacy Integration Tests

Diese Tests wurden aus dem Root-Verzeichnis hierher verschoben.

## Status

⚠️ **VERALTET / LEGACY** - Diese Tests sind möglicherweise nicht auf dem neuesten Stand.

**Empfohlen:** Verwende stattdessen `tests/test_light_modes.py` für Light-Tests.

## Dateien

- `test_comprehensive_lights.py` - Umfassender Light-Test (beide Zonen, alle Modi)
  - ✅ Verwendet `spa.request()` API (funktioniert weiterhin)
  - ⚠️ Redundant zu `tests/test_light_modes.py`

- `test_light_sequence.py` - Test für sequentielle vs. simultane Commands
  - ✅ Verwendet `spa.request()` API (funktioniert weiterhin)
  - ℹ️  Nützlich für Timing-Tests

- `test_rgb_commands.py` - RGB Farb- und Brightness-Tests
  - ⚠️ Verwendet alten `SmartTubClient` (könnte veraltet sein)
  - ⚠️ Möglicherweise nicht kompatibel mit aktueller Implementierung

## Migration

Wenn du diese Tests verwenden möchtest:

1. Prüfe ob sie noch mit der aktuellen Codebase funktionieren
2. Aktualisiere Imports falls nötig
3. Erwäge Integration in `tests/test_light_modes.py`

## Moderne Alternative

```bash
# Empfohlen: Verwende den aktuellen Test
cd /var/python/smarttub-mqtt
python3 tests/test_light_modes.py --quick --zone 1
```
