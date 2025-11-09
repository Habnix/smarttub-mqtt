# Release Checklist - Light Mode Discovery Optimization

**Version:** v1.x.x (Light Discovery Update)  
**Datum:** 8. November 2025

## Phase 1: Pragmatische Discovery-Verbesserungen

### 1. Code-Implementierung
- [x] Adaptive Timeouts für Dynamic Modes (12s statt 5s, 10 retries)
- [x] Zone-Isolation (15s Pause + alle Zonen OFF zwischen Tests)
- [x] Verbesserte Logging-Ausgaben (✓/✗ Symbole für Erfolg/Fehler)
- [ ] Manuelle Config Support (manual_light_modes.yaml) - Optional für später

### 2. Basis-Test mit echtem Pool
- [ ] Discovery-Test durchführen (beide Zonen)
- [ ] Ergebnisse validieren: LOW_SPEED_WHEEL in Zone 1 erkannt?
- [ ] Ergebnisse validieren: Alle bekannten Modi in Zone 2 erkannt?
- [ ] Stabilität prüfen: 2-3 Testläufe mit konsistenten Ergebnissen?

### 3. Code-Cleanup
- [ ] Alte/tote Code-Pfade entfernen
- [ ] Unnötige Debug-Logs entfernen oder auf DEBUG-Level setzen
- [ ] Kommentare aktualisieren
- [ ] TODOs/FIXMEs durchgehen

### 4. Test-Files prüfen
- [ ] `tests/test_light_modes.py` - noch relevant?
- [ ] Alte Test-Scripts im Repo - aufräumen
- [ ] Integration Tests laufen durch?

### 5. Dokumentation aktualisieren
- [ ] `README.md` - Discovery-Beschreibung aktualisieren
- [ ] `CHANGELOG.md` - neue Features dokumentieren
- [ ] `docs/configuration.md` - manual_light_modes.yaml erklären
- [ ] `docs/troubleshooting.md` - Discovery-Probleme & Lösungen

### 6. GitHub & Docker Release
- [ ] Code auf GitHub pushen
- [ ] Tag erstellen (z.B. `v1.5.0`)
- [ ] Release Notes schreiben
- [ ] Docker Image bauen
- [ ] Docker Image auf Docker Hub pushen
- [ ] GitHub Release erstellen

---

## Status-Tracking

### ✅ Abgeschlossen
- Analyse der Discovery-Probleme
- Timing-Profile definiert
- Basis-Implementierung vorbereitet

### 🔄 In Arbeit
- Pragmatische Implementierung

### ⏳ Ausstehend
- Testing
- Cleanup
- Dokumentation
- Release

---

## Notizen

- **Hauptproblem:** LOW_SPEED_WHEEL nicht stabil erkannt in Zone 1
- **Lösung:** Längere Timeouts für Dynamic Modes + Zone-Isolation
- **Ziel:** 95%+ Erkennungsrate bei wiederholten Tests

### Technische Details der Implementierung:

**Adaptive Timeouts (`_test_light_mode`):**
```python
# Dynamic modes (WHEEL, RGB):
initial_wait = 12s
max_retries = 10
retry_delay = 3s
→ Max wait: 12s + (10 × 3s) = 42s per test

# Static modes (Colors, OFF):
initial_wait = 5s
max_retries = 5
retry_delay = 2s  
→ Max wait: 5s + (5 × 2s) = 15s per test
```

**Zone-Isolation:**
```python
# Before all tests:
- Turn OFF all zones
- Wait 15s

# Between zones:
- Turn OFF current zone
- Wait 15s before next zone
```

**Geschätzte Test-Dauer:**
- Phase 1: ~21 Modi × 15-42s (avg ~25s) = ~9 Min/Zone
- Phase 2: ~4 Modi × 2 Brightness × 15s = ~2 Min/Zone
- Zone-Isolation: 15s × 2 = 30s
- **Total: ~22 Min für beide Zonen**

**Datei-Änderungen:**
- `src/core/item_prober.py`: 3 Funktionen modifiziert (~80 Zeilen geändert)
