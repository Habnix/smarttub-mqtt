# SmartTub OpenHAB 5 Integration

Vollständige OpenHAB 5 Integration für SmartTub Spa basierend auf **echten MQTT Topics** vom laufenden System.

## 📋 Übersicht

Diese Integration wurde durch direktes Auslesen der MQTT Topics vom Live-System erstellt und enthält:

- **Device ID**: 100946961
- **Pumpen**: P1 (JET), P2 (JET), CP (CIRCULATION)
- **Lichter**: Zone 1 (INTERIOR), Zone 2 (EXTERIOR)
- **Steuerung**: Heizung, Pumpen, Licht-Modi, Farben, Helligkeit

## 📁 Dateien

```
openhab/
├── smarttub.things          # MQTT Thing-Definition mit allen Channels
├── smarttub.items           # Item-Definitionen
├── smarttub.sitemap         # UI-Konfiguration
└── transform/
    ├── smarttub_heater.map      # Heizung Status (off/on)
    ├── smarttub_pumpstate.map   # Pumpen Status (off/running)
    ├── smarttub_lightstate.map  # Licht Status (on/off)
    └── smarttub_lightmode.map   # Licht Modi (OFF, PURPLE, ORANGE, etc.)
```

## 🚀 Installation

### 1. MQTT Broker in OpenHAB konfigurieren

In OpenHAB UI → Settings → Things → "+" → MQTT Binding → MQTT Broker:

```
Broker Hostname/IP: 192.168.178.164
Port: 1883
Client ID: openhab-smarttub
```

Notiere dir die **Thing ID** (z.B. `mqtt:broker:mosquitto` oder `mqtt:broker:mybroker`)

### 2. Dateien kopieren

```bash
# Things-Datei
sudo cp smarttub.things /etc/openhab/things/

# Items-Datei
sudo cp smarttub.items /etc/openhab/items/

# Sitemap-Datei
sudo cp smarttub.sitemap /etc/openhab/sitemaps/

# Transformation Maps
sudo mkdir -p /etc/openhab/transform/
sudo cp transform/*.map /etc/openhab/transform/
```

### 3. Broker ID ersetzen

**Wichtig**: Ersetze in allen Dateien `<BROKER_ID>` mit deiner tatsächlichen Broker Thing ID:

```bash
# Beispiel: Wenn deine Broker ID "mosquitto" ist:
sudo sed -i 's/<BROKER_ID>/mosquitto/g' /etc/openhab/things/smarttub.things
sudo sed -i 's/<BROKER_ID>/mosquitto/g' /etc/openhab/items/smarttub.items
```

Oder manuell in den Dateien suchen und ersetzen.

### 4. OpenHAB neu starten

```bash
sudo systemctl restart openhab
```

## 📡 MQTT Topics Übersicht

### Heizung

| Topic | Beschreibung | Werte | Write Topic |
|-------|--------------|-------|-------------|
| `smarttub-mqtt/100946961/heater/state` | Heizung Status | `off`, `on` | - |
| `smarttub-mqtt/100946961/heater/temperature` | Aktuelle Temp | Zahl (°C) | - |
| `smarttub-mqtt/100946961/heater/target_temperature` | Ziel Temperatur | Zahl (°C) | `heater/target_temperature_writetopic` |

### Pumpen

**Pump P1 (JET)**:
- State: `smarttub-mqtt/100946961/pumps/P1/state` → Werte: `off`, `running`
- Write: `smarttub-mqtt/100946961/pumps/P1/state_writetopic`

**Pump P2 (JET)**:
- State: `smarttub-mqtt/100946961/pumps/P2/state` → Werte: `off`, `running`
- Write: `smarttub-mqtt/100946961/pumps/P2/state_writetopic`

**Pump CP (CIRCULATION)**:
- State: `smarttub-mqtt/100946961/pumps/CP/state` → Werte: `off`, `running`
- Write: `smarttub-mqtt/100946961/pumps/CP/state_writetopic`

### Lichter

**Zone 1 (INTERIOR)**:
- State: `smarttub-mqtt/100946961/lights/zone_1/state` → `on`, `off`
- Mode: `smarttub-mqtt/100946961/lights/zone_1/mode` → `OFF`, `PURPLE`, `ORANGE`, `RED`, etc.
- Color: `smarttub-mqtt/100946961/lights/zone_1/color` → `#rrggbb`
- Brightness: `smarttub-mqtt/100946961/lights/zone_1/brightness` → `0-100`

**Zone 2 (EXTERIOR)**: Gleiche Topics mit `zone_2`

Alle haben entsprechende `*_writetopic` Topics für Steuerung.

## 💡 Verfügbare Licht-Modi

Aus den Discovery-Daten:
- `OFF` - Aus
- `ON` - An
- `PURPLE` - Lila
- `ORANGE` - Orange
- `RED` - Rot
- `YELLOW` - Gelb
- `GREEN` - Grün
- `AQUA` - Aqua
- `BLUE` - Blau
- `WHITE` - Weiß
- `AMBER` - Bernstein
- `HIGH_SPEED_COLOR_WHEEL` - Schneller Farbwechsel
- `HIGH_SPEED_WHEEL` - Schnelles Rad
- `LOW_SPEED_WHEEL` - Langsames Rad
- `FULL_DYNAMIC_RGB` - Volle RGB Dynamik
- `AUTO_TIMER_EXTERIOR` - Auto Timer Außen
- `PARTY` - Party
- `COLOR_WHEEL` - Farb Rad

## 🎯 Nutzung

### In OpenHAB UI

1. Öffne **Overview** oder erstelle eine neue **Page**
2. Füge **SmartTub** Items hinzu
3. Oder nutze die Sitemap: **Settings → Sitemaps → SmartTub Spa**

### Steuerung

**Temperatur ändern**:
```
SmartTub_TargetTemp = 38
```

**Pumpe schalten** (via MQTT):
```bash
mosquitto_pub -h 192.168.178.164 -t "smarttub-mqtt/100946961/pumps/P1/state_writetopic" -m "on"
```

**Licht Mode ändern**:
```
SmartTub_Light1Mode = "PURPLE"
```

**Licht Farbe**:
```
SmartTub_Light1Color = "120,100,50"  # HSB
```

## 🔧 Troubleshooting

### Items zeigen "NULL" oder "UNDEF"

1. Prüfe MQTT Broker Verbindung:
   ```bash
   mosquitto_sub -h 192.168.178.164 -t 'smarttub-mqtt/#' -v
   ```

2. Prüfe OpenHAB Logs:
   ```bash
   tail -f /var/log/openhab/openhab.log | grep -i mqtt
   ```

3. Stelle sicher dass `<BROKER_ID>` korrekt ersetzt wurde

### Befehle funktionieren nicht

- Prüfe ob smarttub-mqtt Container läuft
- Prüfe ob write topics subscribed sind
- Teste manuell mit `mosquitto_pub`

### Transformation Maps werden nicht geladen

```bash
# Prüfe ob Dateien existieren:
ls -la /etc/openhab/transform/smarttub_*.map

# Prüfe Berechtigungen:
sudo chown openhab:openhab /etc/openhab/transform/smarttub_*.map
```

## 📊 Beispiel Rule

Automatische Heizung bei niedriger Temperatur:

```java
rule "SmartTub Auto Heater"
when
    Item SmartTub_WaterTemp changed
then
    if (SmartTub_WaterTemp.state < 35 && SmartTub_TargetTemp.state < 37) {
        SmartTub_TargetTemp.sendCommand(37)
        logInfo("SmartTub", "Temperature low, increasing target to 37°C")
    }
end
```

## 🔗 Weitere Informationen

- **GitHub**: https://github.com/Habnix/smarttub-mqtt
- **Docker Hub**: https://hub.docker.com/r/willnix/smarttub-mqtt
- **MQTT Broker**: Mosquitto auf 192.168.178.164:1883

## ✅ Validiert

Diese Konfiguration wurde erstellt durch direktes Auslesen der MQTT Topics vom laufenden System (Nov 2025) und entspricht der tatsächlichen Topic-Struktur.
