# Upgrade auf python-smarttub 0.46

## Datum: 2026-02-01

## Änderungen

### 1. python-smarttub Update auf Version 0.46

**Was hat sich geändert:**
- Authentifizierung von Auth0 auf SmartTub IDP migriert
- Neuer Endpoint: `https://api.smarttub.io/idp/signin`
- Token-Format geändert: Tokens sind jetzt in `{"token": {...}}` gewrappt
- Account-ID wird aus `custom:account_id` Claim im ID-Token extrahiert
- Keine Refresh-Token mehr - Re-Authentifizierung bei Token-Ablauf (24h)
- `jwt` Dependency entfernt

**Erforderliche Änderungen in smarttub-mqtt:**
- ✅ `pyproject.toml`: Dependency von `python-smarttub>=0.0.40` auf `python-smarttub>=0.0.46` aktualisiert
- ✅ Keine Code-Änderungen erforderlich (alle Änderungen sind in der Bibliothek gekapselt)

**Referenz:**
- GitHub PR: https://github.com/mdz/python-smarttub/pull/66
- Release: https://github.com/mdz/python-smarttub/releases/tag/v0.0.46

### 2. Fix für Logging-Fehler: OSError [Errno 9] Bad file descriptor

**Problem:**
```
--- Logging error ---
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/logging/handlers.py", line 73, in emit
    if self.shouldRollover(record):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/logging/handlers.py", line 197, in shouldRollover
    self.stream.seek(0, 2)  #due to non-posix-compliant Windows feature
    ^^^^^^^^^^^^^^^^^^^^^^
OSError: [Errno 9] Bad file descriptor
```

**Ursache:**
In Docker/Multi-Threading Umgebungen kann der File-Descriptor des Log-Streams ungültig werden, während `shouldRollover()` versucht, die Dateigröße zu prüfen.

**Lösung:**
- ✅ `src/core/log_rotation.py`: `shouldRollover()` Methode überschrieben mit Error-Handling
- ✅ Try-Catch für `OSError` und `ValueError` hinzugefügt
- ✅ Bei ungültigem File-Descriptor wird automatisch ein Rollover erzwungen
- ✅ `doRollover()` schließt Stream nun mit Error-Handling

**Details:**
Die neue `shouldRollover()` Methode:
1. Prüft ob Stream `None` ist und öffnet ihn bei Bedarf
2. Versucht `seek()` mit try-catch Schutz
3. Bei OSError/ValueError: Loggt Warnung nach stderr und erzwingt Rollover
4. Dadurch Recovery aus ungültigem Zustand

## Installation & Deployment

### Lokale Entwicklung:
```bash
pip install -e .
# oder mit uv:
uv sync
```

### Docker:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Verifizierung:
1. Prüfen ob Container startet ohne Auth-Fehler
2. Logs auf "Bad file descriptor" Fehler prüfen (sollten verschwunden sein)
3. Version prüfen in den Logs bei Start

## Breaking Changes

**Keine Breaking Changes** - Die Authentifizierung ist transparent in der `python-smarttub` Bibliothek implementiert.

Bestehende Konfigurationen mit `SMARTTUB_EMAIL` und `SMARTTUB_PASSWORD` funktionieren weiterhin ohne Änderungen.

## Testing

Nach dem Upgrade testen:
- [ ] Erfolgreiche Anmeldung bei SmartTub
- [ ] Spa-Daten werden korrekt abgerufen
- [ ] MQTT-Nachrichten werden publiziert
- [ ] Keine "Bad file descriptor" Fehler in Logs
- [ ] Log-Rotation funktioniert korrekt
- [ ] WebUI ist erreichbar und zeigt Daten

## Rollback

Falls Probleme auftreten:
```bash
# In pyproject.toml zurücksetzen:
"python-smarttub>=0.0.40"

# Rebuild:
docker-compose build --no-cache
docker-compose up -d
```

## Autor
GitHub Copilot - 2026-02-01
