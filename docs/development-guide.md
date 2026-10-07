# Entwicklerleitfaden

Dieser Leitfaden beschreibt die üblichen Einstiege in die Codebase. Eine
Änderung sollte immer mit dem kleinsten passenden Testlauf beginnen und erst
danach gegen echte SmartTub- und MQTT-Dienste laufen.

Für das Gesamtbild von Komponenten und Laufzeitpfaden zuerst die
[Architekturübersicht](architecture.md) lesen.

## 1. Ohne Gerätezugang entwickeln und testen

Für Unit-, API- und Template-Tests sind keine SmartTub-Zugangsdaten und kein
MQTT-Broker nötig:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
./scripts/quality-check.sh
```

Der Browser-Smoke-Test wird lokal übersprungen, solange Playwright/Chromium
nicht installiert sind. CI installiert Chromium und führt ihn in einem
separaten Job aus.

Der Quality-Check legt Ruff-, MyPy-, Pytest- und Coverage-Artefakte außerhalb
des Source-Verzeichnisses an. Nach manuellen Builds oder älteren Läufen kann
`./scripts/clean.sh` bekannte Artefakte entfernen; Konfiguration und Laufzeitdaten
unter `config/` und `logs/` bleiben unangetastet.

Release-relevante Änderungen werden unter `[Unreleased]` im Changelog ergänzt.
Das Pull-Request-Template enthält dafür eine kurze, wiederverwendbare
Release-Notes-Struktur. Der Release-Workflow prüft außerdem, dass der Git-Tag
mit `src/core/version.py` übereinstimmt.

## 2. Anwendung mit Docker starten

Für einen echten Lauf werden SmartTub- und MQTT-Zugangsdaten benötigt:

```bash
cp config/.env.example config/.env
# config/.env mit echten Zugangsdaten bearbeiten
docker compose up -d
docker compose logs -f smarttub-mqtt
```

Der normale Compose-Aufruf verwendet das veröffentlichte Release-Image. Lokale
Quelländerungen werden mit dem separaten Override gebaut und gestartet:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --force-recreate
```

Die Web-Oberfläche läuft anschließend unter <http://localhost:8080>. Logs
liegen im lokalen Verzeichnis `logs/`, Laufzeitdaten und Discovery-Ergebnisse
unter `config/`.

## 3. Web-Oberfläche oder HTTP-API ändern

Die Web-Schicht trennt Verdrahtung, gerenderte Seiten und HTTP-APIs. Für eine
Änderung zuerst den passenden Einstiegspunkt wählen:

| Aufgabe | Einstiegspunkt |
| --- | --- |
| FastAPI-App, Auth, statische Dateien und Router verdrahten | `src/web/app.py` |
| HTML-Seiten routen und Fehler anzeigen | `src/web/page_router.py` |
| Template-Kontext für Übersicht und Steuerung | `src/web/view_models.py` |
| Status, Capabilities und Health | `src/web/state_router.py`, `src/web/capability_router.py` |
| Steuerbefehle aus der Web-UI | `src/web/command_router.py` |
| Light-Mode-Discovery | `src/web/discovery_router.py` |
| Fehlerantworten ohne interne Details | `src/web/errors.py` |
| Darstellung und Browser-Verhalten | `src/web/templates/`, `src/web/static/` |

Die Steuerungsseite ist bewusst eine Single-Spa-Oberfläche: Sie zeigt nur den
Whirlpool dieser Instanz. Pumpen und Lichtzonen werden über ihre jeweilige
Komponenten-ID adressiert und über dieselbe serielle Queue wie MQTT-Befehle
ausgeführt.

Der Web-Befehlspfad lautet:

```text
Browser → /api/commands/* → `src/web/command_router.py` → CommandManager
        → Command-Queue → CommandHandlers → SmartTubClient → State-Update
```

Nach Änderungen an Endpunkten oder Templates den passenden Vertragstest
ausführen:

```bash
pytest tests/test_web_routers.py -q
```

Die Web-API gibt bei internen Fehlern absichtlich keine Exception-Details aus;
die Ursache steht nur im Server-Log.

## 4. Discovery auswählen oder ändern

Es gibt zwei absichtlich getrennte Discovery-Wege. Sie verwenden dieselben
Laufzeitdaten, haben aber unterschiedliche Ziele:

| Bedarf | Auslöser | Zuständiger Code | Ergebnis |
| --- | --- | --- | --- |
| Lichtmodi im laufenden Dienst erkennen | Web-UI oder `DISCOVERY_MODE` | `DiscoveryRuntime` und `DiscoveryCoordinator` | asynchroner Lauf mit Status-API und MQTT-Veröffentlichung |
| Komponenten einmalig vollständig untersuchen | `python -m src.cli.run --discover` | `ItemProber` | Probing, Datei schreiben, Prozess beenden |
| Vorhandene Ergebnisse ansehen | `python -m src.cli.run --show-discovery` | CLI-Lesepfad | Inhalt von `discovered_items.yaml` ausgeben |

Im normalen Dienst startet `ApplicationLifecycle` die `DiscoveryRuntime`, wenn
`CHECK_SMARTTUB=true` ist. `DISCOVERY_MODE` entscheidet dann, ob gespeicherte
Ergebnisse verwendet oder ein Schnell- bzw. Volltest gestartet wird. Der
CLI-Modus `--discover` besitzt seinen Ablauf selbst und startet keine reguläre
Discovery-Runtime.

Die Lichtmodi stammen zentral aus `src/core/light_mode_catalog.py` und damit aus
der installierten `python-smarttub`-Enum. Die WebUI erhält diese Liste über die
Discovery-Status-API; sie wird nicht zusätzlich in HTML oder JavaScript gepflegt.
Ein Testergebnis unterscheidet unter anderem zwischen unterstütztem Modus,
Helligkeitsabweichung, API-Ablehnung und Timeout. Aktive Lichtmodus-Tests
stellen den ursprünglichen Modus, die Helligkeit und – sofern vorhanden – Farbe
und Zyklusgeschwindigkeit anschließend wieder her.

Discovery-Ergebnisse liegen in `/config/discovered_items.yaml`. Neben den
erkannten Modi und Einzelprüfungen enthält `discovery.last_run` den letzten
Lauf mit Modus, Start-/Endzeit und Summen. Beim ersten Abruf der Discovery-
Status-API nach einem Neustart wird dieser Lauf wieder in den Status geladen.
Die Datei ist Laufzeitstatus: nicht versionieren und bei einem neuen Test nur
bewusst zurücksetzen.

## 5. MQTT oder SmartTub ändern

Der normale Laufzeitpfad ist:

```text
SmartTub-Cloud → SmartTubClient/StateReader → StateManager
              → MQTTTopicMapper → MQTT-Broker

MQTT-Befehl → CommandManager → `src/mqtt/command_router.py` → Command-Queue
            → SmartTubClient → State-Update
```

Wichtige Einstiegspunkte:

- `src/core/smarttub_client.py`: Anmeldung und Auswahl genau eines Whirlpools
- `src/core/smarttub_state_reader.py`: State-Snapshot aus der Cloud
- `src/mqtt/topic_mapper.py`: MQTT-Topic- und Payload-Zuordnung
- `src/mqtt/command_manager.py`: serialisierte Befehlsausführung
- `src/core/discovery_coordinator.py`: Discovery-Lebenszyklus

Für eine Änderung zuerst den jeweils betroffenen Test ausführen, zum Beispiel:

```bash
pytest tests/test_command_manager.py -q
pytest tests/test_smarttub_state_reader.py -q
pytest tests/test_feature_topics.py -q
```

Jede Instanz steuert genau einen Whirlpool. Bei mehreren Geräten muss
`SMARTTUB_DEVICE_ID` gesetzt sein; pro Gerät wird eine separate Instanz mit
einem eigenen `MQTT_BASE_TOPIC` betrieben.

## 6. Konfiguration bis zur Laufzeit verfolgen

Die Konfiguration folgt einer festen Kette. Das hilft besonders bei Problemen,
die nur in Docker oder nur lokal auftreten:

```text
YAML-Datei (optional) + Umgebungsvariablen
    → config_sources.py (Quelle und Priorität)
    → config_loader.py (Dataclasses und Überschreibungen)
    → config_validation.py (fachliche Validierung)
    → ApplicationLifecycle (initialisiert die Dienste)
```

Die Umgebungsvariablen gewinnen nach dem Laden einer YAML-Datei. Prüfe bei
unerwarteten Werten daher zuerst, ob Docker Compose oder die Shell eine Variable
setzt. Für Konfigurationsänderungen sind die Tests zu `config_loader` und
`config_validation` in `tests/test_config_loading.py` der passende erste
Testlauf.
