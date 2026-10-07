# Intensive Projektanalyse: `smarttub-mqtt`


**Analysestand:** 22.08.2026\
**Analysierter Commit:** `2657910` (`main`)\
**Projektversion:** `0.3.3`\
**Upstream-Basis:** [`mdz/python-smarttub`](https://github.com/mdz/python-smarttub), im Projekt auf Tag `v0.0.48` festgelegt\
**Umfang:** Architektur, Laufzeit, SmartTub-Adapter, MQTT, Web-UI, Discovery, Konfiguration, Tests, Security, Packaging, Docker, CI/CD und Dokumentation

> Dieser Bericht ist ein Arbeitskatalog. Jeder nummerierte Befund beschreibt nicht
> nur das Problem, sondern auch eine konkrete Umsetzung und ein überprüfbares
> Abnahmekriterium.

## 0. Umsetzungsfortschritt

> **Arbeitsstand:** Änderungen liegen im Workspace vor, sind aber noch kein
> veröffentlichter Release. Die Prioritäten P0–P3 bleiben als Gesamt-Roadmap
> bestehen; erledigt bedeutet hier „implementiert und lokal automatisiert
> geprüft“.

### Paket 1 – Befehlszuverlässigkeit: erledigt (22.08.2026)

- [x] Gemeinsames Statusmodell `accepted`, `sent`, `confirmed`, `failed` und
      `unknown` eingeführt.
- [x] Jeder Befehl erhält eine eindeutige `command_id` und einen Verlauf seiner
      Statusübergänge.
- [x] HTTP-Antworten enthalten den beobachtbaren Command-Status und behaupten
      keinen physischen Hardwareerfolg.
- [x] MQTT publiziert jeden Übergang nicht-retained unter
      `<base>/<spa>/commands/result`.
- [x] Verschluckte Pumpen-/Licht-/Cloud-Fehler werden als typisierte Fehler bis
      zum CommandManager bzw. HTTP-Router weitergegeben.
- [x] Erwartete HTTP-Fehler werden differenziert: unbekannte Komponente `404`,
      ungültiger/unsupported Befehl `422`, Cloud-Fehler `503`.
- [x] Ungültige Heizmodi fallen nicht länger still auf `AUTO` zurück.
- [x] MQTT-Helligkeit `0` bleibt erhalten.
- [x] RGB-JSON behält gültige Nullkanäle bei.
- [x] Pumpen- und Lichtbefehle verlangen eine explizite Komponenten-ID; dadurch
      kann kein Request wie `lights/None` entstehen.
- [x] Web-Befehlsverlauf kennt und übersetzt die neuen Statuswerte.
- [x] Neue Regressionstests für Handler, Controller, Queue, HTTP und MQTT-
      Rückmeldung ergänzt.

**Prüfstand nach Implementierung:** 89 Nicht-Browser-Tests bestanden; Ruff
bestanden; MyPy prüft 48 Source-Dateien ohne Fehler. Der finale Gesamtcheck wird
nach Dokumentation erneut ausgeführt und hier bei Abweichungen aktualisiert.

**Bewusst noch offen:** `confirmed` ist als Status definiert, wird aber erst dann
gesetzt, wenn ein kommando-spezifischer API-Read-back den erwarteten Zielzustand
wirklich verifiziert. Der derzeitige erfolgreiche Cloud-Aufruf endet korrekt bei
`sent`. Physische Aktorwirkung wird niemals garantiert.

### Paket 2 – Ehrliche Zustandssemantik: erledigt (22.08.2026)

- [x] Zustandsqualität `live`, `stale` und `unavailable` als Teil des
      Snapshot-Vertrags eingeführt.
- [x] `observed_at`, `last_success_at` und `checked_at` machen Alter und letzten
      Prüfzeitpunkt maschinenlesbar; rohe Cloud-Fehler bleiben ausschließlich
      in den Logs und gelangen nicht in öffentliche Payloads.
- [x] Status-, Pumpen- und Lichtabruf bilden eine atomare Beobachtung. Ein
      Teilfehler verwirft den neuen Abruf, statt fehlende Komponenten als leer
      zu erfinden.
- [x] Nach einem Fehler bleibt der letzte erfolgreiche Snapshot unverändert
      erhalten und wird `stale`; vor dem ersten Erfolg wird `components: {}`
      mit `unavailable` geliefert.
- [x] MQTT publiziert retained `<base>/<spa>/availability` (`online|offline`)
      und `<base>/<spa>/state/quality`, ohne bekannte Komponentenwerte mit
      Fallback-Werten zu überschreiben.
- [x] `/api/state`, Web-ViewModels und Dashboard-JavaScript unterscheiden
      aktuelle, veraltete und noch nie beobachtete Daten. UI-Platzhalter werden
      nur in der Präsentationsschicht erzeugt und nie als Telemetrie publiziert.
- [x] Auch fehlgeschlagene Command-Reconciliation ersetzt den letzten Snapshot
      nicht mehr durch einen synthetischen Aus-Zustand.
- [x] Regressionstests decken Startausfall, Ausfall nach erfolgreichem Poll,
      Komponenten-Teilfehler, MQTT-Quality und Web-API-Vertrag ab.

**Vertragsentscheidung:** `availability=offline` beschreibt die Erreichbarkeit
der SmartTub-Datenquelle beim letzten Check, nicht den MQTT-Prozess selbst. Der
globale Prozessstatus bleibt weiterhin unter `<base>/status` getrennt. Ein
`source_error` wird bewusst nicht öffentlich ausgegeben, weil interne Cloud-
und Authentifizierungsdetails enthalten sein können.

### Paket 3 – Modellneutrale Pumpen und Capabilities: erledigt (22.08.2026)

- [x] Pumpenzustand (`on|off|unknown`), aktuelle Stufe
      (`off|low|high|unknown`), Rolle (`jet|circulation|blower|unknown`) und
      Stufenfähigkeit (`one_speed|two_speed|unknown`) getrennt.
- [x] `LOW` wird als eingeschaltet mit niedriger Stufe abgebildet; unbekannte
      Upstream-Werte bleiben `unknown` und ihre Rohwerte bleiben im Snapshot für
      Diagnose/Kompatibilität erhalten.
- [x] MQTT publiziert `speed_capability` und dynamische `supported_speeds` in
      Pumpen-Metadaten statt einer pauschalen `ONE_SPEED`-Annahme.
- [x] Capability-Erkennung leitet Pumpenprofile aus den tatsächlich
      beobachteten API-Feldern ab. Ein Erkennungsfehler behauptet keine
      vorhandene Heizung, Pumpe oder Beleuchtung mehr.
- [x] Binäre Pumpenbefehle verwenden die öffentliche Upstream-`toggle()`-Methode
      mit Read-back nach jedem Übergang. LOW → HIGH → OFF wird sicher als zwei
      beobachtete Übergänge behandelt.
- [x] Ein verifizierter Pumpenzielzustand endet als `confirmed`; ein nach dem
      Senden nicht möglicher Read-back als `unknown`. Bei unbekanntem
      Ausgangszustand wird aus Sicherheitsgründen nicht geschaltet.
- [x] Contract-Tests decken Ein-/Zweistufen-, Zirkulations- und unbekannte
      Pumpenformen ab. Reale anonymisierte Geräte-Fixtures bleiben als
      Community-Aufgabe sinnvoll, weil im Repository keine Rohantworten
      verschiedener Hardwaremodelle vorliegen.

**Upstream-Befund:** `python-smarttub 0.0.48` stellt `SpaPump.toggle()` bereit,
kennt die Zustände `OFF`, `LOW`, `HIGH`, die Rollen `BLOWER`, `CIRCULATION`,
`JET` und liefert zusätzlich das Feld `speed`. Der offene Upstream-Fall einer
J-285-Zweistufenpumpe bestätigt, dass eine reine On/Off-Annahme nicht genügt.

### Paket 4 – Backpressure, MQTT-Recovery und degradierter Start: erledigt (22.08.2026)

- [x] Command-Queue auf `SAFETY_COMMAND_QUEUE_SIZE` begrenzt und den pollenden
      100-ms-Worker durch blockierendes `await queue.get()` ersetzt.
- [x] Queue-Overflow wird für Web als HTTP 503 plus `Retry-After` und für MQTT
      als `failed`-Transition sichtbar; kein Gerätebefehl wird still verworfen.
- [x] `SAFETY_COMMAND_TIMEOUT_SECONDS` wird tatsächlich durchgesetzt. Beim
      Worker-Shutdown werden laufende/noch wartende Befehle als `unknown`
      abgeschlossen, damit Web-Futures nicht unbegrenzt hängen.
- [x] Publish-Queue auf `MQTT_PUBLISH_QUEUE_SIZE` begrenzt. Retained Werte
      koaleszieren pro Topic, Command-Ergebnisse bleiben in einer begrenzten
      FIFO erhalten und weniger wichtige non-retained Meldungen dürfen nach
      dokumentierter Overflow-Policy entfallen.
- [x] Broker-Pufferstatistiken melden reale Größe, Drops und Koaleszierungen.
- [x] Reconnect stellt Subscriptions wieder her und leert Offline-Puffer;
      Shutdown erhält eine konfigurierbare Drain-Frist.
- [x] Ein initialer Broker- oder SmartTub-Ausfall beendet den Prozess nicht
      mehr. Web/Lifecycle starten `degraded`, Broker-Reconnect und Cloud-Polling
      erholen sich ohne Prozessneustart.
- [x] Ohne beim Start bekannte Geräte-ID wird ein spa-weites MQTT-Wildcard nur
      für Subscriptions verwendet; die bestehende exakte Laufzeitprüfung
      verwirft Befehle, bis genau ein Spa ausgewählt wurde.
- [x] Das konfigurierte `CAPABILITY_REFRESH_INTERVAL` wird statt des festen
      Polling-Multiplikators verwendet.
- [x] Tests simulieren Queue-Overflow, Timeout, Worker-Shutdown, initialen
      Broker-Ausfall, Subscription-Restore, Offline-Koaleszierung und Recovery.

**Grenze:** Die Offline-Puffer sind bewusst nur speicherbasiert. Ein harter
Prozessabbruch kann noch nicht bestätigte MQTT-Meldungen weiterhin verlieren;
durable Persistenz wäre eine eigene Produktentscheidung.

### Paket 5 – Upstream-Gateway und vereinheitlichte Discovery: erledigt (22.08.2026)

- [x] `SmartTubGateway` als einzige Grenze für undokumentierte
      `python-smarttub`-Low-Level-Requests eingeführt; getestet gegen `0.0.48`.
- [x] StateReader, Controller, BackgroundDiscovery und ItemProber besitzen
      außerhalb dieses Gateways keinen direkten `spa.request()`-Aufruf mehr.
- [x] Gateway-Contract-Tests sichern GET-Aufrufe ohne Body, Light-PATCH-Form und
      Timeouts ab.
- [x] `LightDiscoveryEngine` als gemeinsamer hardwareverändernder Kern für
      Background/Web/MQTT und CLI extrahiert. Auswahl, Darstellung und Export
      bleiben bewusst dünne Adapter um denselben Transaktionspfad.
- [x] Beide Discovery-Pfade persistieren den Originalzustand vor der ersten
      Mutation atomar in `/config/discovery_recovery.yaml`; außerhalb eines
      beschreibbaren Container-Mounts wird `./config/discovery_recovery.yaml`
      verwendet.
- [x] Journal-Einträge werden erst nach verifiziertem Restore entfernt; ein
      abgebrochener Lauf wird vor einer neuen Discovery automatisch restauriert
      oder mit einer deutlichen manuellen Recovery-Anforderung blockiert.
- [x] Unvollständig lesbare Lichtzustände werden vor jeder Mutation abgelehnt;
      ein fehlgeschlagener oder nicht verifizierbarer Restore stoppt den Lauf
      und lässt das Journal für Recovery bzw. manuelles Eingreifen bestehen.
- [x] Der CLI-`ItemProber` führt vor jedem Lauf denselben Recovery-Preflight aus
      und verwendet für Modustest, Read-back, Fehlerklassifikation und Restore
      dieselbe Engine wie die Background-Discovery.
- [x] Der alte CLI-Ablauf schaltete alle Zonen bereits vor ihrer jeweiligen
      Zustandsaufnahme aus. Diese unsichere „Isolation“ ist entfernt; jede Zone
      wird einzeln anhand ihrer ID verifiziert und danach restauriert.
- [x] `DiscoveryFileRepository` kapselt kompaktes und diagnostisches YAML,
      schreibt ohne Mutation der Eingangsdaten und besitzt einen getesteten
      Fallback außerhalb des Container-Mounts.
- [x] `DiscoveryMqttPublisher` kapselt Snapshot-, Pumpen-Metadaten-, Status-,
      Fortschritts- und Ergebnis-Topics; jede Meldung bleibt korrekt der
      jeweiligen Spa-ID zugeordnet.
- [x] Inventar-, Progress- und exhaustive Mode-Plan-Logik des CLI-Probers ist in
      kleine, separat prüfbare Methoden zerlegt. `item_prober.py` sank von 1.279
      auf 868 Zeilen; kein Funktionskörper überschreitet 50 Zeilen und Ruff
      meldet für die Discovery-Module keinen C901-Verstoß mehr.
- [ ] Ein echter Prozesskill kann nur mit anonymisierten Geräte-Fixtures bzw.
      kontrolliertem Hardwaretest vollständig als End-to-End-Szenario validiert
      werden.

**Bewusste Grenze dieses Arbeitsstands:** P1-05, P1-06 und die softwareseitige
Safety-Transaktion aus P1-07 sind abgeschlossen. Ein echter harter
Prozessabbruch auf Hardware bleibt eine kontrollierte End-to-End-Abnahme und
wird nicht durch Unit-Tests vorgetäuscht.

**Reale Ein-Geschwindigkeits-Referenz:** Die bereitgestellte lokale Statusseite
wurde ausschließlich lesend geprüft. Sie bestätigt zwei Jetpumpen und eine
Zirkulationspumpe, jeweils als Einfachgeschwindigkeit. Das eignet sich als reale
Referenz für die aktuelle Modellabbildung, ersetzt aber keine anonymisierte rohe
Upstream-Antwort und keine Zweistufenpumpen-Fixture. Zweistufenunterstützung
bleibt deshalb synthetisch per Contract-Test abgesichert und soll später durch
eine freiwillige Community-Fixture ergänzt werden.

### Paket 6 – Liveness und Readiness: erledigt (22.08.2026)

- [x] `/live` prüft ausschließlich, ob Webprozess und Eventloop Anwendungscode
      ausführen können, und bleibt unabhängig von externen Diensten HTTP 200.
- [x] `/ready` bewertet MQTT-Verbindung, SmartTub-Verbindung, Snapshot-Qualität,
      Snapshot-Alter und den tatsächlichen Command-Worker-Lebenszyklus.
- [x] Nicht bereite konfigurierte Abhängigkeiten liefern HTTP 503 mit sicheren,
      maschinenlesbaren Komponentenstatus ohne rohe Exceptions oder Secrets.
- [x] Bei bewusst deaktiviertem `CHECK_SMARTTUB` werden SmartTub und Snapshot als
      `disabled` statt fälschlich als ausgefallen bewertet.
- [x] `/health` bleibt als rückwärtskompatibler Alias für Liveness erhalten.
- [x] Basic Auth lässt ausschließlich die drei informationsarmen Diagnosewege
      ohne Anmeldung passieren; fachliche API- und Steuerungswege bleiben
      geschützt.
- [x] Docker und Compose prüfen `/live`, damit ein temporärer MQTT-/Cloud-Ausfall
      nicht die vorhandene Hintergrund-Recovery durch Restart-Schleifen stört.
      Reverse-Proxies und Orchestratoren können `/ready` für Traffic-Steuerung
      verwenden.
- [x] Tests decken vollständige Bereitschaft, MQTT-/Cloud-/Worker-Ausfall,
      veraltete Snapshots, deaktiviertes SmartTub und Worker-Start/Stop ab.

### Paket 7 – Kritische Testpfade und erstes Coverage-Gate: erledigt (22.08.2026)

- [x] Die Coverage wurde nach den Architekturpaketen neu vermessen: **61,27 %**
      beziehungsweise 3.535 von 5.770 Statements, ohne den optionalen lokalen
      Browser-Smoke-Test.
- [x] Jeder öffentliche Schreibbefehl des `SmartTubController` besitzt nun
      mindestens einen verhaltensbasierten Erfolgs- und Fehlerfall. Dazu gehören
      Temperatur, Heizmodus, Primärfiltration, Pumpen, Lichtzustand, Lichtmodus,
      Lichtfarbe und Helligkeit.
- [x] Die Controller-Coverage stieg von ursprünglich 15 % auf **75 %**. Die
      Tests prüfen neben Weiterleitung auch Fehlerübersetzung, Enum-Auflösung,
      RGB-Payloads, Helligkeitsskalierung und verifizierte Pumpenübergänge.
- [x] `DiscoveryMQTTHandler` ist mit Fakes für Subscription-Lifecycle,
      Statuspublishing, Start/Stop-Steuerung sowie ungültige und nicht
      ausführbare Nachrichten getestet; seine Coverage stieg von 20 % auf
      **88 %**.
- [x] `pyproject.toml` definiert ein projektweites Coverage-Reporting und das
      erste monotone Gate bei **55 %**. GitHub/Gitea-CI führt Pytest jetzt mit
      `pytest-cov` und `--cov-fail-under=55` aus.
- [x] Der vollständige Nicht-Browser-Lauf besteht mit **146 Tests** und mehr als
      sechs Prozentpunkten Reserve über dem Gate. Es wurden ausschließlich
      Fakes/Fixtures verwendet; kein Geräte-, Broker- oder Cloud-Befehl wurde
      ausgelöst.

**Nächste Coverage-Ratschen:** 65 % erst nach Tests für Capability-Erkennung,
Discovery-Koordination und Zustandsmanagement; 75 % erst nach Absicherung der
CLI-/Entrypoint- und Fehlerdiagnosepfade. Schwellen dürfen nur angehoben, nicht
zur Behebung eines CI-Fehlers abgesenkt werden.

### Paket 8 – Gemeinsame Command-Domainregeln: erledigt (22.08.2026)

- [x] `CommandValidator` ist die transportneutrale Grenze für alle acht
      schreibbaren Command-Pfade. HTTP, MQTT-Queue und direkte Handler erzeugen
      daraus dieselben kanonischen Payloads.
- [x] Zustände und Modi werden konsistent normalisiert, Komponenten-IDs
      getrimmt und verpflichtend geprüft; boolesche, nicht endliche oder
      anderweitig ungültige Zahlen werden vor dem Queueing abgelehnt.
- [x] Temperaturgrenzen kommen ausschließlich aus dem beobachteten
      Capability-Cache. Solange keine Grenzen erkannt wurden, erfindet der
      generische Kern keine modell- oder markenspezifischen Defaults.
- [x] Domänenfehler besitzen stabile Codes wie `validation_error`,
      `unsupported_command`, `component_not_found`, `queue_full` und
      `cloud_command_failed`. HTTP liefert den Code im
      `X-Command-Error-Code`-Header; MQTT-Command-Ergebnisse und History führen
      denselben Code.
- [x] Contract-Tests belegen, dass semantisch gleiche HTTP- und MQTT-Payloads
      dasselbe Domain-Command ergeben. Integrationsfälle prüfen identische
      Capability-Grenzen und Fehlercodes vor einem Geräteaufruf.

### Paket 9 – Zweite Coverage-Ratsche und modellneutrale Capabilities: erledigt (22.08.2026)

- [x] Die vollständige Nicht-Browser-Suite umfasst **169 Tests** und erreicht
      **66,11 % Statement-Coverage**. Das monotone CI-Gate wurde von 55 % auf
      **65 %** angehoben.
- [x] `CapabilityDetector` stieg von 28 % auf **89 %** Coverage. Contract-Tests
      prüfen vollständige Erkennung, Serialisierungs-Roundtrip, Cache/Expiry,
      Fehler-Fallback, Refresh, MQTT-Ausgabe und erkannte YAML-Lichtmodi.
- [x] Temperaturgrenzen werden nicht länger aus einem Modellnamen geraten. Nur
      explizit in der Upstream-Antwort beobachtete, valide Min-/Max-Werte werden
      in das Capability-Profil übernommen.
- [x] Unquoted `ON`/`OFF` aus YAML-1.1-Dateien werden robust in ihre fachlichen
      Lichtmodi zurückübersetzt; gemischte Bool-/String-Werte können die
      Capability-Erkennung nicht mehr beim Sortieren abbrechen.
- [x] Ein Capability-Refresh publiziert jedes Profil nur einmal. Zuvor wurde es
      durch `detect_capabilities()` und anschließend erneut durch den
      Refresh-Wrapper doppelt gesendet.
- [x] `DiscoveryCoordinator` stieg von 44 % auf **82 %** Coverage. Start/Stop,
      ungültige Modi, bereits laufende Discovery, Reset, Ergebnisse,
      MQTT-Publishing, Runner-Fehler und Singleton-Shutdown sind getestet.
- [x] Die projektseitige Python-3.16-Warnung ist beseitigt:
      `inspect.iscoroutinefunction` ersetzt die abgekündigte asyncio-Variante.

### Paket 10 – Heimnetz-Härtung und reproduzierbarer Wheel-Build: umgesetzt (22.08.2026)

- [x] Ein unauthentifizierter Web-Start auf `0.0.0.0`, `::`, `[::]` oder `*`
      erzeugt eine deutliche strukturierte Warnung mit dem Hinweis auf
      vertrauenswürdiges Heimnetz, fehlende Internetfreigabe sowie Basic Auth,
      HTTPS-Reverse-Proxy oder VPN.
- [x] README und `.env.example` dokumentieren die vereinbarte Netzwerkgrenze,
      Gast-/IoT-Netze, Portweiterleitung, HTTPS und die anonym erreichbaren,
      informationsarmen Health-Endpunkte.
- [x] `requirements.lock` fixiert den vollständigen Produktionssatz auf exakte
      Versionen. `python-smarttub 0.0.48` ist auf den unveränderlichen Commit
      `7b15cb00c0b84b86f90454b9366c66dd2dba5057` statt nur auf einen Git-Tag
      festgelegt.
- [x] CI installiert den Produktions-Lockstand als Constraints-Basis und testet
      Python 3.13 sowie 3.14. Ein eigener Schritt baut das nicht-editierbare
      Wheel und prüft, dass Templates und JavaScript enthalten sind.
- [x] Der Docker-Builder kopiert den Source vor dem Build, installiert die
      gelockten Abhängigkeiten, baut ein Wheel und übernimmt nur die installierte
      Venv in die Runtime. Der separate `/app/src`-Fallback entfällt.
- [x] Web-Assets werden relativ zu `src.web.app.__file__` gefunden. Ein lokal
      gebautes und nach `/tmp` installiertes Wheel lädt Templates und Static
      Assets erfolgreich außerhalb des Repository-Arbeitsverzeichnisses.
- [ ] Der abschließende echte Container-Build ist lokal nicht ausführbar, weil
      auf dem Arbeitsrechner kein `docker`-Kommando installiert ist. Der
      bestehende CI-Dockerjob ist die vorgesehene Container-Abnahme.

### Paket 11 – Ehrliche Konfigurationsoptionen: erledigt (22.08.2026)

- [x] `WEB_UI_REFRESH_INTERVAL_SECONDS` beziehungsweise
      `web_ui.refresh_interval_seconds` steuert nun den tatsächlichen
      Dashboard-Polling-Takt. Der bisher fest verdrahtete Wert von 30 Sekunden
      ist entfernt; ein Router-Test weist die Laufzeitwirkung bis in das
      ausgelieferte HTML nach.
- [x] Die nie wirksamen Observability-, Safety-Retry- und
      Auto-Discovery-Optionen sind aus den Laufzeit-Dataclasses und aus
      `.env.example` entfernt. Für einen Kompatibilitätszyklus werden alte Env-
      und YAML-Schlüssel noch angenommen, aber mit konkreter Migration als
      `FutureWarning` gemeldet und ausdrücklich ignoriert.
- [x] Insbesondere wird kein automatischer Pumpen-Fail-safe und keine
      Command-Wiederholung vorgetäuscht. Die Bridge sendet ohne expliziten
      Nutzerbefehl keine Hardwarekommandos; Command-Ergebnis und anschließend
      beobachteter Zustand bleiben die ehrliche Rückmeldung.
- [x] `src/core/config_registry.py` hält Env-Name, YAML-Pfad, Default,
      Validator, Status, Beschreibung und Ersatz der geprüften Optionen
      maschinenlesbar. `scripts/generate_config_reference.py` erzeugt daraus
      `docs/configuration-reference.md`; ein Drift-Test vergleicht Registry und
      eingecheckte Referenz.
- [x] Tests stellen sicher, dass `.env.example` aus dieser Prüfmenge nur aktive
      Optionen enthält, alle veralteten Env-Schalter warnen und ungültige alte
      Werte nicht versehentlich wieder validiert oder ausgeführt werden.

### Paket 12 – Deklaratives Env-Schema und Config-Modulgrenzen: erledigt (22.08.2026)

- [x] Die 65-fach verzweigte `_apply_env_overrides()`-Implementierung ist
      entfernt. `config_env.py` beschreibt alle **49** unterstützten oder
      bewusst abgelehnten Env-Eingaben als geordnete `EnvOverride`-Einträge mit
      Zielpfad, YAML-Pfad, Parser sowie Minimum/Maximum.
- [x] Historische Alias-Prioritäten bleiben explizit durch die Reihenfolge des
      Schemas erhalten: `POLL_INTERVAL`, `WEB_AUTH_USERNAME` und
      `CAPABILITY_REFRESH_INTERVAL_SECONDS` gewinnen weiterhin gegenüber ihren
      älteren Alternativen, wenn beide gesetzt sind.
- [x] `ConfigError`, wiederverwendbare Parsing-Primitiven und Datei-/Env-Quellen
      besitzen mit `config_errors.py`, `config_parsing.py`, `config_sources.py`
      und `config_env.py` klare Grenzen. Der öffentliche Import
      `config_loader.ConfigError` bleibt kompatibel.
- [x] `config_loader.py` sank von 857 auf **533 Zeilen** und enthält jetzt im
      Wesentlichen die typisierten Konfigurations-Dataclasses, YAML-Komposition
      und den öffentlichen Ladepfad. Die neue `apply_env_overrides()` umfasst
      nur 11 Zeilen und besteht die C901-Komplexitätsprüfung.
- [x] Ein parametrisierter Vertragstest führt jeden Schemaeintrag aus. Weitere
      Tests prüfen eindeutige Env-Namen, dokumentierte Ziele, Alias-Priorität
      und deklarierte Zahlen-/Boolean-/String-Grenzen.
- [x] Die generierte Konfigurationsreferenz enthält nun zusätzlich sämtliche
      Env-Eingaben mit Ziel, Parser und Grenzen. Registry-/Dokumentationsdrift
      bleibt durch einen Gleichheitstest blockiert.

### Paket 13 – Stufenweise strikte Typprüfung: erledigt (22.08.2026)

- [x] MyPy prüft mit `check_untyped_defs = true` jetzt projektweit auch die
      Funktionskörper historisch noch unvollständig annotierter Funktionen.
      Die bisher pauschale Option `ignore_missing_imports` wurde entfernt;
      notwendige dynamische Upstream-Grenzen sind lokal und sichtbar markiert.
- [x] Für **17** stabile Module aus Config, Command-Domain, Gateway,
      Pumpenmodell, Runtime-Health und HTTP/MQTT-Command-Routing gelten darüber
      hinaus `disallow_untyped_defs`, `disallow_incomplete_defs`,
      `disallow_any_generics` und `warn_return_any`.
- [x] Ein realer Typfehler wurde behoben: Der Discovery-Coordinator deklarierte
      seinen MQTT-Publisher als synchronen `Callable[..., None]`, rief ihn aber
      mit `await` auf. Der Vertrag lautet nun durchgängig
      `Callable[[DiscoveryState], Awaitable[None]]`.
- [x] Command-Handler und die heterogenen, rückwärtskompatiblen Queue-Einträge
      besitzen konkrete Typaliase; die Queue ist parametrisiert. Die
      StateManager-Verknüpfung ist nicht länger untypisiert, und
      `SmartTubController` verwendet ein strukturelles Client-Protokoll statt
      eines impliziten `Any`-Konstruktors.
- [x] `StateSnapshot` verlangt nun mindestens `timestamp` und `components`.
      `quality` bleibt an der internen Reader→StateManager-Grenze bewusst
      optional, wird aber als vollständiger `StateQuality`-Record typisiert,
      sobald vorhanden.
- [x] Policy-Tests verhindern das Entfernen der globalen Body-Prüfung, der
      Strict-Modulliste oder einzelner Strict-Schalter. CI und Pre-Commit nutzen
      ausschließlich die versionierte `pyproject.toml`-Policy statt schwächerer
      Kommandozeilen-Overrides.

### Paket 14 – Lokale Exception-Grenzen statt globaler Ausnahmen: erledigt (22.08.2026)

- [x] Die globalen Ruff-Ausnahmen für `BLE001` und `S110` sind entfernt. Ruff
      prüft breite und stille Exception-Handler nun im normalen Projektlauf.
- [x] Die verbleibenden **64** bewusst breiten Adapter-/Supervisor-Grenzen sind
      zeilenlokal sichtbar. Ein Policy-Test setzt diese Zahl als monotone
      Obergrenze; neue breite Suppressionen können nicht unbemerkt hinzukommen.
- [x] Dotenv-Fallback fängt nur noch `OSError`, die Paketversion nur noch
      `PackageNotFoundError`, und Basic-Auth behandelt ausschließlich ungültiges
      Base64, Unicode und Headerformat. Programmierfehler werden dort nicht mehr
      verschluckt.
- [x] Vier zuvor stille Serializer-/Topic-Mapping-Catches protokollieren ihren
      Fallback jetzt auf Debug-Ebene. Nur die rekursionskritische optionale
      MQTT-Logweiterleitung darf weiterhin bewusst schweigen.
- [x] Regressionstests belegen Dateisystem-Fallback versus propagierten
      Programmierfehler, malformed Basic-Auth sowie die Ruff-Policy und ihre
      sinkende Suppressionsobergrenze. Die Zahl breiter Catches sank gegenüber
      dem Analyseausgang von 167 auf 153.

### Paket 15 – Atomare Discovery-Persistenz ohne Eventloop-I/O: erledigt (22.08.2026)

- [x] `DiscoveryRepository` ist die einzige Pfad-, Lese-, Schreib- und
      Update-Grenze für `discovered_items.yaml` und das Recovery-Journal. Der
      Laufzeitpfad wird genau einmal auf `/config` beziehungsweise das lokale
      `config`-Verzeichnis aufgelöst; Komponenten durchsuchen keine wechselnden
      Kandidaten mehr.
- [x] Alle Schreibvorgänge verwenden ein Tempfile im Zielverzeichnis, `fsync`
      und `os.replace`. Ein gemeinsamer Lock pro aufgelöstem Pfad schützt auch
      mehrere Repository-Instanzen und hält Read-Modify-Write-Updates atomar.
- [x] Jedes neu geschriebene Discovery-Dokument trägt `schema_version: 1`.
      Fehlgeschlagene Ersetzungen lassen die vorherige Datei unverändert und
      räumen temporäre Dateien auf.
- [x] Async-Aufrufer in Background-Discovery, Coordinator, CLI-Prober,
      Recovery, YAML-Fallback, Capability-Erkennung und Web-ViewModels lagern
      Dateisystem-I/O über `asyncio.to_thread()` aus.
- [x] Der synchrone MQTT-Snapshot-Mapper liest keine Datei mehr. Er verwendet
      einen pfadbezogenen, threadsicheren und defensiv kopierten Memory-
      Snapshot, der beim asynchronen Start geladen und bei Repository-
      Schreibvorgängen instanzübergreifend aktualisiert wird.
- [x] Paralleltests mit 20 Schreibern und 40 Lesern prüfen verlorene Updates,
      partielles YAML, atomaren Fehlerfall, Cache-Isolation und den I/O-freien
      Mapper-Pfad. Die Tests verwenden ausschließlich temporäre Dateien und
      lösen keine Hardware-, Cloud- oder Brokeraktion aus.

**Architekturwirkung:** P2-04 ist abgeschlossen. Der TopicMapper enthält kein
Discovery-Dateisystem-I/O mehr; seine Verantwortlichkeiten wurden anschließend
in Paket 16 getrennt.

### Paket 16 – Reine Topic-Encoder und separater MQTT-Versand: erledigt (22.08.2026)

- [x] `StateTopicEncoder` bildet Snapshots und Zustandsqualität ohne Broker oder
      Repository auf `MQTTMessage`-Werte ab. Erkannte Lichtmodi werden als
      injizierte Lookup-Funktion übergeben.
- [x] `MetadataTopicEncoder` und `DiscoveryTopicEncoder` erzeugen Capability-,
      Versions-, Discovery-Status- und Discovery-Ergebnis-Topics ohne
      Transportzugriff.
- [x] `MqttPublisher` ist die einzige neue Versandgrenze und kennt nur den
      minimalen `publish_sync`-Vertrag. Encoder rufen niemals den Broker auf.
- [x] `MQTTMessage` ist ein unveränderliches, typisiertes Value Object. Der
      bestehende Import aus `topic_mapper` und alle öffentlichen Mapper-Methoden
      bleiben kompatibel.
- [x] `MQTTTopicMapper` ist nun eine Fassade, die Encoder, den atomaren
      Discovery-Memory-Snapshot und den Publisher komponiert. Die eigentliche
      State-Abbildung ist als eigenständig instanziierbarer Encoder verfügbar.
- [x] Direkte Contract-Tests prüfen State-, Capability-, Discovery- und
      Lichtmodus-Encoding ohne Dummy-MQTT-Client; ein separater Test weist nach,
      dass nur der Publisher `publish_sync` ausführt.
- [x] Die drei neuen MQTT-Grenzen laufen unter der strikten MyPy-Ratsche. Der
      projektweite Strict-Satz umfasst nun 21 Module.

**Architekturwirkung:** P2-05 ist abgeschlossen. Die kompatible Fassade hält
bestehende Aufrufer stabil, während neue Komponenten direkt die reinen Encoder
verwenden können. Als nächster lokaler Punkt empfiehlt sich P2-06: ungenutzte
beziehungsweise konkurrierende StateManager-Pfade bereinigen und die
Vollsnapshot-/Delta-Strategie explizit festlegen.

### Paket 17 – Eindeutiges StateManager-Publikationsmodell: erledigt (22.08.2026)

- [x] Als einziges Modell ist jetzt `full_snapshot` festgelegt: Jeder
      erfolgreiche Poll erzeugt sämtliche retained Komponenten-Topics und einen
      separaten Quality-/Availability-Heartbeat. Der letzte vollständige
      Snapshot bleibt die einzige Web-/Health-Lesequelle.
- [x] Change-Detection und Teil-Merge sind entfernt. Dadurch kann eine leere,
      aber valide Komponentenliste nicht mehr durch eine zweite, versteckte
      „transient“-Heuristik unterdrückt werden; die atomare StateReader-
      Beobachtung entscheidet allein über Erfolg oder Fehler.
- [x] Der ungenutzte zweite Update-/Validierungspfad, Multi-Spa-Passthrough und
      interne Reconnect-Wrapper sind entfernt. Reconnect bleibt bei den dafür
      zuständigen SmartTub-/Lifecycle-Komponenten.
- [x] Die ungenutzte Pending-Command-Registry ist entfernt. CommandManager hält
      Queue, Statusautomat, History und Correlation-ID als alleinige Command-
      Autorität.
- [x] Die alte Pseudo-Reconciliation ist entfernt. Sie hatte Licht-, Farb- und
      Helligkeitsbefehle allein nach einem fehlerfreien Read als erfolgreich
      behandelt und einen Heizmodus nur auf vorhandenen Input geprüft. Echte
      Read-back-Verifikation bleibt befehlsspezifisch im Controller; ansonsten
      endet ein erfolgreicher Cloud-Aufruf ehrlich bei `sent` beziehungsweise
      bei nicht eindeutiger Beobachtung `unknown`.
- [x] `state_manager.py` sank von 374 auf **132 Zeilen**. Architekturtests
      erzwingen zwei vollständige Publishes für zwei identische erfolgreiche
      Polls und verhindern die Rückkehr der konkurrierenden APIs.
- [x] StateManager und StatePublisher wurden in die strikte MyPy-Ratsche
      aufgenommen; diese umfasst nun 23 Module.

**Entscheidung zu P2-07:** Die vorgeschlagene Delta-Optimierung wird derzeit
bewusst nicht umgesetzt. Im gesicherten Heimnetz und beim konfigurierten
Pollintervall überwiegen Selbstheilung retained Topics, einfache Semantik und
vollständige Consumer-Updates. Ein Delta-Cache würde wieder ein zweites
Zustandsmodell einführen und benötigt belastbare Broker-/Traffic-Messwerte sowie
eine definierte Behandlung verschwundener Topics. P2-07 wird erst bei gemessener
Last mit periodischem Voll-Refresh neu bewertet.

### Paket 18 – Logging-Redaction und Command-Korrelation: erledigt (Terra, 23.08.2026)

- [x] `log_safety.py` stellt eine zentrale, strikt typisierte Grenze für
      Credential-Redaction, Textbegrenzung und wertfreie Payload-
      Zusammenfassungen bereit. Authorization, Cookie, Passwort, Secret, Token
      und API-Key sowie Bearer-/Basic-Werte werden redigiert.
- [x] Der MQTT-Command-Eingang protokolliert keine Payload-Werte mehr, sondern
      nur Typ, Größe beziehungsweise begrenzte Feldnamen. Auch die bisherige
      Ausgabe der vollständigen Spa-Liste bei noch nicht initialisiertem Gerät
      wurde entfernt.
- [x] Jeder Command-Statusübergang erzeugt ein strukturiertes Event mit
      `command_id`, Command-Pfad, Status und optionalem `error_code`. Damit ist
      die bestehende Correlation-ID auch in Standardlogs durchgängig sichtbar.
- [x] `CommandAuditLogger` schreibt für Parameter, Resultate und Fehlerdetails
      nur Strukturzusammenfassungen. Der MQTT-Logforwarder redigiert Events vor
      der Serialisierung, auch wenn er außerhalb der normalen structlog-Kette
      direkt verwendet wird.
- [x] Rohe Lichtfarbobjekte und konkrete RGB-Kanäle werden nicht mehr auf
      Debug-Ebene ausgegeben; erhalten bleiben nur Payload-Form und der Hinweis
      auf erfolgreiche Normalisierung.
- [x] Ein bislang ungetesteter Laufzeitfehler im Audit-Logger ist behoben:
      `event` wurde gleichzeitig positionell und als Keyword an structlog
      übergeben und löste dadurch beim ersten Audit-Event einen `TypeError` aus.
- [x] Sechs neue Tests sichern Credential-Redaction, Truncation, wertfreie
      Payload-Logs, MQTT-Forwarding, Audit-Payloads und Command-Korrelation ab.
      `log_safety.py` wurde als 24. Modul in die strikte MyPy-Ratsche aufgenommen.
- [x] Console- und rotierte Dateilogs verwenden dieselbe strukturierte JSON-
      Formatierung wie structlog. Gewöhnliche Standard-Logging-Records
      einschließlich ihrer `extra`-Felder werden darin zu maschinenlesbaren
      Events.
- [x] Tracebacks aus externen Bibliotheken werden vor Console-, Datei- und
      MQTT-Ausgabe formatiert, rekursiv redigiert und begrenzt. Verschachtelte
      Secret-Felder, JSON-artige Credentials und Byte-Payloads können damit
      keinen Logging-Sink mehr umgehen. (Terra)

**Abschluss P2-09:** Die gemeinsame Ausgabegrenze normalisiert auch bestehende
Standard-Logging-Aufrufe zu sicheren JSON-Events. Neue Logs sollen weiterhin
stabile Eventnamen und strukturierte Felder verwenden; die Safety- und
Maschinenlesbarkeitsgarantie hängt jedoch nicht mehr davon ab, ob ein
Altaufrufer noch einen interpolierten Nachrichtentext verwendet.

### Paket 19 – Einheitliches Quality- und Security-Gate: erledigt (Terra, 23.08.2026)

- [x] `scripts/quality-check.sh` ist der gemeinsame lokale und CI-Entry-Point
      für vollständiges Ruff, Formatcheck, versionierte MyPy-Policy und den
      Nicht-Browser-Testlauf mit dem 65-%-Coverage-Gate.
- [x] Der Browser-Smoke-Test läuft in CI separat auf einem Chromium-fähigen
      Runner; sein Bedarf an Browser-Infrastruktur kann damit nicht mehr den
      normalen lokalen Quality-Check verfälschen.
- [x] `scripts/security-check.sh` führt Bandit, `pip-audit` gegen den
      gelockten, öffentlich auditierbaren Produktionssatz sowie einen
      `detect-secrets`-Baseline-Vergleich aus. Die per Git-Commit fixierte
      Upstream-Abhängigkeit `python-smarttub` ist dabei explizit dokumentiert,
      weil sie keinen PyPI-Vulnerability-Eintrag besitzt.
- [x] Die frühere globale Bandit-Ausnahme B104 ist entfernt. Die vier
      bewussten Home-LAN-Bindungen besitzen jeweils eine zeilenlokale,
      begründete Ausnahme und die bestehende Laufzeitwarnung bleibt aktiv.
- [x] Dev-Security-Tools sind exakt versioniert; CI publiziert Bandit- und
      Dependency-Audit-Berichte, sofern der CI-Anbieter Artefakte unterstützt.
      (Terra)

### Paket 20 – Reproduzierbare Multi-Arch-Releases: erledigt (Terra, 23.08.2026)

- [x] Die Gitea-Container-Registry ist die kanonische Imagequelle. Nicht-
      Release-CI publiziert ausschließlich den klar als Entwicklung markierten
      Tag `edge`; Release-Tags publizieren SemVer-Tags, aber kein `latest`.
- [x] Release-Builds erzeugen ein gemeinsames OCI-Manifest für
      `linux/amd64,linux/arm64`, SBOM und Provenance. Der erzeugte Digest wird
      in die Release-Notes übernommen.
- [x] Der Releaseprozess verlangt einen konfigurierten Cosign-Schlüssel und
      signiert den Multi-Arch-Digest. Ohne Schlüssel schlägt das Publizieren
      absichtlich früh und verständlich fehl, statt einen unsignierten Release
      als vertrauenswürdig erscheinen zu lassen.
- [x] Compose verwendet die konkrete Version `0.3.3` aus derselben Registry
      und `restart: unless-stopped`; README erklärt Upgrade, Rollback und
      Digest-Deployment. Workflow-/Compose-Contract-Tests verhindern eine
      Rückkehr zu `latest` oder zu einer Ein-Architektur-Veröffentlichung.
      (Terra)

### Paket 21 – Ereignisbasierte Web-Updates: erledigt (Terra, 23.08.2026)

- [x] `/api/events` liefert einen authentifizierten, reconnect-fähigen SSE-
      Stream für State-, Command- und Discovery-Ereignisse mit initialem
      Snapshot sowie Keepalive.
- [x] Ein begrenzter Web-Event-Hub fächert defensive Payload-Kopien aus und
      behält für langsame Clients den jeweils neuesten Zustand statt den
      Anwendungspfad zu blockieren.
- [x] StateManager und CommandManager veröffentlichen über lokale Observer;
      die bestehende Discovery-State-Maschine wird ohne zweiten Discovery-
      Zustand angebunden.
- [x] Dashboard, Command-History und Discovery-Ansicht verarbeiten die
      Ereignisse direkt. EventSource reconnectet mit exponentiellem Backoff;
      das bisherige HTTP-Polling bleibt als robuster Fallback aktiv. (Terra)

### Status der schwierigen Sol-Punkte

Die ursprünglich priorisierten, lokal umsetzbaren Sol-Risikopunkte aus P0 und
P1 sind implementiert und regressionsgetestet. Noch nicht als lokal abgenommen
gelten ausschließlich Grenzen, für die externe Infrastruktur oder nicht
vorhandene Hardware nötig ist:

- der reale Docker-Build läuft mangels lokalem Docker erst im vorhandenen
  CI-Job vollständig durch (P1-12);
- ein echter Prozesskill während einer hardwareverändernden Discovery braucht
  einen kontrollierten Geräte-End-to-End-Test;
- reale Zweistufenpumpen- und weitere Modell-/Firmware-Fixtures fehlen; die
  generische Abbildung ist derzeit durch synthetische Contract-Tests gesichert.

Die Sol-Einträge N4 (weitergehendes 429-Budget/Circuit-Breaker), N9 (gezielte
Zweistufensteuerung bei ausreichendem Upstream-Vertrag) und N12 (Community-
Support-Matrix) sind optionale neue Roadmap-Funktionen, keine offenen Fehler der
abgeschlossenen P0/P1-Härtung. P2-09 ist mit Paket 18 nun als **Terra**
abgeschlossen; P2-07 ist durch die dokumentierte Vollsnapshot-
Produktentscheidung zurückgestellt und P2-08 bereits erledigt.

### Nächste Pakete

- [x] Paket 2: ehrliche Zustandssemantik (`live|stale|unavailable`) und MQTT-
      Availability statt Fake-Fallback-Werten.
- [x] Paket 3: modellneutrale Pumpen-/Capability-Abbildung einschließlich LOW/
      HIGH/UNKNOWN.
- [x] Paket 4: begrenzte Queues, Backpressure, MQTT-Reconnect und degradierter
      Startup.
- [x] Paket 5: zentraler Upstream-Gateway und vereinheitlichte, recovery-sichere
      Discovery-Engine einschließlich separater Datei- und MQTT-Ausgabeadapter.
- [x] Paket 6: getrennte Prozess-Liveness und abhängigkeitsbewusste Readiness.
- [x] Paket 7: Controller-/MQTT-Discovery-Regressionstests und CI-Coverage-Gate
      bei 55 % (nach Paket 8 aktuell 62,05 %).
- [x] Paket 8: gemeinsame Command-Domainvalidierung für HTTP und MQTT samt
      Capability-basierter Temperaturgrenze und stabilen Fehlercodes.
- [x] Paket 9: 65-%-Coverage-Gate, modellneutrale Capability-Grenzen und
      DiscoveryCoordinator-Lifecycle-Tests.
- [x] Paket 10: Heimnetz-Warnung, Security-Dokumentation, Produktions-Lockstand,
      Python-3.13/3.14-Matrix und echtes Wheel (aktuell 70,20 % Coverage).
- [x] Paket 11: wirksames Web-UI-Intervall, explizite Migration früherer
      No-op-Optionen und generierte Konfigurationsreferenz.
- [x] Paket 12: Config-Modulgrenzen und deklaratives, vollständig
      vertraggetestetes Env-Override-Schema.
- [x] Paket 13: globale Prüfung untypisierter Funktionskörper und Strict-Ratsche
      für 17 stabile Kern-/Command-Module ohne pauschales Import-Ignorieren.
- [x] Paket 14: globale Exception-Ausnahmen entfernt, konkrete Fehler verengt
      und verbleibende Adaptergrenzen lokal mit monotoner Obergrenze sichtbar.
- [x] Paket 15: zentraler, schema-versionierter und atomarer Discovery-
      Repository-Pfad; Eventloop-Aufrufer nutzen Worker-Threads und der
      TopicMapper nur einen Memory-Snapshot.
- [x] Paket 16: reine State-/Metadaten-/Discovery-Encoder, unveränderliche
      MQTT-Nachrichten und eine einzige, separat getestete Versandgrenze.
- [x] Paket 17: StateManager auf ein einziges Vollsnapshot-Modell reduziert;
      tote Delta-, Recovery- und Pseudo-Reconciliation-Pfade entfernt.
- [x] Paket 18 (P2-09): zentrale Log-Redaction, sichere strukturierte JSON-
      Ausgabe für Console/Datei/MQTT einschließlich externer Tracebacks,
      wertfreie Command-Payload-Zusammenfassungen und strukturierte
      Correlation-ID-Transitions. (Terra)
- [x] Paket 19 (P2-10): gemeinsames vollständiges Quality-Gate, separater
      Browser-Smoke-Job sowie Bandit-, Lockfile- und Secret-Checks ohne globale
      Security-Ausnahmen. (Terra)
- [x] Paket 20 (P2-13): kanonische Gitea-Registry, versioniertes Compose,
      Multi-Arch-Release mit SBOM/Provenance und verpflichtender Cosign-
      Signatur. (Terra)
- [x] Paket 21 (P3-03): SSE für State, Commands und Discovery mit begrenztem
      Fan-out, Reconnect-Backoff und beibehaltenem Polling-Fallback. (Terra)
- [x] Paket 21 (P2-11, P2-12, P2-14): warnungsfreier Python-3.14-Testclient,
      zentrale Paket-/API-/CLI-/OCI-Version, echte Projekt-URLs und
      konsolidierte Dokumentation mit Release-Notes-Template. (Luna)
- [x] Paket 22 (P3-02, P3-04): native, zugängliche Discovery-Radio-Inputs
      mit Zustandsdarstellung sowie isolierte Quality-Artefakte und ein
      begrenzter Clean-Task für bekannte Build-/Python-Caches. (Luna)

## 1. Kurzfazit

Das Projekt ist deutlich weiter als ein einfacher MQTT-Wrapper: Es besitzt eine
nachvollziehbare Schichtenstruktur, eine serielle Befehlsverarbeitung, eine
Capability-/Light-Mode-Discovery, ein brauchbares Web-Dashboard, strukturierte
Logs, Docker- und CI-Unterstützung sowie 279 automatisierte
Nicht-Browser-Tests. Ruff und der
aktuell konfigurierte MyPy-Lauf sind fehlerfrei. Die Abhängigkeit
`python-smarttub` ist mit `0.0.48` auf dem zum Analysezeitpunkt neuesten
Upstream-Tag. Der aktuelle Nicht-Browser-Prüfstand umfasst 279 Tests und
70,33 % Coverage; die folgenden Risikobefunde dokumentieren zusätzlich den
historischen Ausgangszustand vor den Umsetzungspaketen.

Vor einem als zuverlässig und sicher beworbenen Produktivbetrieb sollten jedoch
vier Themen zwingend gelöst werden:

1. Einige fehlgeschlagene Gerätebefehle werden intern verschluckt und danach als
   **erfolgreich** gemeldet.
2. Bei Cloud-/API-Fehlern werden erfundene Zustände wie „Heizung aus“ und „keine
   Pumpen“ publiziert. Ein technischer Ausfall ist damit nicht von einem echten
   Gerätezustand zu unterscheiden.
3. Die Web-Steuerung lauscht standardmäßig auf allen Interfaces, während die
   Authentifizierung standardmäßig deaktiviert ist.
4. Ausgerechnet die komplexesten und hardwarekritischen Module sind nur schwach
   getestet; die Gesamt-Coverage ohne Browser-Smoke-Test beträgt **45 %**.

Die Architektur ist grundsätzlich rettbar und muss nicht neu geschrieben
werden. Sinnvoll ist eine schrittweise Härtung: zuerst korrekte Fehlersemantik
und Zustandsqualität, dann Entkopplung des Upstream-Adapters, danach Discovery-
und Konfigurationszerlegung.

## 2. Modell-Empfehlungen

Die Angabe nennt jeweils das **kleinste sinnvoll geeignete Modell**. Ein stärkeres
Modell kann die Aufgaben eines kleineren ebenfalls übernehmen.

| Modell | Geeignet für |
| --- | --- |
| **GPT-5.6 Luna** | Kleine, klar begrenzte Korrekturen; Konfiguration, Dokumentation, einzelne Tests oder mechanisches Refactoring |
| **GPT-5.6 Terra** | Mittlere, mehrere Dateien betreffende Änderungen mit klarer vorhandener Architektur |
| **GPT-5.6 Sol** | Komplexe Nebenläufigkeit, Sicherheits-/Safety-Themen, Hardwarezustände, größere Architekturänderungen und Upstream-Protokollfragen |

## 3. Bewertungsübersicht

| Bereich | Bewertung | Hauptgrund |
| --- | ---: | --- |
| Architektur | 6/10 | Gute grobe Schichtung, aber sehr große Module, doppelte Discovery-Logik und schwache Domänengrenzen |
| Funktionskorrektheit | 5/10 | Mehrere bestätigte Fehler in Befehls- und Zustandswegen |
| Zuverlässigkeit | 4/10 | Fehler werden teils verschluckt; Fake-Fallback-Zustände; unbeschränkte Queues |
| Security | 5/10 | Solide Secret-Grundlagen, aber Web-Steuerung standardmäßig offen und Security-CI lückenhaft |
| Testqualität | 5/10 | 78 nicht-browserbasierte Tests bestehen, aber nur 45 % Coverage und kritische Pfade sind kaum abgedeckt |
| Typisierung/Linting | 7/10 | Aktueller MyPy- und Ruff-Lauf grün; MyPy prüft untypisierte Funktionskörper nicht vollständig |
| Deployment | 5/10 | Docker/CI vorhanden, aber fragiler Editable-Build, `latest`, nur AMD64 und schwacher Healthcheck |
| Web-UI/UX | 7/10 | Gute jüngste Verbesserungen; Status-/Fehlersemantik und Live-Kommunikation bleiben ausbaufähig |
| Dokumentation | 7/10 | Gute Architektur- und Entwicklerdokumente, aber mehrere Drift-/Versionsprobleme |

## 4. Positive Befunde

- Die Verantwortlichkeiten `core`, `mqtt`, `web`, `cli` und `docker` sind
  grundsätzlich verständlich getrennt.
- `SmartTubClient`, `SmartTubStateReader` und `SmartTubController` sind bereits
  als Adapter/Fassade getrennt; das ist eine gute Basis für weitere Härtung.
- Web- und MQTT-Befehle laufen über dieselbe serielle Command-Queue. Das verhindert
  viele Race Conditions zwischen gleichzeitigen Gerätebefehlen.
- Die Instanz ist bewusst auf genau einen Whirlpool beschränkt; fremde Spa-IDs
  werden bei MQTT-Befehlen verworfen.
- Basic Auth vergleicht Zugangsdaten mit `secrets.compare_digest` und interne
  Exceptions werden nicht direkt in HTTP-Antworten offengelegt.
- Der MQTT-Client nutzt den nativen `aiomqtt`-2.x-Lebenszyklus und stellt
  Subscriptions nach Reconnect wieder her.
- Snapshot-Leser der Web-Schicht erhalten eine tiefe Kopie statt des internen
  mutierbaren Zustands.
- Die lokale Bootstrap-Datei reduziert Laufzeitabhängigkeiten von CDNs.
- Architektur- und Entwicklerdokumentation sind für ein Projekt dieser Größe
  überdurchschnittlich hilfreich.
- Upstream `python-smarttub v0.0.48` enthält die aktuelle Authentifizierung und
  `ECO_MODE`; das Projekt nutzt diese Version bereits.

## 5. Priorisierte Befunde und Maßnahmen

### P0 – vor produktiver Freigabe beheben

#### P0-01 – Gerätefehler werden als Erfolg gemeldet

**Umsetzungsstatus:** ✅ Mit Paket 1 implementiert und durch Regressionstests
abgesichert. Kommando-spezifische `confirmed`-Verifier folgen mit Paket 2/3.

**Befund:** In [`src/core/smarttub_controller.py`](src/core/smarttub_controller.py)
fangen `set_pump_state`, `set_light_mode`, `set_light_color` und
`set_light_brightness` Cloud-/API-Exceptions ab, protokollieren sie und kehren
normal zurück. Auch „Pump/Licht nicht gefunden“ und ungültige Zonen enden häufig
mit einem normalen `return`. `CommandManager` interpretiert jede normale Rückkehr
als Erfolg und schreibt einen erfolgreichen History-Eintrag. Web-UI und MQTT-
Logs können daher Erfolg anzeigen, obwohl nichts geschaltet wurde.

**Auswirkung:** Falsche Bedienrückmeldung, unsichere Automatisierung und kaum
diagnostizierbare Gerätefehler.

**Umsetzung:**

1. Domänenfehler wie `ComponentNotFound`, `UnsupportedCommand`,
   `CloudCommandFailed` und `CommandVerificationFailed` einführen.
2. Controller-Methoden dürfen erwartete Fehler mit Kontext anreichern, müssen sie
   aber wieder werfen.
3. Nur echte Idempotenz („bereits im Zielzustand“) gilt als Erfolg.
4. `CommandManager` führt den festgelegten Statusautomaten
   `accepted → sent → confirmed` und die Ausgänge `failed|unknown`. Wenn die API
   keinen verlässlichen Read-back erlaubt, endet der Befehl bei `sent` oder
   `unknown`, niemals bei einem erfundenen `confirmed`.
5. `CommandManager` übersetzt Exceptions in `failed`; Web-Endpunkte liefern je
   nach Fehler 404, 409, 422 oder 503.
6. Tests für jeden Fehlerpfad, jedes Status-Transition und die History ergänzen.

**Abnahme:** Ein simulierter `spa.request()`-Fehler führt zu HTTP 503 bzw. einem
`failed`-History-Eintrag und niemals zu einer Erfolgsmeldung. Eine positive
Cloud-Antwort ohne beobachtbaren Read-back wird als `sent`/`unknown`, ein per API
beobachteter Zielzustand als `confirmed` ausgewiesen.\
**Empfohlenes Modell:** **GPT-5.6 Sol** – safety-relevanter, schichtenübergreifender
Umbau.

#### P0-02 – Fallback publiziert erfundene Hardwarezustände

**Umsetzungsstatus:** ✅ Mit Paket 2 implementiert und durch Regressionstests
abgesichert. Öffentliche Zustände enthalten bewusst keinen rohen `source_error`;
Details bleiben aus Sicherheitsgründen in den strukturierten Logs.

**Befund:** [`src/core/smarttub_state_reader.py`](src/core/smarttub_state_reader.py)
wandelt einen allgemeinen Lesefehler in einen Snapshot mit `heater=off`, leeren
Pumpen/Lichtern und `spa=unknown` um. `StateManager.sync_state()` publiziert ihn
wie echte Telemetrie. Auch `/api/state` liefert vor dem ersten erfolgreichen
Abruf diesen Fake-Zustand.

**Auswirkung:** „Nicht bekannt“ wird fälschlich als „aus/nicht vorhanden“
interpretiert. Retained MQTT-Werte können Automationen und UI dauerhaft irreführen.

**Umsetzung:**

1. Snapshot-Hülle einführen: `observed_at`, `received_at`, `quality`
   (`live|stale|unavailable`), `source_error` und optional `data`.
2. Bei Fehler den letzten guten Snapshot unverändert behalten und nur
   Availability/Quality auf `offline` bzw. `stale` setzen.
3. Separates retained Topic `<base>/<spa>/availability` verwenden.
4. Erst nach einem erfolgreichen Vollabruf Komponentenwerte publizieren.
5. UI muss stale/unavailable klar darstellen und Schreibaktionen optional sperren.

**Abnahme:** Ein API-Timeout ändert keinen bekannten Pumpen-/Heizwert, publiziert
aber zuverlässig `availability=offline` und ein Datenalter.\
**Empfohlenes Modell:** **GPT-5.6 Sol** – Änderung des zentralen Zustandsvertrags.

#### P0-03 – Web-Steuerung ist standardmäßig im Netzwerk ungeschützt

**Umsetzungsstatus:** ✅ Gemäß der Produktentscheidung mit Paket 10
abgeschlossen. Der LAN-Default bleibt erhalten, warnt aber bei breiter Bindung
ohne Authentifizierung sichtbar; README und `.env.example` beschreiben die
Heimnetzgrenze, Basic Auth, VPN/HTTPS-Proxy und das Verbot direkter
Portweiterleitung. Health-Endpunkte bleiben absichtlich informationsarm offen.

**Befund:** `WEB_HOST=0.0.0.0`, `WEB_ENABLED=true` und
`WEB_AUTH_ENABLED=false` sind die Standardwerte. Damit sind schreibende
Temperatur-, Pumpen-, Licht-, Discovery- und Error-Clear-Endpunkte im lokalen
Netz ohne Anmeldung erreichbar. Bandit meldet das Binden an alle Interfaces
dreimal als Medium-Risiko.

**Produktentscheidung:** Die Web-UI ist für den Betrieb in einem **gesicherten
Heimnetz** vorgesehen. Ein direktes Exponieren ins Internet gehört nicht zum
unterstützten Standardbetrieb.

**Umsetzung:** Eine zum Heimnetz passende sichere Standardstrategie festlegen:

- `0.0.0.0` darf für den LAN-Betrieb erhalten bleiben, muss aber beim Start eine
  deutliche Warnung ausgeben, wenn Basic Auth deaktiviert ist;
- README und `.env.example` müssen klar sagen: nur vertrauenswürdiges Heimnetz,
  kein Port-Forwarding und kein direkter Internetzugriff;
- für Netze mit Gästen, IoT-Segmenten oder nicht vollständig vertrauenswürdigen
  Teilnehmern Basic Auth weiterhin dringend empfehlen;
- externer Zugriff ausschließlich über VPN oder einen authentifizierenden
  HTTPS-Reverse-Proxy dokumentieren;
- schreibende API-Routen getrennt absichern und Login-Rate-Limit/Reverse-Proxy-
  Hinweise ergänzen;
- Readiness/Health darf anonym bleiben, aber keine Detaildaten offenlegen.

**Abnahme:** Die dokumentierte Standardkonfiguration ist eindeutig auf ein
vertrauenswürdiges LAN beschränkt, warnt sichtbar vor unauthentifiziertem Betrieb
und beschreibt einen sicheren VPN-/Proxy-Weg für externen Zugriff.\
**Empfohlenes Modell:** **GPT-5.6 Terra** – klar begrenzte Security-, Config- und
Dokumentationsänderung.

#### P0-04 – MQTT-Helligkeit `0` funktioniert nicht

**Umsetzungsstatus:** ✅ Mit Paket 1 behoben und getestet.

**Befund:** In `CommandHandlers.set_light_brightness()` wird
`data.get("brightness") or data.get("value")` verwendet. Der gültige Wert `0`
ist falsy und wird dadurch durch `value`/`None` ersetzt. Ein Licht kann über ein
JSON-Payload mit `{"brightness": 0}` nicht zuverlässig auf null gesetzt werden.

**Umsetzung:** Schlüsselpräsenz statt Truthiness prüfen; anschließend parametrisierte
Tests für `0`, `1`, `100`, negative Werte, `101`, Strings und fehlende Werte.

**Abnahme:** `0` erreicht unverändert den Controller; außerhalb 0–100 wird ein
Fehler zurückgegeben und als fehlgeschlagen verbucht.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P0-05 – RGB-JSON mit Nullkanälen wird falsch geparst

**Umsetzungsstatus:** ✅ Mit Paket 1 behoben und getestet.

**Befund:** `_parse_rgb_color()` nutzt für die Kanäle `data.get("red") or
data.get("r")`. Damit wird z. B. `{"red":0,"green":255,"blue":0}` für Rot und
Blau zu `None`, obwohl Null ein gültiger Kanalwert ist.

**Umsetzung:** Aliasauflösung anhand vorhandener Schlüssel implementieren,
Schema strikt validieren, Bool-Werte ablehnen und außerhalb 0–255 entweder klar
ablehnen oder dokumentiert clampen.

**Abnahme:** Primär- und Kurzschlüssel akzeptieren alle Nullkanäle; unvollständige
Objekte liefern einen kontrollierten Validierungsfehler.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P0-06 – Globaler Brightness-Befehl kann `lights/None` aufrufen

**Umsetzungsstatus:** ✅ Mit Paket 1 behoben: schreibende Pumpen-/Lichtbefehle
verlangen eine explizite Komponenten-ID und ungültige IDs schlagen sichtbar fehl.

**Befund:** Ohne `light_id` wählt `set_light_brightness()` zwar das erste Licht,
verwendet beim PATCH jedoch weiterhin die lokale Variable `zone=None`. Der globale
MQTT-Pfad `lights/brightness_writetopic` ist abonniert und kann deshalb einen
Request auf `lights/None` auslösen. Ähnliche implizite „erstes Element“-Fallbacks
existieren für andere Komponenten.

**Umsetzung:** Generische Topics entweder entfernen oder explizit dokumentieren.
Falls „erstes Licht“ gewünscht ist, nach Auswahl immer
`target_zone = target_light["zone"]` nutzen. Bevorzugt jede schreibende
Komponentenaktion mit einer verpflichtenden, validierten ID ausführen.

**Abnahme:** Kein Command-Pfad kann eine URL mit `None` erzeugen; unbekannte oder
fehlende IDs schlagen sichtbar fehl.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P0-07 – Ungültiger Heizmodus fällt still auf `AUTO` zurück

**Umsetzungsstatus:** ✅ Mit Paket 1 behoben und getestet.

**Befund:** `set_heat_mode()` verwendet `getattr(heat_mode, mode.upper(),
heat_mode.AUTO)`. Jeder Tippfehler wird somit zu einem echten `AUTO`-Befehl.

**Auswirkung:** Ein ungültiger Benutzerwunsch verändert das Gerät unerwartet.

**Umsetzung:** Nur exakt unterstützte Enum-Namen akzeptieren; unterstützte Werte
aus der installierten Bibliothek ableiten; Web und MQTT dieselbe Validierung nutzen.

**Abnahme:** `AUTOO` erzeugt einen Validierungsfehler und keinen Cloud-Request.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P0-08 – LOW-Pumpenstatus wird als „aus“ veröffentlicht

**Umsetzungsstatus:** ✅ Mit Paket 3 implementiert und durch normalisierte
Contract- sowie Read-back-Tests abgesichert. Mangels Geräte-Rohdaten im
Repository sind zusätzliche anonymisierte Community-Fixtures weiterhin
erwünscht, aber keine unbekannte Form wird mehr als aus/einstufig angenommen.

**Befund:** Der StateReader setzt eine Pumpe nur für `HIGH` oder `ON` auf
`running`; `LOW` wird `off`. Gleichzeitig wird die Geschwindigkeit immer als
`ONE_SPEED` ausgegeben. Das ist insbesondere im Kontext des offenen Upstream-
Themas [Two-speed pump support #68](https://github.com/mdz/python-smarttub/issues/68)
problematisch.

**Produktentscheidung:** Das öffentliche GitHub-Projekt darf keine einzelne
Whirlpoolserie als Normalfall voraussetzen. Unterschiede zwischen Modellen,
Marken und Firmwareständen müssen über beobachtete Daten und Capabilities
abgebildet werden.

**Umsetzung:** Pumpenzustand und Geschwindigkeit getrennt und modellneutral
modellieren:
`state=on|off`, `speed=off|low|high|unknown`, `type=one_speed|two_speed|circulation`.
Reale, anonymisierte Fixture-Daten für Ein- und Zweistufenpumpen verschiedener
Modelle sammeln und als Contract-Tests ablegen. Unbekannte Werte müssen als
`unknown` erhalten bleiben, nicht auf einen vermuteten Default reduziert werden.

**Abnahme:** `LOW` wird als laufend mit niedriger Stufe publiziert; keine
unbeobachtete Geschwindigkeit wird erfunden.\
**Empfohlenes Modell:** **GPT-5.6 Sol** – benötigt Geräte-/Upstream-Verständnis.

### P1 – hohe Priorität

#### P1-01 – Konfiguriertes Capability-Intervall wird ignoriert

**Umsetzungsstatus:** ✅ Mit Paket 4 behoben und durch einen Lifecycle-Test
abgesichert.

**Befund:** Die Konfiguration lädt `CAPABILITY_REFRESH_INTERVAL`, der
Application-Start verwendet aber `polling_interval_seconds * 5`. Bei den
Defaults sind das 150 statt dokumentierter 300 Sekunden.

**Umsetzung:** `config.capability.refresh_interval_seconds` direkt an
`_capability_refresh_loop()` übergeben und mit einem Lifecycle-Test absichern.

**Abnahme:** Ein gesetzter Wert wird exakt im Task verwendet.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P1-02 – Mehrere Konfigurationswerte sind tote oder irreführende Optionen

**Umsetzungsstatus:** ✅ Mit Paket 11 behoben. Das UI-Intervall wirkt bis in den
Browser-Polling-Takt; ehemalige No-op-Optionen warnen und werden kontrolliert
ignoriert. Registry, generierte Referenz und Drift-/Wirkungstests sichern diese
Entscheidung ab.

**Befund:** `observability.*`, `web_ui.refresh_interval_seconds`, Teile von
`safety.*`, `enable_auto_discovery` und `discovery_refresh_interval` werden
geladen/validiert, aber nicht oder nur teilweise im normalen Laufzeitpfad
verwendet. Die UI pollt fest mit 30 Sekunden, obwohl eine Web-UI-Konfiguration
existiert. Changelog, `.env.example` und tatsächlicher Code widersprechen sich
bei Safety-Optionen.

**Umsetzung:** Für jede Option entscheiden: implementieren, deprecaten oder
entfernen. Eine maschinenlesbare Registry aus Env-Name, YAML-Pfad, Default,
Validator und Beschreibung erstellen; daraus `.env.example` und Referenzdoku
generieren.

**Abnahme:** Jede dokumentierte Variable besitzt mindestens einen Test, der eine
sichtbare Laufzeitwirkung nachweist.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P1-03 – Unbeschränkte Command- und Publish-Queues

**Umsetzungsstatus:** ✅ Mit Paket 4 implementiert: beide Queues sind
konfigurierbar begrenzt, Overflow/Timeout sichtbar und der Command-Worker wartet
ereignisgesteuert.

**Befund:** Sowohl `queue.Queue()` für Befehle als auch `asyncio.Queue()` für
Publishes haben keine Obergrenze. Bei MQTT-Flut oder langsamem Broker wächst der
Speicherverbrauch unbegrenzt. Der Command-Worker pollt zusätzlich alle 100 ms,
obwohl die Callback-Verarbeitung bereits im Async-Eventloop läuft.

**Umsetzung:** `asyncio.Queue(maxsize=...)`, blockierendes `await queue.get()`,
Timeouts, Metriken und definierte Overflow-Politik einführen. Gerätebefehle nicht
still verwerfen; Telemetrie kann bei Bedarf „latest value wins“ koaleszieren.

**Abnahme:** Lasttest mit mehreren tausend Nachrichten hält Speicher und Latenz
innerhalb definierter Grenzen; Overflow ist sichtbar.\
**Empfohlenes Modell:** **GPT-5.6 Sol** – Nebenläufigkeit und Backpressure.

#### P1-04 – Fire-and-forget-MQTT verliert Daten bei Disconnect/Shutdown

**Umsetzungsstatus:** ✅ Mit Paket 4 für kontrollierte Disconnects behoben:
retained Werte koaleszieren, Command-Ergebnisse werden begrenzt gepuffert,
Reconnect leert den Puffer und Shutdown versucht einen zeitlich begrenzten
Drain. Ein harter Prozesskill bleibt ohne persistente Outbox naturgemäß offen.

**Befund:** `publish_sync()` überspringt Publishes vollständig, wenn die Verbindung
offline ist. Bei Shutdown werden Worker sofort abgebrochen, ohne die Queue zu
leeren. `get_buffer_stats()` meldet trotzdem nur Nullen. Retained Status und
Command-Ergebnisse können verloren gehen.

**Umsetzung:** Publishes nach Semantik klassifizieren: Telemetrie darf koaleszieren,
Availability/Command-Ergebnis muss bestätigt oder nach Reconnect erneut gesendet
werden. Beim Shutdown kurze Drain-Frist; ehrliche Queue-/Drop-Metriken.

**Abnahme:** Ein Disconnect-Reconnect-Test bestätigt, dass der letzte Zustand und
Availability anschließend konsistent sind.\
**Empfohlenes Modell:** **GPT-5.6 Sol**.

#### P1-05 – Direkte Nutzung interner Upstream-Endpunkte ist verstreut

**Umsetzungsstatus:** ✅ Mit Paket 5 abgeschlossen. Direkte Low-Level-Aufrufe
existieren ausschließlich in `SmartTubGateway`; alle Verbraucher nutzen dessen
getestete Compatibility-Methoden.

**Befund:** Mehrere Stellen verwenden `spa.request("GET/PATCH/POST", ...)` direkt,
teilweise wegen alter `python-smarttub`-Bugs. Upstream `v0.0.45` nennt bereits
Fixes für Pump-/Light-State-Probleme; Kommentare und Workarounds müssen deshalb
neu validiert werden. Direkte Requests koppeln das Projekt an undokumentierte
Pfade und Payloads.

**Umsetzung:** Sämtliche direkten Requests in einen versionierten
`SmartTubGateway`/Compatibility-Adapter verschieben. Für jede Abweichung einen
Upstream-Link, unterstützte Versionen und Contract-Test hinterlegen. Nicht mehr
nötige Workarounds entfernen oder upstream als PR beitragen.

**Abnahme:** Außerhalb des Adapters existiert kein `spa.request`; ein Upgrade von
`python-smarttub` kann zentral getestet werden.\
**Empfohlenes Modell:** **GPT-5.6 Sol**.

#### P1-06 – Discovery ist doppelt und extrem komplex implementiert

**Umsetzungsstatus:** ✅ Mit Paket 5 abgeschlossen. Der gemeinsame
hardwareverändernde Kern liegt in `LightDiscoveryEngine`; Datei- und MQTT-Ausgabe
liegen in `DiscoveryFileRepository` und `DiscoveryMqttPublisher`. Der CLI-Prober
enthält nur noch kleine Orchestrierungs-, Inventar- und Mode-Plan-Schritte. Kein
Discovery-Funktionskörper überschreitet 50 Zeilen oder Ruff-Komplexität 10.

**Befund:** `item_prober.py` hat 1.639 Zeilen; `background_discovery.py` weitere
596. Die Komplexitätsprüfung meldet u. a. Werte bis C901=52, 219 Statements in
einer Funktion und bis zu 53 Branches. Test-, Restore-, Verifikations- und YAML-
Logik sind teilweise doppelt.

**Umsetzung:** Gemeinsame Discovery-Engine mit kleinen Strategien erstellen:
`ModePlan`, `ProbeExecutor`, `StateVerifier`, `RestoreTransaction`,
`DiscoveryRepository` und `ProgressSink`. CLI, MQTT und Web verwenden nur noch
dieselbe Engine mit unterschiedlichen Triggern.

**Abnahme:** Kein Discovery-Funktionskörper überschreitet etwa 50 Zeilen bzw.
Komplexität 10; Quick/Full/Restore sind durch identische Contract-Tests abgedeckt.\
**Empfohlenes Modell:** **GPT-5.6 Sol**.

#### P1-07 – Discovery-Manipulation braucht eine robustere Safety-Transaktion

**Umsetzungsstatus:** ✅ Softwareseitig für Background/Web/MQTT und CLI mit
Paket 5 umgesetzt: atomisches Journal, Restore im cancellation-geschützten Pfad,
Recovery vor jedem neuen Lauf, Abbruch bei unvollständigem Vorzustand und
Blockierung bei nicht verifiziertem Restore. Die ausstehende Hardwareprüfung
eines echten Prozesskills ist als End-to-End-Abnahme dokumentiert.

**Befund:** Light-Mode-Discovery verändert reale Beleuchtung über Minuten und
versucht anschließend die Wiederherstellung. Viele Fehlerpfade werden breit
abgefangen oder sogar ignoriert. Ein Abbruch, Prozesskill oder API-Fehler kann
einen unerwünschten Zustand hinterlassen.

**Umsetzung:** Vorzustand persistent als Recovery-Journal speichern, jeden Schritt
idempotent machen, Restore in `finally` mit begrenzten Retries durchführen und
beim nächsten Start ein unvollständiges Journal erkennen. UI verlangt eine
Bestätigung mit Dauer- und Auswirkungsangabe.

**Abnahme:** Abbruchtests an jedem Schritt führen spätestens beim Neustart zum
Restore oder zu einer unübersehbaren manuellen Recovery-Anweisung.\
**Empfohlenes Modell:** **GPT-5.6 Sol**.

#### P1-08 – Healthcheck prüft nur den Webprozess

**Umsetzungsstatus:** ✅ Mit Paket 6 abgeschlossen. `/live` bleibt reine
Prozess-Liveness, `/ready` liefert HTTP 200/503 anhand von MQTT, SmartTub,
Snapshot-Qualität/-Alter und Command-Worker. Docker verwendet bewusst `/live`,
damit vorübergehend gestörte, selbstheilende Abhängigkeiten keinen Restart-Loop
auslösen.

**Befund:** `/health` antwortet immer mit `healthy`, unabhängig von SmartTub-
Login, Alter des letzten Snapshots, MQTT-Verbindung, Command-Worker und Discovery.
Docker kann daher einen funktional ausgefallenen Container als gesund melden.

**Umsetzung:** `/live` für reine Prozess-Liveness und `/ready` für Abhängigkeiten
trennen. Readiness enthält nur sichere Statusfelder: MQTT verbunden, initialer
SmartTub-Abruf erfolgt, Snapshot-Alter, Queue-Worker aktiv. Docker nutzt passend
zur Restart-Strategie `/live` oder `/ready`.

**Abnahme:** Simulierter Broker-/Cloud-Ausfall verändert Readiness reproduzierbar,
ohne den Prozess fälschlich als abgestürzt zu behandeln.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P1-09 – Kritische Module sind kaum getestet

**Umsetzungsstatus:** ✅ Paket 7 setzte das erste CI-Gate bei 55 % um; Paket 9
hob es auf 65 % an. Die
aktuelle Gesamt-Coverage beträgt **70,33 %**; `smarttub_controller` erreicht
75 %, `discovery_handler` 88 %, `CapabilityDetector` 89 % und
`DiscoveryCoordinator` 82 %. Alle öffentlichen Controller-Schreibbefehle
besitzen mindestens einen Erfolgs- und Fehlerfall. Nur die geplante letzte
Ratsche auf 75 % bleibt als Folgearbeit und ist an die oben genannten kritischen
Modulgruppen gebunden.

**Befund:** Gemessene Gesamt-Coverage ohne Browser-Smoke-Test: **45 %**. Besonders
schwach sind `item_prober` (11 %), `capability_detector` (13 %),
`smarttub_controller` (15 %), `log_rotation` (18 %), `discovery_handler` (20 %),
`command_handlers` (25 %) und `error_tracker` (31 %). Gerade dort liegen
Hardwarebefehle, Recovery und Discovery.

**Umsetzung:** Zuerst verhaltensbasierte Tests für P0/P1 ergänzen, danach
Coverage-Gates gestuft anheben: 55 %, 65 %, 75 %. API-Fixtures anonymisieren und
Contract-Tests für verschiedene Spa-Modelle einführen. Mutation Testing für
Validatoren und Command-Routing erwägen.

**Abnahme:** Kein Controller-Command besitzt einen ungetesteten Erfolgs- oder
Fehlerpfad; CI erzwingt die vereinbarte Schwelle.\
**Empfohlenes Modell:** **GPT-5.6 Terra**; für reale Protokoll-Fixtures **Sol**.

#### P1-10 – Start ist nicht degradiert möglich

**Umsetzungsstatus:** ✅ Mit Paket 4 für initiale Broker-/Cloud-Ausfälle
implementiert. Der Prozess bleibt aktiv, meldet `degraded` und erholt sich durch
Broker-Backoff sowie erneute Cloud-Initialisierung im Polling-Pfad.

**Befund:** Broker-Verbindung und SmartTub-Initialisierung sind harte
Startup-Voraussetzungen. Ist eine Cloud-/Broker-Abhängigkeit kurz nicht verfügbar,
endet der Prozess, statt Webdiagnose, Backoff und Recovery anzubieten.

**Umsetzung:** Composition Root starten, Services separat mit Zustandsautomaten
verbinden, exponentielles Backoff/Jitter und Circuit Breaker verwenden. Web-UI
und Health bleiben verfügbar, Schreibaktionen sind bis `ready` gesperrt.
Insbesondere Upstream [429 Too Many Requests #63](https://github.com/mdz/python-smarttub/issues/63)
bei Authentifizierung berücksichtigen.

**Abnahme:** Start ohne Broker/Cloud bleibt stabil, zeigt `degraded` und erholt
sich nach Wiederkehr automatisch ohne Neustart.\
**Empfohlenes Modell:** **GPT-5.6 Sol**.

#### P1-11 – Abhängigkeiten sind nicht reproduzierbar

**Umsetzungsstatus:** ✅ Mit Paket 10 für Produktionsbuilds abgeschlossen.
`requirements.lock` enthält exakte Versionen, der Upstream ist per Commit-SHA
fixiert und CI prüft Python 3.13/3.14 gegen denselben Produktions-Constraints-
Stand. Entwicklungswerkzeuge bleiben bewusst ein separat aktualisierbares
Extra.

**Befund:** Bis auf den Git-Tag des Upstreams sind Abhängigkeiten nur mit unteren
Grenzen versehen; ein Lockfile fehlt. Ein Git-Dependency erschwert Offline-Builds
und Tags sind theoretisch verschiebbar. Die lokale Umgebung enthält bereits sehr
neue Versionen (z. B. FastAPI 0.141.1 und Uvicorn 0.52.3), ohne dass CI eine
Kompatibilitätsmatrix erzwingt.

**Umsetzung:** `uv.lock` oder kompiliertes Constraints-File einchecken; Upstream
nach Möglichkeit als veröffentlichte Distribution beziehen oder Commit-SHA plus
Hash pinnen. Renovate/Dependabot in kleinen PRs mit Tests nutzen.

**Abnahme:** Zwei saubere Builds installieren identische Versionen; Build benötigt
keinen beweglichen Git-Tag.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P1-12 – Docker-Build installiert das Projekt als Editable ohne Source

**Umsetzungsstatus:** 🟡 Der Dockerfile baut und installiert jetzt ein echtes
Wheel ohne `/app/src`-Fallback; Wheel und Assets wurden lokal aus `/tmp`
verifiziert. Die abschließende Container-Abnahme bleibt dem vorhandenen CI-Job
vorbehalten, da lokal kein Docker-CLI verfügbar ist.

**Befund:** Im Builder werden nur `pyproject.toml` und `README.md` kopiert, danach
läuft `pip install -e .`; `src/` wird erst im Runtime-Stage nach `/app` kopiert.
Das funktioniert aktuell hauptsächlich, weil `/app` das Working Directory ist,
ist aber kein sauberer, unveränderlicher Artefakt-Build.

**Umsetzung:** Source vor dem Build kopieren, ein Wheel bauen und dieses Wheel in
einer frischen Runtime-Venv installieren. Danach Import und CLI aus einem anderen
Working Directory testen. Build-Cache über separaten Dependency-Layer erhalten.

**Abnahme:** Container enthält keine Editable-PTH-Datei und startet auch mit
anderem `WORKDIR`.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

### P2 – mittlere Priorität / Codequalität

#### P2-01 – `config_loader.py` ist zu groß und zu verzweigt

**Umsetzungsstatus:** ✅ Mit Paket 12 behoben. Env-Aliasse, Parser, Ziele und
Grenzen sind deklarativ; jeder der 49 Einträge wird parametrisiert ausgeführt.
Parsing, Fehler und Quellen sind getrennt, während die öffentliche Loader-API
kompatibel bleibt.

**Befund:** 920 Zeilen; `_apply_env_overrides()` hat Komplexität 66, 65 Branches
und 139 Statements. Neue Variablen müssen an mehreren Stellen manuell synchron
gehalten werden.

**Umsetzung:** Deklaratives Setting-Schema oder etablierte Settings-Library nutzen;
Aliases, Parser, Grenzen und Dokumentation pro Feld an einer Stelle definieren.

**Abnahme:** Neue Option benötigt eine Definition und einen parametrisierten Test,
nicht mehrere verteilte `if`-Blöcke.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-02 – Typprüfung vermittelt mehr Sicherheit als sie liefert

**Umsetzungsstatus:** ✅ Mit Paket 13 für die zentralen Config-, Command-,
Gateway-, Pumpen- und State-Verträge abgeschlossen. MyPy prüft global auch
untypisierte Körper, 17 Module laufen unter der strengeren Ratsche, und die
pauschale Missing-Import-Ausnahme ist entfernt. Dynamische externe Payloads
bleiben an ihren Adaptergrenzen bewusst als `Any` sichtbar.

**Befund:** MyPy ist grün, meldet aber ausdrücklich untypisierte Funktionskörper,
die standardmäßig nicht geprüft werden. Mehrere Grenzen verwenden weiterhin
`Any`, unparametrisierte `Callable`, unparametrisierte Tasks/Queues und dynamische
Dicts. `StateSnapshot` ist `total=False`, wodurch praktisch alle Felder optional
sind.

**Umsetzung:** `check_untyped_defs`, `disallow_untyped_defs` und schrittweise
strengere Module aktivieren. Pydantic/dataclass-Domänenmodelle für Config,
Commands, Snapshot und Discovery statt frei geformter Dicts verwenden.

**Abnahme:** Zentrale Domain-, Command- und State-Module laufen im strikten
MyPy-Modus ohne pauschales `ignore-missing-imports`.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-03 – 167 breite `except Exception`-Stellen

**Umsetzungsstatus:** ✅ Mit Paket 14 auf eine überprüfbare Policy umgestellt.
Es gibt keine globale Ruff-Ausnahme mehr; konkrete Fehler wurden verengt,
stille Fallbacks entfernt und jede verbleibende breite Grenze ist lokal
sichtbar. Das Test-Ceiling von 67 Suppressionen darf nur sinken.

**Befund:** Der Quellcode enthält 167 breite Exception-Catches; Ruff ignoriert
`BLE001` und `S110` global. Einige Grenzen sollen den Dienst bewusst isolieren,
aber die globale Ausnahme verhindert, zwischen erwartbaren Transportfehlern,
Programmierfehlern und Cancellation sauber zu unterscheiden.

**Umsetzung:** Ignorieren nur lokal mit Begründung; bekannte aiohttp/aiomqtt/
Validation-/Filesystem-Exceptions gezielt behandeln. Unerwartete Exceptions
loggen und propagieren oder den zuständigen Supervisor-Task fehlschlagen lassen.

**Abnahme:** Globale Ruff-Ausnahmen entfallen; verbleibende Suppressionen sind
zeilenlokal und getestet.\
**Empfohlenes Modell:** **GPT-5.6 Terra**, modulweise auch **Luna**.

#### P2-04 – Synchrone Dateioperationen im Eventloop und uneinheitliche Pfade

**Umsetzungsstatus:** ✅ Mit Paket 15 abgeschlossen. Ein zentraler
`DiscoveryRepository` vereinheitlicht Pfad und Schema, schreibt atomar und
serialisiert parallele Updates. Async-Laufzeitpfade lagern I/O in Worker-Threads
aus; der synchrone TopicMapper verwendet nur den beim Start beziehungsweise bei
Schreibvorgängen aktualisierten Memory-Snapshot.

**Befund:** Discovery-/Topic-Code sucht dieselbe YAML-Datei über mehrere feste
Pfade und liest/schreibt synchron. Lange oder konkurrierende Schreibvorgänge
können den Eventloop blockieren; Crash/Parallelzugriff kann Dateien beschädigen.

**Umsetzung:** Einen injizierten `DiscoveryRepository` mit genau einem
konfigurierten Pfad, Schema-Version, atomarem Tempfile+Rename, Lock und
`asyncio.to_thread()` für I/O verwenden.

**Abnahme:** Parallele Lese-/Schreibtests erzeugen immer valides YAML; Pfadlogik
existiert nur an einer Stelle.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-05 – TopicMapper übernimmt zu viele Verantwortlichkeiten

**Umsetzungsstatus:** ✅ Mit Paket 16 abgeschlossen. `StateTopicEncoder`,
`MetadataTopicEncoder` und `DiscoveryTopicEncoder` erzeugen Nachrichten ohne
Brokerzugriff; `MqttPublisher` besitzt allein den Versand. Die öffentliche
`MQTTTopicMapper`-API bleibt als kompatible Kompositionsfassade erhalten.

**Befund:** 796 Zeilen mit State-Mapping, Capabilities, Versionen, Discovery,
YAML-Lesen und Publishing. Datenabbildung ist dadurch eng mit Transport und
Dateisystem gekoppelt.

**Umsetzung:** Reine Mapper (`StateTopicEncoder`, `CapabilityTopicEncoder`,
`DiscoveryTopicEncoder`) ohne I/O erstellen; `MqttPublisher` übernimmt Versand,
Repository übernimmt YAML.

**Abnahme:** Mapper lassen sich mit einfachen Input/Output-Tests ohne Dummy-Client
testen.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-06 – Veraltete/ungenutzte StateManager-Funktionen

**Umsetzungsstatus:** ✅ Mit Paket 17 abgeschlossen. `full_snapshot` ist das
einzige Publikationsmodell; nicht aufgerufene Change-/Merge-/Recovery-Pfade und
die irreführende Command-Pseudo-Verifikation wurden entfernt. CommandManager und
befehlsspezifischer Controller-Read-back bleiben die einzigen Statusautoritäten.

**Befund:** Change Detection, Aggregation, Recovery, Pending Commands und
Reconciliation sind im normalen Hauptpfad teilweise ungenutzt. Gleichzeitig
publiziert `sync_state()` bewusst immer den Vollsnapshot. Das erzeugt zwei
konkurrierende mentale Modelle.

**Umsetzung:** Eindeutig entscheiden: Vollsnapshot plus retained Topics oder
Delta-Publishing. Tote private Funktionen entfernen; echte Command-Verifikation
in einen eigenen `CommandReconciler` verschieben.

**Abnahme:** Jede verbleibende öffentliche/fachliche Funktion hat mindestens einen
Produktionsaufrufer und Test.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-07 – Polling erzeugt unnötig viele MQTT-Publishes

**Entscheidungsstatus:** ⏸️ Bewusst zurückgestellt. Vollständige retained
Snapshots pro Poll sind die festgelegte, selbstheilende Produktsemantik. Eine
Delta-Optimierung wird erst bei gemessener Broker-/Netzlast umgesetzt und muss
dann einen periodischen Voll-Refresh sowie das Entfernen verschwundener Topics
vertraglich definieren.

**Befund:** Jeder Poll publiziert den kompletten Snapshot in vielen Einzelmessages,
auch wenn sich nichts geändert hat. Das kann Broker, Funknetz und OpenHAB mit
identischen retained Nachrichten belasten.

**Umsetzung:** Werte nur bei Änderung publizieren, aber periodischen
`last_seen`/Availability-Heartbeat behalten. Optional ein konfigurierbares
Voll-Refresh-Intervall verwenden.

**Abnahme:** Unveränderte Gerätewerte verursachen pro Poll nur Heartbeat/Status;
spätestens nach dem Voll-Refresh sind alle retained Topics erneut vorhanden.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-08 – Temperatur- und Command-Domainregeln sind nicht zentral

**Umsetzungsstatus:** ✅ Mit Paket 8 abgeschlossen. HTTP und MQTT verwenden
denselben `CommandValidator`; kanonische Payloads, beobachtete Temperaturgrenzen
und stabile Domain-Fehlercodes sind durch Cross-Transport-Tests abgesichert.

**Befund:** Web validiert teilweise per Pydantic, MQTT separat in Handlern und
Controller nochmals anders. Eine Temperatur hat im Web nur den Typ `float`, aber
keine modell-/capabilityabhängige Grenze. Invalid MQTT-Werte werden teils nur
geloggt und anschließend als Erfolg gewertet.

**Umsetzung:** Ein gemeinsames Command-Modell mit Normalisierung, ID- und
Capability-Prüfung vor dem Queueing. Temperaturgrenzen aus Capability/Upstream
beziehen; alle Eingänge verwenden denselben Validator.

**Abnahme:** Derselbe Input erzeugt über HTTP und MQTT dasselbe Domain-Command
oder denselben Fehlercode.\
**Empfohlenes Modell:** **GPT-5.6 Sol**.

#### P2-09 – Logging ist inkonsistent und potenziell zu ausführlich

**Umsetzungsstatus:** ✅ Mit Paket 18 vollständig umgesetzt und durch
Regressionstests abgesichert. Command-/Audit-Payloads werden nur als Struktur
geloggt, Credentials und verschachtelte Werte zentral redigiert,
Statusübergänge mit `command_id` strukturiert korreliert und sämtliche
Console-, Datei- sowie MQTT-Ausgaben folgen einer sicheren JSON-Ausgabegrenze.
Auch Tracebacks externer Bibliotheken werden vor dem Rendern redigiert. (Terra)

**Befund:** `structlog` und Standard-Logging werden gemischt; viele f-Strings
erschweren strukturierte Felder. MQTT-Command-Payloads und rohe Lichtdaten werden
protokolliert. Bei Debug kann das Volumen groß werden; eine zentrale Redaction-
Policy fehlt.

**Umsetzung:** Einheitliche strukturierte Events mit Eventname, spa_id,
component_id, command_id und error_code. Payloads standardmäßig nicht vollständig
loggen, Redaction/Truncation zentral anwenden und Correlation-ID vom Eingang bis
zum Resultat führen.

**Abnahme:** Logs sind maschinenlesbar, Secrets/Payload-Grenzen getestet und ein
Befehl über eine ID vollständig nachvollziehbar.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-10 – CI prüft nur einen Teil der Ruff-Regeln

**Umsetzungsstatus:** ✅ Mit Paket 19 abgeschlossen. Lokaler und CI-Quality-
Lauf verwenden denselben versionierten Entry-Point; Ruff läuft ohne
Regelauswahl. Browser-Smoke ist klar separat, Bandit hat keine globale
Ausnahme mehr und der Security-Workflow kombiniert statische Analyse,
Lockfile-Audit und Secret-Baseline. Die nicht im PyPI-Index verfügbare,
unveränderlich per Git-SHA fixierte Upstream-Abhängigkeit wird dabei nicht als
falscher Audit-Erfolg ausgegeben, sondern explizit vom Registry-Audit getrennt.
(Terra)

**Befund:** Lokal besteht `ruff check .`, in CI wird aber nur `F,E` selektiert.
Komplexität, Bugbear, Security-nahe und Modernisierungsregeln laufen nicht.
Bandit überspringt B104 vollständig. `safety check` ist weniger transparent als
ein lockfilebasierter Audit. Action-Versionen sind nur per Major-Tag gepinnt.

**Umsetzung:** CI und lokale Befehle vereinheitlichen; `ruff check .`, Formatter,
striktere MyPy-Ziele, `pip-audit`/OSV, Bandit mit dokumentierten lokalen
Ausnahmen, Secret-Scan und Container-Scan (z. B. Trivy). Actions auf Commit-SHAs
pinning erwägen.

**Abnahme:** Derselbe `make/just/uv run quality`-Befehl läuft lokal und in CI;
keine globale Security-Ausnahme versteckt Befunde.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-11 – Python-3.14-/Test-Warnungen

**Umsetzungsstatus:** ✅ Mit Paket 21 behoben und mit dem vollständigen
Nicht-Browser-Testlauf auf Python 3.14 geprüft. Die Projektverwendung von
`inspect.iscoroutinefunction` bleibt bestehen; Starlette erhält über das
Dev-Extra nun die kompatible, exakt gepinnte `httpx2`-Testclient-Abhängigkeit.
Der Browser-Smoke-Test bleibt ein separater CI-Job. (Luna)

**Befund:** Tests melden die geplante Entfernung von
`asyncio.iscoroutinefunction` in Python 3.16 sowie eine Starlette-Testclient-
Deprecation. Der vollständige lokale Testlauf hatte 78 bestandene Tests und einen
Browser-Setup-Fehler, weil Chromium in der Sandbox keinen Mach-Port registrieren
konnte; dies ist kein bestätigter Produktfehler.

**Umsetzung:** `inspect.iscoroutinefunction` verwenden; FastAPI/Starlette-Test-
Abhängigkeiten kompatibel pinnen; Browser-Tests klar markieren und einen
separaten CI-Job mit installiertem Chromium führen.

**Abnahme:** Testlauf auf Python 3.13 und 3.14 ohne Projekt-Deprecations; Browser-
Job wird separat und eindeutig berichtet.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P2-12 – Packaging/API-Versionen und URLs driften

**Umsetzungsstatus:** ✅ Mit Paket 21 abgeschlossen. `src/core/version.py`
ist über `setuptools.dynamic` die einzige Versionsquelle für Paketmetadaten;
FastAPI/OpenAPI, CLI, Web-/MQTT-Metadaten und OCI-Labels verwenden denselben
Wert. Das Console-Script `smarttub-mqtt` ist registriert, die Repository-URLs
zeigen auf das echte Remote, und der Release-Workflow prüft Tag und
Quellversion auf Gleichheit. (Luna)

**Befund:** FastAPI meldet Version `1.0.0`, Paket/Docker melden `0.3.3`, der
Fallback lautet `0.3.3-dev`. `pyproject.toml` enthält Platzhalter-URLs wie
`https://github.com/smarttub-mqtt`, während das echte Remote anders lautet.
Ein Console-Script fehlt.

**Umsetzung:** Version aus genau einer Quelle (SCM/Package-Metadata), bei App,
OCI-Labels und Release verwenden. Echte Repository-URLs setzen und
`smarttub-mqtt = "src.cli.run:main"` als Script definieren.

**Abnahme:** CLI, `/openapi.json`, UI, MQTT-Meta und Image-Label zeigen dieselbe
Version; alle Projektlinks funktionieren.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P2-13 – Release/Compose sind nicht konsistent und nur AMD64

**Umsetzungsstatus:** ✅ Mit Paket 20 abgeschlossen. Die Gitea-Registry ist
für Entwicklung und Releases kanonisch; CI verwendet `edge`, Releases nur
SemVer-Tags. Jeder Release ist ein signiertes AMD64-/ARM64-Manifest mit SBOM,
Provenance und in den Release-Notes ausgegebenem Digest. Compose nutzt eine
konkrete Release-Version derselben Registry und aktiviert die dokumentierte
Restart-Policy. (Terra)

**Befund:** Compose nutzt `willnix/smarttub-mqtt:latest`, Release publiziert in
eine Gitea-Registry, CI-Publish nur `latest`; Release baut ausschließlich
`linux/amd64`. `restart` ist auskommentiert. Das ist auf ARM-Systemen und für
Rollback/Reproduzierbarkeit problematisch.

**Umsetzung:** Registrystrategie vereinheitlichen, SemVer plus Digest verwenden,
Multi-Arch `linux/amd64,linux/arm64` bauen, SBOM/Provenance und Signatur erzeugen.
Compose-Beispiel auf eine konkrete Version pinnen und Restart-Policy erklären.

**Abnahme:** Beide Architekturen starten denselben signierten Release; Compose
zieht keine unbestimmte `latest`-Version.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P2-14 – Dokumentation/Changelog enthalten historische Drift

**Umsetzungsstatus:** ✅ Mit Paket 21 abgeschlossen. `CHANGELOG.md` enthält
alle Änderungen unter `[Unreleased]`, bewahrt historische Texte und ergänzt
Korrekturhinweise zu wiederhergestellten Tests/Dokumenten, aktuellen
Discovery-Pfaden und Safety-Variablen. Historische Links wurden auf das echte
Repository korrigiert; ein Pull-Request-Template macht Release Notes und
Dokumentationsprüfung nachvollziehbar. (Luna)

**Befund:** Changelog beschreibt entfernte Tests/Dokumente, obwohl sie wieder
vorhanden sind, nennt alte Dateipfade und widerspricht aktuellen Safety-Variablen.
Viele jüngste Commits heißen nur „Web UI optimiert“, was spätere Ursachenanalyse
erschwert.

**Umsetzung:** Changelog gegen Tags neu konsolidieren; historische Aussagen nicht
umschreiben, aber Korrekturhinweise ergänzen. Conventional Commits oder zumindest
fachlich konkrete Commit-Titel und Release-PR-Template verwenden.

**Abnahme:** Dokumentierte Pfade/Variablen existieren; Unreleased enthält alle
Änderungen seit 0.3.3; Release-Notes sind aus Commits nachvollziehbar.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

### P3 – Optimierungen und Pflege

#### P3-01 – Relative Web-Asset-Pfade sind vom Working Directory abhängig

**Umsetzungsstatus:** ✅ Mit Paket 10 abgeschlossen. Templates und Static-Dateien
werden relativ zum installierten Web-Paket aufgelöst; ein nach `/tmp`
installiertes Wheel wurde erfolgreich geprüft.

**Befund:** Templates und Static-Assets werden über `src/web/...` relativ zum
Prozessverzeichnis geladen. Ein installierter Wheel-Start aus einem anderen
Verzeichnis kann scheitern.

**Umsetzung:** Pfade relativ zu `Path(__file__)` oder über
`importlib.resources.files()` bestimmen.

**Abnahme:** Web-App startet nach Wheel-Installation aus `/tmp`.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P3-02 – Discovery-UI verwendet nachgebaute Radio-Cards

**Umsetzungsstatus:** ✅ Mit Paket 22 abgeschlossen. Die drei Modi verwenden
native Radio-Inputs mit gemeinsamem Namen und verknüpften Labels; Auswahl,
Fokus, Disabled- und Error-Zustände werden über Standard-HTML/CSS abgebildet.
Das JavaScript verwaltet keine eigene Tastatur-/ARIA-Radiologik mehr. (Luna)

**Befund:** `div role=radio` mit eigener Keyboard-/ARIA-Verwaltung ist komplexer
als native Inputs und erhöht das Accessibility-Risiko.

**Umsetzung:** Visuell gestylte native `<input type="radio">` mit `<label>`
verwenden; Fokus-, Disabled- und Error-Zustände testen.

**Abnahme:** Bedienung mit Tastatur und Screenreader funktioniert ohne eigenes
Radio-State-Management.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

#### P3-03 – Web-Updates pollen statt Ereignisse zu abonnieren

**Umsetzungsstatus:** ✅ Mit Paket 21 umgesetzt. Der authentifizierte SSE-
Endpunkt sendet State-, Command- und Discovery-Änderungen samt initialem
Snapshot; der Browser aktualisiert die betroffenen Ansichten sofort und
reconnectet begrenzt. Die bestehenden Poller bleiben absichtlich aktiv, falls
ein Proxy oder Browser keinen Stream bereitstellt. (Terra)

**Befund:** Übersicht, History und Discovery nutzen feste Pollintervalle; mehrere
Clients erzeugen wiederholte Requests, während Änderungen verzögert erscheinen.

**Umsetzung:** Server-Sent Events als einfacher unidirektionaler Kanal für State,
Discovery und Command-Result; Polling als Fallback behalten.

**Abnahme:** Änderungen erscheinen zeitnah; Verbindungsabbruch reconnectet mit
Backoff; Polling-Fallback bleibt funktionsfähig.\
**Empfohlenes Modell:** **GPT-5.6 Terra**.

#### P3-04 – Generierte Artefakte im Source-Verzeichnis

**Umsetzungsstatus:** ✅ Mit Paket 22 abgeschlossen. `quality-check.sh` legt
Ruff-, MyPy-, Pytest- und Coverage-Artefakte in einem temporären Verzeichnis
an; `clean.sh` entfernt nur explizit bekannte Build-, Egg-Info- und Python-
Cache-Pfade. `config/`, `logs/`, `.git/` und die virtuelle Umgebung werden
nicht traversiert oder gelöscht. (Luna)

**Befund:** Lokale `__pycache__`- und `src/smarttub_mqtt.egg-info`-Verzeichnisse
sind vorhanden (korrekt ignoriert), erschweren aber manuelle Größen-/Artefakt-
Analysen.

**Umsetzung:** Build/Test in isolierten Verzeichnissen ausführen und einen
`clean`-Task anbieten; keine pauschale automatische Löschung von Nutzerdateien.

**Abnahme:** Ein frischer Quality-Lauf hinterlässt den Source-Baum sauber.\
**Empfohlenes Modell:** **GPT-5.6 Luna**.

## 6. Optimiertes Ziel-Design

```text
                     ┌────────────────────────────┐
HTTP / MQTT input ──▶│ Command API + Validation   │
                     │ typed, shared domain rules │
                     └──────────────┬─────────────┘
                                    ▼
                     ┌────────────────────────────┐
                     │ Bounded Command Executor   │
                     │ timeout, result, audit ID  │
                     └──────────────┬─────────────┘
                                    ▼
                     ┌────────────────────────────┐
                     │ SmartTub Gateway           │
                     │ only upstream dependency   │
                     │ public API + compat layer  │
                     └──────────────┬─────────────┘
                                    ▼
                              SmartTub Cloud

SmartTub Cloud ─▶ State Reader ─▶ State Store ─┬─▶ MQTT encoder/publisher
                          live/stale/offline    ├─▶ Web API / SSE
                                               └─▶ Metrics / readiness

Discovery Trigger ─▶ Shared Discovery Engine ─▶ Recovery Journal/Repository
                  CLI | MQTT | HTTP              atomic, versioned, testable
```

### Empfohlene Paketstruktur

```text
src/smarttub_mqtt/
├── domain/
│   ├── commands.py          # typisierte Commands und Validierung
│   ├── state.py             # Snapshot + quality/availability
│   └── capabilities.py
├── application/
│   ├── command_executor.py  # bounded Queue, Timeout, Result
│   ├── state_service.py
│   └── discovery_service.py
├── adapters/
│   ├── smarttub_gateway.py  # einzige python-smarttub-Grenze
│   ├── mqtt/
│   ├── web/
│   └── persistence/
├── bootstrap.py             # Composition Root / Supervisor
└── cli.py
```

Die Umbenennung vom generischen Top-Level-Paket `src` in `smarttub_mqtt` sollte
als eigener, weitgehend mechanischer Schritt erfolgen, nachdem die P0-Fehler
abgesichert sind.

## 7. Optimiertes Web-Design

Die aktuelle Web-UI ist bereits verständlich und zugänglicher als die frühere
Version. Das nächste Design sollte vor allem **Vertrauen in den Zustand** und
**sichere Steuerung** verbessern:

1. Globale Statusleiste: `Cloud`, `MQTT`, `Datenalter`, `Befehls-Queue` getrennt
   statt eines allgemeinen „Datenverbindung aktiv“.
2. Jede Karte zeigt „live“, „vor X Sekunden“, „veraltet“ oder „nicht verfügbar“;
   unbekannte Werte niemals als aus darstellen.
3. Controls bei stale/offline deaktivieren oder eine bewusste Bestätigung
   verlangen.
4. Jeder Befehl zeigt die Zustände `queued → sent → verified` oder `failed` mit
   Correlation-ID; ein angenommener Erfolg reicht nicht.
5. Discovery erhält Dauerprognose, Warnung vor sichtbaren Lichtänderungen,
   Abbruch-/Restore-Status und Recovery-Hilfe.
6. Technische MQTT-Topics bleiben in einem einklappbaren Diagnosebereich;
   normale Nutzer sehen Begriffe des Whirlpools.
7. Responsive Karten nach Wichtigkeit sortieren: Wasser/Zieltemperatur,
   Availability, Heizung, Pumpen, Licht, technische Details.
8. SSE liefert Live-Updates; Polling bleibt als robuster Fallback.

**Umsetzung des Gesamtentwurfs:** **GPT-5.6 Sol** für State-/Command-Semantik;
**Terra** für SSE und UI-Flows; **Luna** für einzelne Accessibility-/CSS-Punkte.

## 8. Sinnvolle neue Funktionen

| Priorität | Funktion | Nutzen / grobe Umsetzung | Modell |
| --- | --- | --- | --- |
| N1 | Home-Assistant MQTT Discovery | Geräte und Entities automatisch anlegen; Availability, Device-Class und Unique IDs korrekt publizieren | Terra |
| N2 | OpenMetrics/Prometheus | Verbindungsstatus, Snapshot-Alter, API-Latenz, 429er, Queue-Länge, Command-Erfolg und Reconnects | Terra |
| N3 | Command-Acknowledgement-Topics | `<command_id>/result` mit `accepted`, `sent`, `confirmed`, `failed` oder `unknown`; niemals eine nicht beobachtbare physische Wirkung behaupten | Sol |
| N4 | 429-aware Rate Limiter | Login-/API-Budget, Retry-After, Jitter und Circuit Breaker passend zum offenen Upstream-Problem | Sol |
| N5 | Diagnosepaket mit Redaction | Versionen, Capability, letzte Fehler, anonymisierte API-Form und Config ohne Secrets exportieren | Terra |
| N6 | Dry-run/Read-only-Modus | UI/Discovery sichtbar, aber keine Schreibbefehle; ideal für Erstinstallation und Debugging | Terra |
| N7 | Config-Schema und Migration | Konfiguration prüfen, alte Variablen melden und sichere Migration anbieten | Terra |
| N8 | Backup/Restore für Discovery | Versionierte, atomare Backups und UI-Import/Export für `discovered_items.yaml` | Terra |
| N9 | Zweistufenpumpen | LOW/HIGH gezielt abbilden und – sobald Upstream/Hardware es erlaubt – steuern | Sol |
| N10 | Event-basierte Web-Updates | SSE für State, Discovery und Commands; weniger Polling und schnellere Rückmeldung | Terra |
| N11 | Mehrsprachigkeit | Deutsche/englische UI über zentrale Übersetzungskataloge statt Text in Templates/JS | Terra |
| N12 | Support-Matrix | Anonymisierte Fixtures nach Marke/Modell/Firmware; getestete Capabilities dokumentieren | Sol |

Nicht als erste neue Funktion empfohlen: mehrere Whirlpools in einem Prozess.
Die aktuelle „eine Instanz = ein Whirlpool“-Grenze vereinfacht Routing, Safety,
Availability und Deployment erheblich. Multi-Spa sollte erst nach Stabilisierung
der State-/Command-Domain geprüft werden.

## 9. Empfohlene Umsetzungsreihenfolge

### Phase A – Korrektheit und Sicherheit

1. P0-01 bis P0-08 mit Regressionstests.
2. Sichere Web-Defaults und echte Command-Fehlerantworten.
3. Fake-Fallback durch live/stale/offline ersetzen.
4. Release `0.3.4` als reines Stabilitätsrelease.

### Phase B – Resilienz

1. Bounded Queues und Command-Acknowledgements.
2. Readiness/Liveness und degradierter Startup.
3. 429-aware Backoff sowie MQTT-Reconnect-/Drain-Semantik.
4. Coverage mindestens auf 65 % mit Fokus auf Controller/Discovery.

### Phase C – Architektur

1. Zentraler SmartTub-Gateway.
2. Gemeinsame Discovery-Engine und atomisches Repository.
3. Deklarative Konfiguration und typisierte Domainmodelle.
4. TopicMapper und StateManager verkleinern.

### Phase D – Produktqualität

1. Reproduzierbare Wheel-/Multi-Arch-Images, SBOM und signierte Releases.
2. SSE, Command-Status und überarbeitete Statusleiste.
3. Home-Assistant Discovery, Metrics und Diagnoseexport.

## 10. Prüfprotokoll dieser Analyse

### Aktueller Prüfstand nach den Luna-Paketen (23.08.2026)

| Prüfung | Ergebnis |
| --- | --- |
| Pytest ohne optionalen Browser-Smoke | **279 bestanden**, ohne Deprecation-Warnung |
| Statement-Coverage / CI-Gate | **70,33 % / 65 %**, bestanden |
| Wheel-Build außerhalb Repository | bestanden; Templates und Static Assets enthalten |
| Docker-Build | lokal nicht ausführbar (`docker` nicht installiert); CI-Job vorhanden |
| Ruff Check / Format | bestanden, 109 geprüfte Python-Dateien; `BLE001`/`S110` aktiv, Config und Discovery ohne C901-Verstoß |
| MyPy `src` | bestanden, 64 Source-Dateien; untypisierte Körper werden global geprüft, 24 Module zusätzlich strikt |
| Python `compileall` | bestanden |
| JavaScript `node --check` | bestanden |
| `pip check` | keine defekten Requirements |
| `git diff --check` | bestanden |

Der folgende ursprüngliche Analyse-Prüfstand bleibt zur Nachvollziehbarkeit des
Ausgangszustands erhalten:

| Prüfung | Ergebnis |
| --- | --- |
| `git status` vor Analyse | sauber (`main...gitea/main`) |
| `ruff check .` | bestanden |
| `ruff format --check .` | bestanden, 75 Dateien formatiert |
| MyPy aktueller Projektbefehl | bestanden; Hinweise auf untypisierte Funktionskörper |
| Pytest vollständig | 78 bestanden, 1 Browser-Setup-Fehler, 2 Warnungen |
| Pytest ohne Browser-Smoke | 78 bestanden |
| Coverage ohne Browser-Smoke | 45 % |
| Bandit | 15 Befunde: 3 Medium (B104), 12 Low (B110), keine High |
| Erweiterte Ruff-Komplexitätsprüfung | 52 Befunde |
| `pip check` | keine defekten installierten Requirements |
| Wheel-Prüfung | lokal nicht abschließbar: Build-Backend in der bestehenden Venv nicht importierbar; Docker-CI baut separat |
| Upstream-Stand | `v0.0.48` ist aktueller Tag; Projekt verwendet ihn bereits |

Der Browserfehler entstand beim Start des Chromium Headless Shells durch eine
macOS-Sandbox-Berechtigung (`MachPortRendezvousServer: Permission denied`). Er
belegt keinen Defekt der Web-Anwendung, sollte aber als separater Browser-CI-Job
sichtbar bleiben.

## 11. Festgelegte Produktanforderungen und verbleibende Fragen

### Festgelegt

1. **Netzwerkgrenze:** Die Web-UI läuft ausschließlich im gesicherten Heimnetz.
   Direkter Internetzugriff ist kein unterstützter Standardfall; für Fernzugriff
   werden VPN oder ein authentifizierender HTTPS-Reverse-Proxy dokumentiert.
2. **Befehlsrückmeldung:** Das System muss unterscheiden zwischen:
   - `accepted`: lokal validiert und in die Queue aufgenommen;
   - `sent`: SmartTub-API-Aufruf ohne gemeldeten Fehler abgeschlossen;
   - `confirmed`: ein anschließender API-Read zeigt den erwarteten Zustandswechsel;
   - `failed`: Validierung, Transport, Cloud-API oder bestätigender Read meldet
     einen Fehler;
   - `unknown`: Cloud-Aufruf wurde gesendet, aber eine Bestätigung ist technisch
     nicht möglich oder nicht eindeutig.

   `confirmed` bedeutet nur „durch die SmartTub-API anschließend so beobachtet“
   und ist keine Garantie, dass der physische Aktor tatsächlich reagiert hat.
   Ein bloßes Ausbleiben einer Exception darf nicht pauschal als bestätigter
   Hardwareerfolg dargestellt werden.
3. **Geräteunterstützung:** Das GitHub-Projekt bleibt modell- und markenflexibel.
   Capabilities werden dynamisch erkannt; unbekannte Gerätewerte werden erhalten
   und nicht durch Jacuzzi-/Modell-spezifische Annahmen ersetzt. Modellwissen
   gehört in optionale Profile oder anonymisierte Contract-Fixtures, nicht in den
   generischen Kern.
4. **MQTT-Ausfallstrategie:** Retained Werte werden pro Topic koalesziert und
   nach Reconnect erneut publiziert; Command-Ergebnisse werden in einer
   begrenzten FIFO gepuffert. Queue-Größen, Drops und Drain sind sichtbar.

### Noch zu entscheiden

1. Ist OpenHAB weiterhin das primäre Ziel, oder sollen Home Assistant und andere
   MQTT-Consumer gleichwertig unterstützt werden?
2. Welche Registry ist die kanonische Quelle: Docker Hub, die private Gitea-
   Registry oder beide?

Die frühere Discovery-Entscheidung ist geklärt: Der CLI-Prober wurde nach dem
Strangler-Prinzip auf die gemeinsame Engine migriert; sein bisheriger Export
bleibt vorläufig als Adapter erhalten. Für Zweistufenpumpen liegt auf dem
vorhandenen Gerät keine reale Referenz vor; eine anonymisierte Community-Fixture
bleibt daher willkommen, ist aber kein Blocker für die generische Abbildung.

## 12. Recap

Das Projekt hat eine gute funktionale Basis und sichtbar investierte Arbeit in
Dokumentation, UI, Typisierung und MQTT-Reconnects. Der größte Hebel ist jetzt
nicht eine weitere Funktion, sondern **ehrliche Zustands- und Fehlersemantik**:
Ein unbekannter Zustand darf nicht „aus“ heißen, und ein fehlgeschlagener Befehl
darf nicht „success“ werden. Sobald diese Grundlage mit Tests abgesichert ist,
können Discovery, Konfiguration und Upstream-Adapter kontrolliert zerlegt werden.
Danach ist das Projekt gut positioniert für Home-Assistant-Discovery, Metrics,
Multi-Arch-Releases und eine deutlich professionellere Live-UI.

**Stand nach Umsetzung:** Die zuvor größten Risiken – falsche Command-Erfolge,
Fake-Zustände, LOW-Pumpenfehler, unbeschränkte Queues, initial harter
Dependency-Ausfall und verstreute Low-Level-Upstream-Aufrufe – sind behoben und
regressionsgetestet. Die Discovery-Implementierungen nutzen inzwischen eine
gemeinsame recovery-sichere Engine. Das zweite Coverage-Gate ist mit 70,33 %
Ist-Stand und 65 % Mindestschwelle aktiv. Für die letzte geplante 75-%-Ratsche
sind vor allem StateManager, CLI/Entrypoint, Fehlerdiagnose und die verbleibenden
Discovery-Orchestrierungspfade relevant. P2-04 und P2-05 sind mit dem atomaren,
eventloop-sicheren Discovery-Repository sowie den reinen Topic-Encodern und dem
separaten Publisher abgeschlossen. Der StateManager besitzt inzwischen ebenfalls
nur noch das festgelegte Vollsnapshot-Modell. P2-09 schützt Command-/Audit-
Payloadgrenzen, korreliert Statuslogs und erzwingt nun auch für Standard-
Logging und externe Tracebacks eine zentrale sichere JSON-Ausgabegrenze. (Terra)
