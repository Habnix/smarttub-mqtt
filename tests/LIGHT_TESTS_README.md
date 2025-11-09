# SmartTub Light Mode Discovery Tests

Systematisches Testen der Light-Modi um herauszufinden welche Modi wirklich funktionieren.

## 🎯 Ziel

- ✅ Herausfinden welche Modi tatsächlich funktionieren
- ✅ Optimale Timing-Parameter ermitteln (Wait-Time, Delays)
- ✅ Status-Update-Verzögerungen messen
- ✅ Fehlgeschlagene Modus-Wechsel identifizieren
- ✅ Unterschiede zwischen Zonen dokumentieren

## 🚀 Quick Start

### Einfachster Weg (Empfohlen):

```bash
cd /var/python/smarttub-mqtt
./tests/run_light_test.sh
```

Das interaktive Script führt Sie durch die Optionen:
- Quick Test (8 Modi, ~45s) - **EMPFOHLEN für ersten Test**
- Color Modes Only (9 Modi)
- Dynamic Modes Only (7 Modi)
- Full Test (18 Modi, ~2 Minuten)
- Custom modes
- Zone 2 Test

### Direkter Aufruf:

```bash
# Quick Test Zone 1
python3 tests/test_light_modes.py --quick --zone 1

# Full Test Zone 1
python3 tests/test_light_modes.py --full --zone 1

# Nur bestimmte Modi testen
python3 tests/test_light_modes.py --modes PURPLE,ORANGE,RED,BLUE --zone 1

# Zone 2 testen
python3 tests/test_light_modes.py --quick --zone 2

# Timing anpassen (5s wait, 3s delay)
python3 tests/test_light_modes.py --quick --wait 5.0 --delay 3.0
```

## 📋 Test-Modi Gruppen

### Quick Test (Standard)
8 representative Modi: OFF, ON, PURPLE, ORANGE, RED, BLUE, WHITE, PARTY

**Dauer:** ~45 Sekunden  
**Empfohlen für:** Ersten Test, schnelle Validierung

### Color Modes
9 Farb-Modi: PURPLE, ORANGE, RED, YELLOW, GREEN, AQUA, BLUE, WHITE, AMBER

**Dauer:** ~60 Sekunden  
**Empfohlen für:** Farbgenauigkeit testen

### Dynamic Modes
7 dynamische Modi: HIGH_SPEED_COLOR_WHEEL, HIGH_SPEED_WHEEL, LOW_SPEED_WHEEL, FULL_DYNAMIC_RGB, AUTO_TIMER_EXTERIOR, PARTY, COLOR_WHEEL

**Dauer:** ~70 Sekunden (mit automatisch verlängerten Wartezeiten)  
**Empfohlen für:** Animations-Modi testen  
**Hinweis:** Diese Modi benötigen längere Wartezeiten und werden automatisch mit 4-5s getestet

### Full Test
Alle 18 Modi

**Dauer:** ~2-3 Minuten (mit optimierten Wartezeiten)  
**Empfohlen für:** Vollständige Dokumentation

### Optimized Full Test (D1 Chairman)
Alle 18 Modi mit optimierten Parametern für zuverlässige Erkennung:

```bash
# Empfohlene Einstellungen für D1 Chairman (100946961)
python3 tests/test_light_modes.py --full --wait 4.0 --verify 5 --delay 2.5 --zone 1
python3 tests/test_light_modes.py --full --wait 4.0 --verify 5 --delay 2.5 --zone 2
```

**Parameter-Erklärung:**
- `--wait 4.0`: 4 Sekunden für Status-Update (dynamische Modi bekommen automatisch 5s)
- `--verify 5`: 5-fache Überprüfung des finalen Status (Majority Vote)
- `--delay 2.5`: 2.5 Sekunden Pause zwischen Tests
- **Dauer:** ~3-4 Minuten pro Zone

## 📊 Output

### Console Output (während Test):

```
🧪 Testing Mode: PURPLE
📊 State before:
   Mode: OFF, Intensity: 0, Color: #aaaaaa
⚙️  Setting mode to: PURPLE
✅ Command sent (0.23s)
⏳ Waiting 3.0s for state update...
📊 State after:
   Mode: PURPLE, Intensity: 50, Color: #ff00ff
✅ SUCCESS: Mode confirmed as 'PURPLE'
🎨 Color changed: #aaaaaa → #ff00ff
⏱️  Total duration: 3.45s
```

### Summary am Ende:

```
📊 TEST SUMMARY
======================================================================

✅ Successful: 7/8 (87.5%)
❌ Failed: 1/8 (12.5%)

✅ Working Modes:
   • OFF                            (3.21s, Color: #000000)
   • PURPLE                         (3.45s, Color: #ff00ff)
   • ORANGE                         (3.38s, Color: #ffa500)
   ...

❌ Failed Modes:
   • HIGH_SPEED_WHEEL               (Got: PARTY, Error: Mode not confirmed)

⏱️  Timing Analysis:
   Average: 3.35s
   Min: 3.21s
   Max: 3.67s
   Recommended wait time: 4.17s
```

### JSON Output:

Datei: `tests/light_mode_test_zone1_20251103_143022.json`

```json
{
  "device_id": "100946961",
  "zone": 1,
  "timestamp": "2025-11-03T14:30:22.123456",
  "total_tests": 8,
  "successful": 7,
  "results": [
    {
      "mode": "PURPLE",
      "success": true,
      "state_before": {
        "mode": "OFF",
        "intensity": 0,
        "color": "#aaaaaa"
      },
      "state_after": {
        "mode": "PURPLE",
        "intensity": 50,
        "color": "#ff00ff"
      },
      "mode_changed": true,
      "color_changed": true,
      "intensity_changed": true,
      "command_duration": 0.23,
      "total_duration": 3.45,
      "wait_time": 3.0,
      "timestamp": "2025-11-03T14:30:25.567890"
    },
    ...
  ]
}
```

## 🔧 Optionen

```
--email EMAIL           SmartTub account email (oder SMARTTUB_EMAIL env)
--password PASSWORD     SmartTub password (oder SMARTTUB_PASSWORD env)
--device-id ID          Device ID (oder SMARTTUB_DEVICE_ID env)
--zone ZONE             Light zone to test (default: 1)

Test Modi:
--quick                 Quick test (8 modi)
--full                  Full test (18 modi)
--colors                Nur Farb-Modi
--dynamic               Nur dynamische Modi
--modes MODES           Custom comma-separated list (z.B. PURPLE,ORANGE,RED)

Timing:
--wait SECONDS          Wait time nach mode change (default: 3.0)
                        Hinweis: Dynamische Modi verwenden automatisch längere Zeiten
--delay SECONDS         Delay zwischen tests (default: 2.0)
--verify NUMBER         Anzahl der State-Verifikationen (default: 3)
                        Höhere Werte = zuverlässigere Erkennung

Output:
--output FILENAME       Custom JSON output filename
```

## 💡 Tipps & Best Practices

### 1. Erste Tests

Starten Sie mit einem **Quick Test**:
```bash
./tests/run_light_test.sh
# Wähle Option 1
```

### 2. Timing optimieren

Wenn Modi nicht richtig erkannt werden:
- **Erhöhen Sie --wait**: Mehr Zeit für Status-Update
- **Erhöhen Sie --verify**: Mehrfache Überprüfung (3-5 Versuche)
- **Erhöhen Sie --delay**: Mehr Zeit zwischen Tests

```bash
# Langsame Modi mit extra Wartezeit und Verifikation
python3 tests/test_light_modes.py --quick --wait 5.0 --verify 5 --delay 3.0
```

**Hinweis:** Dynamische Modi (LOW_SPEED_WHEEL, HIGH_SPEED_WHEEL, etc.) verwenden 
automatisch längere Wartezeiten (4-5s statt 3s).

### 3. Problematische Modi einzeln testen

Wenn ein Modus fehlschlägt (z.B. LOW_SPEED_WHEEL):
```bash
# Extra lange Wartezeit + mehrfache Verifikation
python3 tests/test_light_modes.py --modes LOW_SPEED_WHEEL --wait 7.0 --verify 5
```

### 4. Beide Zonen vergleichen

```bash
# Zone 1
python3 tests/test_light_modes.py --quick --zone 1 --output zone1_test.json

# Zone 2
python3 tests/test_light_modes.py --quick --zone 2 --output zone2_test.json

# Ergebnisse vergleichen
diff zone1_test.json zone2_test.json
```

### 5. Nur fehlgeschlagene Modi nachtesten

Nach einem Full-Test die Failed-Modi nochmal mit längeren Wartezeiten:
```bash
python3 tests/test_light_modes.py --modes MODE1,MODE2,MODE3 --wait 7.0
```

## 🎨 Was Sie testen sollten

### Empfohlene Test-Sequenz:

1. **Quick Test Zone 1** - Baseline etablieren
2. **Quick Test Zone 2** - Unterschiede zwischen Zonen
3. **Color Modes** - Alle Farben validieren
4. **Dynamic Modes** - Animationen testen
5. **Full Test** (optional) - Vollständige Dokumentation

## 📈 Ergebnisse verwenden

### 1. OpenHAB Transformation Map aktualisieren

Basierend auf erfolgreichen Modi in `openhab/transform/smarttub_lightmode.map`:

```bash
# Nur funktionierende Modi behalten
# Fehlgeschlagene Modi auskommentieren oder entfernen
```

### 2. Discovery-Code optimieren

Timing-Parameter in `src/discovery/light_discovery.py` anpassen basierend auf:
- Recommended wait time aus Summary
- Durchschnittliche Dauer erfolgreicher Tests

### 3. Dokumentation aktualisieren

README.md und Konfigurationsbeispiele mit validierten Modi.

## 🐛 Troubleshooting

### "Mode not confirmed" Fehler

**Ursache:** Status-Update dauert länger als wait time

**Lösung:** 
```bash
python3 tests/test_light_modes.py --modes PROBLEMATIC_MODE --wait 7.0
```

### Immer gleiche Farbe trotz verschiedener Modi

**Ursache:** Manche Modi setzen nur intensity/behavior, nicht Farbe

**Das ist normal:** OFF/ON und manche dynamic modes ändern keine Farbe

### "Light zone X not found"

**Ursache:** Zone existiert nicht oder ist nicht verfügbar

**Lösung:** Prüfen Sie verfügbare Zonen:
```python
python3 -c "from src.smarttub import Account; import asyncio; account = Account('email', 'pwd'); spa = asyncio.run(account.get_spa('ID')); lights = asyncio.run(spa.get_lights()); print([l.zone for l in lights])"
```

### Test hängt / sehr langsam

**Ursache:** Netzwerk-Timeout oder API-Rate-Limit

**Lösung:** Erhöhen Sie --delay:
```bash
python3 tests/test_light_modes.py --quick --delay 5.0
```

## 🔬 Erweiterte Nutzung

### Test automatisieren (cron)

```bash
# tests/cron_light_test.sh
#!/bin/bash
cd /var/python/smarttub-mqtt
python3 tests/test_light_modes.py --quick --zone 1 --output /tmp/daily_test_$(date +%Y%m%d).json
```

### Mehrere Zonen parallel testen

```bash
# Nicht empfohlen - kann zu API conflicts führen
# Besser nacheinander
```

### Ergebnisse visualisieren

```python
import json
import matplotlib.pyplot as plt

with open('light_mode_test_zone1_*.json') as f:
    data = json.load(f)
    
durations = [r['total_duration'] for r in data['results'] if r['success']]
modes = [r['mode'] for r in data['results'] if r['success']]

plt.bar(modes, durations)
plt.xticks(rotation=45)
plt.ylabel('Duration (seconds)')
plt.title('Light Mode Test Durations')
plt.tight_layout()
plt.savefig('test_results.png')
```

## 📝 Nächste Schritte nach Tests

1. ✅ Analysieren Sie die Summary
2. ✅ Identifizieren Sie funktionierende Modi
3. ✅ Aktualisieren Sie `smarttub_lightmode.map`
4. ✅ Passen Sie Discovery-Timing an
5. ✅ Dokumentieren Sie Ergebnisse im README
6. ✅ Testen Sie in OpenHAB

## 🤝 Beitragen

Wenn Sie Tests durchführen, teilen Sie gerne Ihre Ergebnisse:
- Welche Modi funktionieren bei Ihrem Modell?
- Welche Timing-Parameter sind optimal?
- Unterschiede zwischen Zonen?

Fügen Sie Ihre JSON-Ergebnisse zu `tests/results/` hinzu!
