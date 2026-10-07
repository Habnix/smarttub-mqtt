# Veröffentlichung auf GitHub und Docker Hub

## Private Tests und öffentliche Releases

Dasselbe Repository verwendet zwei voneinander getrennte Veröffentlichungswege:

| Auslöser | Prüfungen und Ergebnis |
| --- | --- |
| Push auf Gitea `main` | Vollständige CI, anschließend privates Image `${GITEA_IMAGE}:edge` |
| Push auf GitHub `main` / Pull Request | Vollständige CI ohne Image-Veröffentlichung |
| GitHub-Tag `vX.Y.Z` | Vorprüfung, vollständige CI auf dem Tag, signiertes AMD64-/ARM64-Image auf Docker Hub und GitHub-Release |

Gitea erhält keine Docker-Hub-Zugangsdaten. Der öffentliche Release-Workflow
läuft ausschließlich auf GitHub. Ein manueller Start benötigt einen ausgewählten
Release-Tag; ein Start auf einem Branch wird abgewiesen.

## Einmalige Einrichtung auf GitHub

### Lokale GitHub-Anmeldung

Auf dem Mac bietet sich GitHub CLI mit HTTPS und Browser-Anmeldung an:

```bash
brew install gh
gh auth login --hostname github.com --git-protocol https --web --scopes workflow
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

Im Browser mit dem Konto anmelden, das Schreibrecht für
`Habnix/smarttub-mqtt` besitzt. Der zusätzliche Scope `workflow` wird für
Änderungen an GitHub-Actions-Workflows benötigt. Die Anmeldung verwendet
normalerweise den System-Schlüsselbund; `gh auth status` zeigt den Speicherort.
Keine Option `--insecure-storage` verwenden und keine Tokens in Chat oder Git
kopieren. Die Konfiguration ist ausdrücklich auf `github.com` beschränkt.

Die Git-Autorenangaben sind unabhängig von dieser Anmeldung. Für künftige
Commits die persönliche `noreply`-Adresse aus
[GitHub Settings → Emails](https://github.com/settings/emails) übernehmen:

```bash
git config --local user.name 'Habnix'
git config --local user.email '<eigene-noreply-Adresse-aus-GitHub>'
```

Dies verändert vorhandene Commits nicht. Vor dem ersten öffentlichen Push
auch die Autoren- und Committer-Adressen der noch unveröffentlichten Historie
prüfen. Bereits auf Gitea vorhandene Historie nicht ungeprüft umschreiben.

### Secrets für die Veröffentlichung

Im Repository unter **Settings → Secrets and variables → Actions** werden
folgende Repository-Secrets benötigt:

| Secret | Inhalt |
| --- | --- |
| `DOCKERHUB_USERNAME` | `willnix`, bzw. ein Benutzer mit Schreibrecht für `willnix/smarttub-mqtt` |
| `DOCKERHUB_TOKEN` | Docker-Hub-Personal-Access-Token mit Read/Write-Recht |
| `COSIGN_PRIVATE_KEY` | Vollständiger Inhalt eines Cosign-Schlüssels, einschließlich Kopf- und Fußzeile |
| `COSIGN_PASSWORD` | Passwort dieses Schlüssels; bei einem unverschlüsselten Schlüssel leer |

Tokens und private Schlüssel ausschließlich in Secrets speichern, niemals in
Git oder in Chat-Nachrichten. Die Gitea-Secrets `REGISTRY_USERNAME` und
`REGISTRY_TOKEN` bleiben dort für die privaten Builds.

Falls noch kein Cosign-Schlüssel existiert, auf einem vertrauenswürdigen Rechner
mit installiertem Cosign `cosign generate-key-pair` außerhalb des Repositorys
ausführen. Den privaten Schlüssel sicher sichern; `cosign.pub` ist öffentlich.
Der Workflow prüft das Entschlüsseln des Schlüssels vor dem Image-Push und hängt
den öffentlichen Schlüssel an das GitHub-Release an.

GitHub Actions muss für das Repository aktiviert sein. Das Image-Repository
`willnix/smarttub-mqtt` muss auf Docker Hub existieren. Das automatisch bereitgestellte
`GITHUB_TOKEN` erhält im Release-Job `contents: write`; dafür ist kein separates
GitHub-PAT nötig.

## Release vorbereiten

1. Neue Version in `src/core/version.py` setzen.
2. Version in `docker-compose.yml`, `docker-compose.local.yml` und den aktuellen
   Beispielen in README und `docs/dockerhub.md` anpassen.
3. Änderungen aus `[Unreleased]` in einen datierten Abschnitt `[X.Y.Z]` im
   Changelog verschieben und den Release-Link ergänzen. `[Unreleased]` bleibt
   für nachfolgende Änderungen bestehen. Die aktuelle Vorbereitung gilt 0.4.0.
4. Lokale Prüfungen ausführen:

   ```bash
   ./scripts/quality-check.sh
   ./scripts/security-check.sh
   ```

   Eine kaputte lokale `.venv` zuerst reparieren oder eine separate Python-3.13+
   Testumgebung verwenden. Die Scripts verwenden eine funktionierende `.venv`
   bevorzugt; andernfalls kann `PYTHON=/pfad/zum/python` gesetzt werden.

## Erst privat prüfen

Vor dem Übernehmen dieser öffentlichen Workflow-Version in Gitea die
Repository-Variablen konfigurieren:

| Gitea-Variable | Inhalt |
| --- | --- |
| `GITEA_REGISTRY` | Registry-Host ohne Protokoll, beispielsweise `registry.example.com` |
| `GITEA_IMAGE` | Vollständiger Image-Pfad ohne Tag, beispielsweise `registry.example.com/namespace/smarttub-mqtt` |

Die Anmeldung verwendet weiterhin die Gitea-Secrets `REGISTRY_USERNAME` und
`REGISTRY_TOKEN`. Private Hosts und Accountnamen ausschließlich in der
Gitea-Konfiguration und lokalen, ignorierten Dateien speichern.

```bash
git push gitea main
```

Gitea-CI einschließlich Browser-, Docker- und Security-Jobs erfolgreich abwarten.
Für den privaten Testhost `SMARTTUB_PRIVATE_IMAGE` in der ignorierten
`config/.env` auf den eigenen vollständigen Image-Pfad mit Tag `edge` setzen.
Compose muss diese Datei auch für die Image-Interpolation lesen:

```bash
docker compose --env-file config/.env -f docker-compose.yml -f docker-compose.gitea.yml pull
docker compose --env-file config/.env -f docker-compose.yml -f docker-compose.gitea.yml up -d
```

Konfiguration vorher sichern. Status, MQTT-Publishing, Web-Steuerung und
Discovery-Ergebnisse am Testgerät prüfen. Hardwareändernde Tests bewusst
starten. Ein vorhandener Container aktualisiert sich nicht allein durch einen
Git-Push oder einen Registry-Build.

## GitHub aktualisieren und Release starten

Vor dem öffentlichen Push sowohl den aktuellen Dateistand als auch alle seit
`origin/main` hinzugekommenen Commits auf Zugangsdaten und persönliche Angaben
prüfen. Der Baseline-Scan in `scripts/security-check.sh` prüft den aktuellen
Dateistand, nicht die vollständige Git-Historie. `.env`, Logs, private Schlüssel,
reale Geräte-IDs und private Accountnamen gehören nicht in öffentliche Beispiele.
Die öffentlichen Projekt-Namensräume `Habnix` und `willnix` sind dagegen Teil
der GitHub- und Docker-Hub-Adressen. Private Registry-Adressen in versionierten
Workflows werden beim Push ebenfalls öffentlich sichtbar.

Bei getrennten privaten und öffentlichen Historien den geprüften öffentlichen
Branch verwenden. Der erstmalige Import von 0.4.0 verwendet
`codex/public-release-0.4.0`, der direkt auf dem bisherigen GitHub-`main`
aufbaut. Er enthält einen bereinigten Commit mit noreply-Autorenadresse.
Die privaten Gitea-Commits werden nicht übertragen; bereits vorhandene
öffentliche Historie bleibt bestehen. Kein Force-Push ist erforderlich.

Aus dessen Arbeitsverzeichnis nach abgeschlossener Prüfung:

```bash
git push origin HEAD:main
```

GitHub-CI für genau diesen Commit erfolgreich abwarten und die erforderlichen
Secrets prüfen. Für GitHub immer ausdrücklich `origin` angeben. Nicht den
privaten Gitea-Branch versehentlich nach GitHub pushen.

Erst danach einen neuen, bislang unbenutzten Tag erstellen und pushen:

```bash
git tag -a v0.4.0 -m 'Release 0.4.0'
git push origin v0.4.0
```

Bereits veröffentlichte Tags oder Versionsimages nicht für neue Inhalte
wiederverwenden. Kein pauschales `git push --tags`: Es könnte weitere lokale
Tags unbeabsichtigt veröffentlichen.

Der Release-Workflow prüft Secrets und Tag-Version, führt denselben vollständigen
CI-Workflow auf dem Tag erneut aus und baut danach für AMD64 und ARM64. Die
Tags `0.4.0`, `0.4` und `latest` werden veröffentlicht. Installationen sollten
die vollständige Version oder den Digest verwenden.

## Ergebnis prüfen

- GitHub-Release-Workflow vollständig erfolgreich, einschließlich Signatur und
  Release-Erstellung.
- Auf Docker Hub existieren der neue Versionstag und beide Plattformen.
- `docker buildx imagetools inspect willnix/smarttub-mqtt:0.4.0` zeigt AMD64 und
  ARM64. Zusätzliche `unknown/unknown`-Einträge können Attestierungen sein.
- Ein frischer Pull startet mit der gesicherten Testkonfiguration; `/live` und
  `/ready` sowie die Web-UI und MQTT-Daten prüfen.
- Die Signatur mit dem aus vertrauenswürdiger Quelle bezogenen `cosign.pub` und
  dem Digest aus den Release-Notes prüfen:

  ```bash
  cosign verify --key cosign.pub willnix/smarttub-mqtt@sha256:<release-digest>
  ```

Wenn Signieren oder Release-Erstellung nach dem Image-Push fehlschlägt, kann
bereits ein Image auf Docker Hub vorhanden sein. Dann den Workflow-Fehler
untersuchen und die Veröffentlichung abschließen, bevor Nutzer zum Upgrade
aufgefordert werden. `latest` kann zu diesem Zeitpunkt bereits verschoben sein.

## Docker-Hub-Dokumentation veröffentlichen

`docs/dockerhub.md` ist die gepflegte englische Beschreibung für Container-Nutzer.
Nach erfolgreichem Release auf Docker Hub **willnix/smarttub-mqtt → Overview /
Beschreibung bearbeiten** öffnen und den Markdown-Inhalt dieser Datei einfügen.
Als Kurzbeschreibung eignet sich:

> MQTT bridge for SmartTub hot tubs with a Web UI, discovery and Docker support.

Die Dokumentation wird bewusst separat von der Image-Veröffentlichung gepflegt;
ein Image-Push ändert die Docker-Hub-Beschreibung nicht. Für das Kopieren über die
Web-Oberfläche sind keine zusätzlichen CI-Secrets nötig.

## Rollback

Vorherige Imageversion oder vorherigen Digest wieder in Compose setzen. Bei
geänderten Discovery-Dateien die vor dem Upgrade gesicherte Konfiguration
zurückspielen. Danach `docker compose pull` und `docker compose up -d` ausführen.
Der alte 0.3.3-Container ist nur für AMD64 veröffentlicht.

## Referenzen

- [GitHub-CLI-Anmeldung](https://cli.github.com/manual/gh_auth_login)
- [Git-Autoren-E-Mail](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)
- [Private Sicherheitsmeldungen](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)
- [Docker-Hub-Tokens](https://docs.docker.com/security/access-tokens/personal-access-tokens/)
- [Multi-Plattform-Builds](https://docs.docker.com/build/ci/github-actions/multi-platform/)
- [Wiederverwendbare GitHub-Workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
