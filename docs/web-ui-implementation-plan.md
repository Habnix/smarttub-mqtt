# Abarbeitungsplan: Web-UI-Verbesserungen

Dieser Plan basiert auf der UI-Analyse vom 22.08.2026. Die Punkte werden in
kleinen, überprüfbaren Schritten umgesetzt. Bereits vorhandene Änderungen im
Arbeitsbaum bleiben erhalten.

## 1. Statuswerte und Datenqualität

- [x] Fehlende Temperatur- und Zielwerte als `—` bzw. „Nicht verfügbar“ statt
      als `0,0 °C` darstellen.
- [x] Whirlpool-Verbindung und Whirlpool-Betriebsstatus getrennt ausweisen.
- [x] `INIT`, `unknown` und weitere Rohwerte in verständliche Statuslabels und
      eindeutige Statusklassen übersetzen.
- [x] Veraltete Daten neben dem Hinweis auch in den betroffenen Karten sichtbar
      machen.

## 2. Sprache und Fachbegriffe

- [x] Sichtbare englische Begriffe in der Übersicht vollständig lokalisieren.
- [x] Rohwerte wie `running`, `ONE_SPEED` und `INIT` nutzerfreundlich darstellen.
- [x] Bezeichnungen für Pumpen, Lichtzonen und Betriebsmodi vereinheitlichen.

## 3. Accessibility und visuelle Verständlichkeit

- [x] Überschriftenhierarchie in Übersicht und Steuerung korrigieren.
- [x] Aktive Navigation mit `aria-current="page"` auszeichnen.
- [x] Status- und Helligkeitsanzeigen in der Übersicht mit geeigneten ARIA-Werten versehen.
- [x] Farbkontraste der betroffenen Info-Header verbessern.
- [x] Zustände nicht ausschließlich über Farbe oder Symbole vermitteln.

## 4. Dashboard und Navigation

- [x] Technische Discovery-Hinweise aus den normalen Komponenten-Karten in
      einen Detailbereich oder die Discovery-Seite verschieben.
- [x] Statusübersicht und technische Metadaten in der Navigation klarer trennen.
- [x] Übersicht auf die wichtigsten Betriebsdaten fokussieren (technische Details
      sind einklappbar und die Heizungskarte stellt die Zieltemperatur klarer heraus).

## 5. Steuerung und Befehlsverlauf

- [x] Aktuellen Zustand und Datenalter auf der Steuerungsseite sichtbar machen.
- [x] Kritische oder potenziell unerwartete Aktionen verständlicher absichern.
- [x] Interne MQTT-Topic-Namen im Befehlsverlauf in nutzerfreundliche Texte
      übersetzen; technische Details optional ausklappbar lassen.

## 6. Robustheit und Wartbarkeit

- [x] Bootstrap-Abhängigkeit lokal oder mit Integritätsprüfung absichern.
- [x] Wiederholte Inline-Styles in gemeinsame CSS-Klassen überführen.
- [x] Fehler- und Ladezustände für API-Aktualisierungen sichtbar machen.

## 7. Verifikation

- [x] Bestehende Web-Router- und Browser-Smoke-Tests ausführen: `66 passed` im
      vollständigen Lauf und `1 passed` im Browser-Smoke-Test.
- [x] Desktop- und Mobile-Darstellung erneut prüfen.
- [x] Browser-Konsole auf Fehler und Warnungen prüfen.
- [x] Änderungen und verbleibende Risiken dokumentieren.

## Umsetzungsstand

Der erste Umsetzungsschritt ist begonnen: Übersicht, gemeinsame Karten- und
Navigationsbausteine sowie die betroffenen Statusaktualisierungen wurden
angepasst. Jinja-Templates, JavaScript-Syntax und ein repräsentatives
Übersichts-Rendering wurden lokal geprüft. Die laufende Testinstanz
verwendet weiterhin ihre bereits deployte Version; sie
lädt Änderungen im Arbeitsverzeichnis nicht automatisch.

Die zweite Runde ergänzt die sichtbare Veraltet-Markierung, gruppiert die
Navigations-Metadaten, lokalisiert weitere Steuerungsmodi und macht die
Discovery-Statusänderungen für Screenreader ankündigbar.

Zusätzlich werden Pumpen- und Lichtzonennamen über gemeinsame Template-Makros
lokalisiert und in Übersicht sowie Steuerung identisch dargestellt. Die
Bezeichnungen sind durch einen Router-Regressionstest abgesichert.

Die dritte Runde verschiebt die wiederverwendbaren UI-Regeln in die zentrale
`app.css` und reduziert damit die page-spezifischen Inline-Styles.

Die Testumgebung der Projekt-Virtualenv ist inzwischen bestätigt: Der komplette
Testlauf besteht mit 66 Tests; der Browser-Smoke-Test besteht mit 1 Test. Es
bleibt eine Deprecation-Warnung aus Starlette/httpx. Für den Chromium-Start war
eine Ausführung außerhalb der Sandbox erforderlich.

Ein nachträglich aufgedeckter Datenfehler wurde behoben: `Number(null)` machte
aus einem fehlenden Außentemperaturwert `0,0 °C`. `ui.js` behandelt fehlende
Temperaturen jetzt vor der numerischen Umwandlung als `—`.

Bootstrap 5.3.0 wird inzwischen als versioniertes CSS-Asset lokal ausgeliefert;
die Web-UI benötigt kein Bootstrap-JavaScript.
