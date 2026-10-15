# HmWz

**HmWz** ist ein modularer Discord-Bot zur Verwaltung von WZ-Anmeldungen für das Spiel **Hadestar**. Er veröffentlicht pro Server eine interaktive Registrierungsübersicht, vergibt die dazugehörigen Discord-Rollen und hält Registrierungen und Einstellungen in einer lokalen SQLite-Datenbank fest.

Diese README beschreibt den aktuellen Projektstand, die Einrichtung auf einem Discord-Server, alle verfügbaren Befehle sowie Installation und Betrieb.

![Beispiel einer Bot-Übersicht](assets/registration.png)

## Funktionen

- Interaktive Anmeldung und Abmeldung über Schaltflächen in einer Serverübersicht.
- Serverbezogene Registrierungsrollen; Rollen können als permanent markiert werden.
- Verwaltung der Anmeldungsnachricht und der für einen Reset zusätzlich zu bereinigenden Textkanäle.
- CSV-Export und Zurücksetzen nicht permanenter Registrierungen.
- Separate Bereinigungsbefehle für konfigurierte Kanäle und für den aktuellen Textkanal.
- Speicherung von Servereinstellungen und Registrierungen in SQLite.
- Deutsche und englische Command-Lokalisierungen.
- Optionales Ressourcenmonitoring mit `psutil`; Messwerte und Schwellwertüberschreitungen erscheinen im Log.

## Voraussetzungen

- Python **3.12 oder neuer**.
- Ein Discord-Bot und ein Server, auf dem der Bot eingerichtet werden darf.
- Für die Installation mit den bereitgestellten Skripten: Windows PowerShell beziehungsweise Bash auf Linux.
- Git ist nur erforderlich, wenn das Projekt aus dem Repository bezogen wird.

### Python-Abhängigkeiten

`requirements.txt` installiert `discord.py` für die Discord-Anbindung, `aiosqlite` für den asynchronen SQLite-Zugriff und `hmlogger` für das vom Einstiegspunkt verwendete Logging. `psutil` wird für das optionale Ressourcenmonitoring verwendet; ohne dieses Paket startet der Bot mit deaktiviertem Monitoring.

## Discord-Bot einrichten

1. Erstelle im [Discord Developer Portal](https://discord.com/developers/applications) eine Application und darin einen Bot. Kopiere den Bot-Token und behandle ihn wie ein Passwort.
2. Aktiviere im Bereich **Bot → Privileged Gateway Intents** die Intents **Server Members Intent** und **Message Content Intent**. Der Einstiegspunkt aktiviert `guilds`, `members` und `message_content`.
3. Lade den Bot über **OAuth2 → URL Generator** auf den Zielserver ein. Verwende die Scopes `bot` und `applications.commands`.
4. Gib dem Bot mindestens die Berechtigungen **View Channels**, **Send Messages**, **Read Message History**, **Manage Roles**, **Manage Channels**, **Manage Messages** und **Attach Files**. Die Berechtigungen und die Rollenposition des Bots müssen auch in den betroffenen Kanälen und gegenüber den zu vergebenden Rollen ausreichen.
5. Setze den Bot in der Rollenliste über die Rollen, die er vergeben oder entfernen soll. Discord erlaubt dem Bot keine Verwaltung gleichrangiger oder höherer Rollen.
6. Starte den Bot. Beim Start werden die Slash-Commands global synchronisiert; bis sie in Discord erscheinen, kann es kurz dauern.

Die Befehle unter `/wz` prüfen die nötigen Bot-Berechtigungen für Rollen, Kanäle, Nachrichten, Dateianhänge und den Nachrichtenverlauf. Die Einrichtungskommandos sind auf Mitglieder mit **Manage Roles**, **Manage Messages** und **Manage Channels** beschränkt. `/wz registration register`, `/wz registration reset` und `/wz registration csv` verlangen zusätzlich **Moderate Members**. `/purge` besitzt im Bot selbst keine zusätzliche Berechtigungsprüfung für den ausführenden Benutzer; beschränke den Zugriff auf diesen Befehl deshalb über die Discord-Integrationseinstellungen. Sorge außerdem dafür, dass der Bot Nachrichten in den Registrierungs- und gegebenenfalls Bereinigungskanälen sehen und verwalten kann.

## Installation und Start

Führe Befehle aus dem Projektverzeichnis aus. Das ist wichtig, weil `configuration.json`, die Datenbank und das Log anhand des aktuellen Arbeitsverzeichnisses angesprochen werden.

### Automatische Installation

Die Skripte erstellen eine virtuelle Umgebung, installieren `requirements.txt` und können optional den Bot-Token hinterlegen. Prüfe ein Skript, bevor du es ausführst.

**Windows (PowerShell):**

```powershell
.\scripts\win\install.ps1
.\venv\Scripts\python.exe src\bot.py
```

**Linux:**

```bash
bash scripts/linux/install.bash
./venv/bin/python src/bot.py
```

Das Linux-Skript kann bei Bedarf systemweite Pakete und weitere Installationsschritte erfordern. Die Dienstskripte `scripts/linux/start_bot_service.bash` und `scripts/linux/stop_bot_service.bash` steuern einen bereits eingerichteten systemd-Dienst namens `discordbot.service`; sie erstellen weder dessen Unit-Datei noch konfigurieren sie den Dienst.

### Manuelle Installation

**Windows (PowerShell):**

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
$env:WZ_BOT_TOKEN = "DEIN_DISCORD_BOT_TOKEN"
.\venv\Scripts\python.exe src\bot.py
```

**Linux:**

```bash
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
export WZ_BOT_TOKEN="DEIN_DISCORD_BOT_TOKEN"
./venv/bin/python src/bot.py
```

Nach dem Setzen der Umgebungsvariable läuft der Bot im selben Terminal. Für einen dauerhaften Betrieb muss sie in der Umgebung des jeweiligen Dienstes gesetzt werden. Unter Windows und Linux können die Installationsskripte den Token alternativ in der Windows-Registry beziehungsweise in `~/.config/hsbot/config` ablegen. Die Anwendung sucht den Token zuerst in `WZ_BOT_TOKEN`, danach im jeweiligen plattformspezifischen Speicher.

Der Token darf nicht in Git eingecheckt oder öffentlich geteilt werden. Bei versehentlicher Veröffentlichung muss er im Developer Portal erneuert werden.

## Commands

Alle Bot-Befehle sind Discord-Slash-Commands. Die Registrierungsfunktionen liegen unter `/wz registration`; Einrichtung und Konfiguration unter `/wz setup`.

### Übersicht und allgemeine Moderation

| Befehl | Beschreibung |
| --- | --- |
| `/about-bot` | Zeigt Informationen über den Bot an. Die Antwort ist standardmäßig privat. |
| `/wz about-bot` | Zeigt Informationen über den Bot an. Die Antwort ist standardmäßig privat. |
| `/purge` | Bereinigt Nachrichten im aktuellen Textkanal oder Thread. `limit` ist standardmäßig `500`; `ignore_bots` und `ignore_pinned` sind standardmäßig aktiviert. |

### Registrierung

| Befehl | Beschreibung |
| --- | --- |

| `/wz registration csv` | Erstellt einen CSV-Export der Registrierungen und hängt ihn an die Antwort an. Die Datei enthält Discord-Name, Anzeigename, Rolle, Zeitstempel und Rollenscore. Antwortstandard: privat. Der Befehl ist pro Server auf einen Aufruf alle 120 Sekunden begrenzt. |
| `/wz registration reset` | Entfernt Registrierungen und Rollen aller **nicht permanenten** Registrierungsrollen. Standardmäßig (`purge: true`) werden außerdem im Registrierungskanal und in den konfigurierten Bereinigungskanälen jeweils bis zu 500 nicht angepinnte Nachrichten von Nicht-Bots gelöscht. Mit `purge: false` bleibt die Kanalbereinigung aus. Antwortstandard: nicht privat. |
| `/wz registration purge-list` | Zeigt vor der Bereinigung die konfigurierten Kanäle zur Bestätigung an und löscht dort jeweils bis zu 500 nicht angepinnte Nachrichten von Nicht-Bots; Registrierungen und Rollen werden dabei nicht zurückgesetzt. Antwortstandard: privat. |

`reset` und `purge-list` wirken destruktiv. Prüfe die angezeigten Kanäle und sichere benötigte Informationen, bevor du sie ausführst. Angepinnte Nachrichten und Nachrichten von Bots werden bei diesen beiden Bereinigungsbefehlen übersprungen.

### Einrichtung

Die Befehle in `/wz setup` setzen für den ausführenden Benutzer **Manage Roles**, **Manage Messages** und **Manage Channels** voraus.

| Befehl | Beschreibung |
| --- | --- |
| `/wz setup configure channel:<Textkanal> [role:<Rolle>]` | Legt den Kanal für die Registrierungsübersicht fest. Optional kann die erste Registrierungsrolle hinzugefügt werden; ohne `role` muss mindestens eine Registrierungsrolle bereits konfiguriert sein. |
| `/wz setup role-add role:<Rolle> [permanent:<true/false>]` | Fügt eine Registrierungsrolle hinzu. Standard für `permanent` ist `false`; maximal vier Rollen sind vorgesehen. |
| `/wz setup role-remove role:<Rolle>` | Entfernt eine konfigurierte Registrierungsrolle, die zugehörigen gespeicherten Registrierungen und die Rolle von betroffenen Servermitgliedern. Die letzte konfigurierte Rolle kann nicht entfernt werden. |
| `/wz setup message [title:<Text>] [message:<Text>] [message_upload:<TXT-Datei>]` | Ändert Titel und/oder Beschreibung der Übersicht. Für die Beschreibung kann Text oder eine UTF-8-codierte `.txt`-Datei verwendet werden, nicht beides gleichzeitig. Die Datei `assets/DiscordMessageExample.txt` dient als Beispiel. |
| `/wz setup purge-channel-add` | Öffnet eine Auswahl zum Hinzufügen zusätzlicher Textkanäle für die Bereinigung beim Registrierungs-Reset. Höchstens 25 Kanäle pro Server; der Registrierungskanal wird separat durch `configure` festgelegt. |
| `/wz setup purge-channel-remove` | Öffnet eine Auswahl zum Entfernen zusätzlicher Bereinigungskanäle. |

Antworten auf die Setup-Befehle und die Kanalauswahl sind privat. Änderungen an Rollen, Nachrichten und Kanälen sind dauerhaft beziehungsweise können Servermitgliedern und Nachrichten betreffen.

## Konfiguration

Die Datei [`configuration.json`](./configuration.json) liegt im Projektstamm. Fehlende Dateien werden beim Start mit Standardwerten erzeugt. Die darin enthaltenen Abschnitte sind:

| Abschnitt | Schlüssel | Bedeutung |
| --- | --- | --- |
| `bot` | `prefix`, `delay_seconds`, `token_env` | Allgemeine Standardwerte für Bot-Präfix, Verzögerung und Token-Variablennamen. Der aktuelle Bot verwendet Slash-Commands; das eigentliche Token-Lesen erfolgt über `WZ_BOT_TOKEN` und `Token`. |
| `database` | `folder`, `filename` | Speicherort der SQLite-Datenbank. Standard: `data/data.db`. |
| `monitoring` | `interval_seconds`, `cpu_threshold`, `memory_threshold`, `disk_threshold`, `temperature_threshold` | Intervall und Warnschwellen der optionalen Ressourcenüberwachung. |
| `wz_registration` | `max_registration_roles`, `min_registration_roles`, `default_title`, `default_description` | Grenzwerte und Standardtexte der WZ-Registrierung. Standardmäßig sind höchstens vier und mindestens eine Registrierungsrolle vorgesehen. |

Die Serverkonfiguration für Registrierungskanal, Rollen, Anmeldungen und Bereinigungskanäle wird in SQLite gespeichert, nicht in `configuration.json`. Verändere die Datei bei gestopptem Bot und sichere vor Änderungen oder Upgrades sowohl sie als auch `data/data.db`.

## Daten, Logs und Betrieb

- SQLite-Datenbank: standardmäßig `data/data.db`. Sie enthält serverbezogene Konfigurationen und Registrierungsdaten und muss für Neustarts erhalten bleiben.
- Logdatei: `bot.log` im Projektstamm. Die Anwendung protokolliert außerdem auf der konfigurierten Logging-Ausgabe.
- Das optionale Paket `psutil` aktiviert periodische Ressourcenwarnungen. Ohne `psutil` startet der Bot weiter, das Monitoring bleibt deaktiviert.
- Der Prozess muss laufen, damit Registrierungen verarbeitet und Übersichten aktualisiert werden. Für einen Dauerbetrieb empfiehlt sich ein Dienst mit gesicherter Token- und Datenbankumgebung.
- SQLite-Datei und Logs können IDs und Nutzungsdaten enthalten. Schütze sie entsprechend, nimm sie nicht in öffentliche Commits auf und erstelle regelmäßig sichere Backups.

## Projektstruktur

```text
assets/                         Beispiele und Vorlagen
data/                           Laufzeitdatenbank (wird bei Bedarf erstellt)
scripts/
  linux/                        Linux-Installation und systemd-Steuerung
  win/                          Windows-Installation
src/
  bot.py                        Einstiegspunkt
  HmWz/
    hmClient/                   Discord-Client, Commands und Monitoring
    moduls/                     Modulsystem und WZ-Registrierung
    i18n/                       gemeinsame Übersetzungen
    configuration.py            Laden der Laufzeitkonfiguration
    sqlLiteDB.py                 asynchroner SQLite-Zugriff
requirements.txt                Python-Abhängigkeiten
configuration.json              Laufzeitkonfiguration
```

Der Einstiegspunkt `src/bot.py` fügt `src/HmWz` dem Python-Importpfad hinzu, richtet Logging und Discord-Intents ein, lädt den Token und startet anschließend den Client. Das Registrierungsmodul und seine Datenbanktabellen werden serverbezogen verwaltet.

## Entwicklung und Tests

Für lokale Entwicklung und Debugging kann die virtuelle Umgebung wie oben angelegt werden. Der Bot lässt sich aus dem Projektstamm mit `python src/bot.py` starten; zum Debuggen ist außerdem eine VS-Code-Konfiguration in `.vscode/launch.json` vorhanden. Die Python-Abhängigkeiten sind in `requirements.txt` festgehalten.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [`LICENSE`](./LICENSE).
