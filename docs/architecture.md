# Architektur und Laufzeitablauf

Dieses Dokument ist der kürzeste Weg, um die Codebase als neuer Entwickler zu
verstehen. Der [Entwicklerleitfaden](development-guide.md) beschreibt danach
die konkreten Arbeitsabläufe und Tests.

## Leitplanken

- Eine laufende Instanz steuert genau einen Whirlpool.
- `SmartTubClient` ist die Grenze zur SmartTub-Cloud.
- `StateManager` hält den letzten vollständigen Snapshot und koordiniert die
  Veröffentlichung.
- MQTT-Befehle und Web-Befehle werden über dieselbe serielle Command-Queue
  ausgeführt.
- Discovery ist ein optionaler Nebenpfad und darf den normalen Polling- und
  Bedienpfad nicht blockieren.
- Fehler an externen Grenzen werden protokolliert und möglichst isoliert, damit
  ein einzelner API-, MQTT- oder UI-Fehler den Dienst nicht beendet.

## Komponentenkarte

| Verantwortlichkeit | Einstiegspunkt | Aufgabe |
| --- | --- | --- |
| Prozessstart und Shutdown | [`src/cli/run.py`](../src/cli/run.py) | Konfiguration laden, Dienste verbinden, Tasks starten und beenden |
| Konfiguration | [`src/core/config_sources.py`](../src/core/config_sources.py), [`src/core/config_loader.py`](../src/core/config_loader.py), [`src/core/config_validation.py`](../src/core/config_validation.py) | Quellen zusammenführen, Dataclasses bauen und Werte validieren |
| SmartTub-Fassade | [`src/core/smarttub_client.py`](../src/core/smarttub_client.py) | Anmelden, genau einen Whirlpool auswählen und Lesen/Schreiben anbieten |
| Status lesen | [`src/core/smarttub_state_reader.py`](../src/core/smarttub_state_reader.py) | Cloud-Daten in den stabilen Snapshot übersetzen |
| Status halten | [`src/core/state_manager.py`](../src/core/state_manager.py) | Letzten Snapshot halten, Fallback liefern und Aktualisierungen auslösen |
| MQTT-Veröffentlichung | [`src/mqtt/topic_mapper.py`](../src/mqtt/topic_mapper.py), [`src/core/state_publisher.py`](../src/core/state_publisher.py) | Snapshot in MQTT-Topics und Payloads übersetzen |
| MQTT-Verbindung | [`src/mqtt/broker_client.py`](../src/mqtt/broker_client.py) | Verbinden, abonnieren, veröffentlichen und reconnecten |
| MQTT-Befehle | [`src/mqtt/command_manager.py`](../src/mqtt/command_manager.py), [`src/mqtt/command_router.py`](../src/mqtt/command_router.py), [`src/mqtt/command_handlers.py`](../src/mqtt/command_handlers.py) | MQTT-Topic routen, serialisieren und SmartTub-Aktion ausführen |
| Web-Verdrahtung | [`src/web/app.py`](../src/web/app.py) | FastAPI, Middleware, Templates und Router zusammenbauen |
| Web-Seiten | [`src/web/page_router.py`](../src/web/page_router.py), [`src/web/view_models.py`](../src/web/view_models.py) | HTML-Kontext aufbauen und Seiten rendern |
| Web-Befehle | [`src/web/command_router.py`](../src/web/command_router.py) | HTTP-Requests validieren und in die Command-Queue geben |
| Discovery im Dienst | [`src/core/discovery_runtime.py`](../src/core/discovery_runtime.py), [`src/core/discovery_coordinator.py`](../src/core/discovery_coordinator.py) | Laufende Discovery starten, stoppen und veröffentlichen |
| Discovery einmalig | [`src/core/item_prober.py`](../src/core/item_prober.py) | Komponenten und Lichtmodi untersuchen und YAML schreiben |

Die beiden `CommandRouter` sind absichtlich verschieden: `src/mqtt/command_router.py`
routet MQTT-Topics, `src/web/command_router.py` routet HTTP-Endpunkte.

## Start einer normalen Instanz

Der zentrale Ablauf liegt in [`ApplicationLifecycle.run()`](../src/cli/run.py).

```text
main()
  → ApplicationLifecycle.run()
  → config_loader.load_config()
  → _initialize_runtime()
       → MQTT-Broker verbinden und Status „starting“ veröffentlichen
       → SmartTubClient, TopicMapper, StateManager, CapabilityDetector
         und CommandManager erzeugen
       → SmartTubClient.initialize()
  → globale Metadaten veröffentlichen
  → initiale Capabilities erkennen, wenn CHECK_SMARTTUB aktiv ist
  → DiscoveryRuntime starten, wenn normaler Dienst + CHECK_SMARTTUB aktiv
  → bei --discover: ItemProber ausführen und beenden
  → bei --show-discovery: YAML ausgeben und beenden
  → Status „connected“ veröffentlichen
  → MQTT-Befehlsthemen abonnieren
  → Web-UI starten, wenn WEB_ENABLED aktiv ist
  → Signal-Handler registrieren
  → Background-Tasks starten:
       • SmartTub-Polling
       • Capability-Refresh
       • Command-Queue
  → auf Shutdown-Signal warten
  → Tasks stoppen, Discovery stoppen, Broker trennen
```

`CHECK_SMARTTUB=false` lässt die Verbindung und die Infrastruktur entstehen,
überspringt aber Discovery, Polling und Capability-Refresh. `--discover` und
`--show-discovery` sind Einmalmodi; sie starten keine reguläre Laufzeit nach
dem jeweiligen Ergebnis.

## Statusfluss

```text
SmartTub-Cloud
      │
      ▼
SmartTubClient
      │
      ▼
SmartTubStateReader ── normalisierter StateSnapshot
      │
      ▼
StateManager ── hält letzten Snapshot und liefert Fallback
      │
      ├── StatePublisher → MQTTTopicMapper → MQTT-Broker
      │
      └── WebViewModels → PageRouter → Jinja-Template → Browser
```

Der Browser liest den letzten Snapshot über `/api/state`. Er greift nicht
direkt auf die SmartTub-Cloud zu. Dadurch bleiben Zugangsdaten und Polling im
Server und Web-Tests benötigen keine echte Cloud-Verbindung.

## Befehlsfluss

### Web-Befehl

```text
Browser
  → POST /api/commands/*
  → src/web/command_router.py
  → CommandManager.execute_command()
  → serielle Command-Queue
  → src/mqtt/command_handlers.py
  → SmartTubClient / SmartTubController
  → StateManager: gezieltes State-Update
  → Browser: Erfolg oder Fehler + späterer Status-Refresh
```

### MQTT-Befehl

```text
MQTT-Broker
  → CommandManager._handle_command_message()
  → src/mqtt/command_router.py
  → serielle Command-Queue
  → CommandHandlers
  → SmartTubClient / SmartTubController
  → StateManager: gezieltes State-Update
```

Die Queue ist der gemeinsame Serialisierungspunkt. Neue Befehle gehören daher
in `CommandHandlers` und die passende Mapping-/Validierungsstelle, nicht in
den MQTT-Callback oder direkt in einen Web-Router.

## Discovery-Entscheidung

| Modus | Einstieg | Lebenszyklus | Ergebnis |
| --- | --- | --- | --- |
| Normaler Dienst, `DISCOVERY_MODE=off` | `ApplicationLifecycle` | Keine automatische Probe | Manuelle Web-/MQTT-Aktionen bleiben möglich |
| Normaler Dienst, `startup_*` | `DiscoveryRuntime` | Asynchron neben dem Dienst | Status-API, MQTT-Status und `/config/discovered_items.yaml` |
| `--discover` | `ItemProber` | Einmalig, danach Prozessende | Vollständige Probing-Ergebnisse |
| `--show-discovery` | CLI-Lesepfad | Einmalig, danach Prozessende | YAML-Inhalt auf stdout |

Die gespeicherten Ergebnisse unter `/config/discovered_items.yaml` sind
Laufzeitdaten. Unter `discovery.last_run` werden zusätzlich Modus, Start-/
Endzeit und Summen des letzten Laufs gespeichert. Der
`DiscoveryCoordinator` rekonstruiert daraus beim ersten Status-/Ergebnisabruf
nach einem Neustart den zuletzt abgeschlossenen WebUI-Lauf. Die Datei gehört
nicht in Git und sollte nur bewusst zurückgesetzt werden.

Die Lichtmodus-Erkennung verwendet mit `src/core/light_mode_catalog.py` eine
gemeinsame Quelle für Backend, Einmal-Prober und WebUI. Der Volltest folgt der
installierten `python-smarttub`-Enum; der Schnelltest nutzt daraus eine kleine
repräsentative Teilmenge. Jede aktive Prüfung läuft mit einem begrenzten
Verifikationszeitfenster und versucht danach, den vorherigen Lichtzustand
wiederherzustellen und zu verifizieren.

## Wo ändere ich etwas?

1. **Neuer Statuswert:** StateReader → State-Modell/View-Model → TopicMapper;
   Tests für StateReader und Topic-Mapping ergänzen.
2. **Neuer SmartTub-Befehl:** Controller/Client → `CommandHandlers` → MQTT-
   und Web-Mapping; anschließend Command- und Web-Router-Tests ergänzen.
3. **Neue Web-Darstellung:** `view_models.py` → Template/Static-Dateien;
   zuerst `tests/test_web_routers.py`, bei Interaktion zusätzlich den Browser-
   Smoke-Test ausführen.
4. **Discovery-Verhalten:** Entscheiden, ob es zum laufenden Dienst
   (`DiscoveryRuntime`) oder zum Einmal-Probing (`ItemProber`) gehört.
5. **Konfigurationswert:** Quelle/Priorität in `config_sources.py`, Dataclass in
   `config_loader.py`, fachliche Regel in `config_validation.py` und danach
   `tests/test_config_loading.py` anpassen.

## Minimaler Verifikationslauf

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/ --ignore-missing-imports --show-error-codes
```

Für Änderungen an der Web-Schicht reicht als schneller erster Lauf:

```bash
pytest tests/test_web_routers.py tests/test_web_view_models.py -q
```
