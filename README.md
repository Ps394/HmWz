# HmWz

**HmWz** ist ein modularer Discord-Bot zur Verwaltung von WZ-Anmeldungen für das Spiel **Hadestar**. Er veröffentlicht pro Server eine interaktive Registrierungsübersicht, vergibt die dazugehörigen Discord-Rollen und hält Registrierungen und Einstellungen in einer lokalen SQLite-Datenbank fest.

Diese README beschreibt den aktuellen Projektstand, die Einrichtung auf einem Discord-Server, alle verfügbaren Befehle sowie Installation und Betrieb.

![Beispiel einer Bot-Übersicht](assets/registration.png)

## Funktionen

- Mehrere voneinander unabhängige WZ-Anmeldungen pro Server, jeweils mit eigenem
  Anmeldungskanal, Rollen, Übersicht und Bereinigungskanälen.
- QS-Anmeldungen auf derselben Registrierungsbasis wie WZ, mit bis zu vier
  nicht permanenten Rollen.
- Kanalbezogene QS-Übersichten; ein Reset benötigt eine ausdrückliche Bestätigung.
- Kanalbezogene QS-Phasenqueues mit 24-stündigen Eruptionen und 3 bis 6
  konfigurierbaren Phasen.
- Höchstens 40 verschiedene Teilnehmende pro Eruption; eine Person kann sich
  für mehrere Phasen anmelden und pro Eruption nur eine Basiszerstörung bestätigen.
- Private Phasenthreads mit nummerierten Anmeldelisten, hervorgehobenen ersten
  acht Plätzen, separat konfigurierter QS-Rolle und Bestätigungsübersicht.
- IANA-Zeitzonen für lokale Phasenstarts; nicht existierende und mehrdeutige
  Ortszeiten sowie überlappende Phasen werden abgewiesen.
- Interaktive Anmeldung und Abmeldung über Schaltflächen in der jeweiligen Übersicht.
- Verknüpfung mehrerer Ingame-Accounts mit einem Discord-Mitglied sowie
  accountbezogene An- und Abmeldung (einschließlich ALT-Anmeldungen).
- Mehrere WZ-Anmeldungen pro Guild mit jeweils eigenen Rollen; eine Discord-Rolle
  kann nur einer Anmeldung zugeordnet werden.
- Registrierungsinformationen aller Anmeldungen können bei konfiguriertem
  Ereigniskanal in einen festen Guild-Kanal geteilt werden.
- Verwaltung der Anmeldungsnachricht und der für einen Reset zusätzlich zu bereinigenden Textkanäle.
- CSV-Export und Zurücksetzen nicht permanenter Registrierungen.
- Separate Bereinigungsbefehle für konfigurierte Kanäle und für den aktuellen Textkanal.
- Speicherung von Servereinstellungen, Ingame-Accounts und Registrierungen in
  SQLite; Discord-Namen werden bei Bedarf aus der Guild bezogen und nicht separat
  zwischengespeichert.
- `WzGameAccounts` verknüpft Ingame-Accountnamen mit Discord-Mitgliedern.
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
4. Gib dem Bot mindestens die Berechtigungen **View Channels**, **Send Messages**, **Embed Links**, **Read Message History**, **Manage Roles**, **Manage Channels**, **Manage Messages** und **Attach Files**. Die Berechtigungen und die Rollenposition des Bots müssen auch in den betroffenen Kanälen und gegenüber den zu vergebenden Rollen ausreichen.
5. Setze den Bot in der Rollenliste über die Rollen, die er vergeben oder entfernen soll. Discord erlaubt dem Bot keine Verwaltung gleichrangiger oder höherer Rollen.
6. Starte den Bot. Beim Start werden die Slash-Commands global synchronisiert; bis sie in Discord erscheinen, kann es kurz dauern.

Registrierungen und deren Einrichtung werden über die gemeinsamen Befehle unter `/registration` verwaltet. Verknüpfte Ingame-Accounts liegen unabhängig davon unter `/account`.

QS-Phasenqueues werden pro Textkanal mit `/queue setup` eingerichtet. Das Setup
konfiguriert eine QS-Rolle, den Titel und die Beschreibung der Gesamtübersicht,
ein lokales Startdatum und eine Startuhrzeit mit IANA-Zeitzone sowie 3 bis 6 Phasen. Jede Phase startet
zu einer vollen Stunde zwischen `00:00` und `23:00` und dauert 1 bis 3 Stunden.
Phasen dürfen sich nicht überlappen; Starts in DST-Lücken oder doppelte lokale
Uhrzeiten bei der Herbstumstellung werden abgewiesen. Die Eruption beginnt zum gewählten lokalen Zeitpunkt und dauert exakt 24 Stunden.

In jeder Eruption können höchstens 40 unterschiedliche Personen teilnehmen.
Eine Person darf sich für mehrere Phasen anmelden; die Anmeldung vergibt die
konfigurierte QS-Rolle und gibt Zugriff auf den jeweiligen privaten
Phasenthread. Beim Abmelden aus der letzten Phase dieser Eruption entfernt der
Bot die QS-Rolle nur, wenn er sie bei der Anmeldung selbst vergeben hatte. Die
nummerierte Thread-Liste ist chronologisch sortiert und hebt die ersten acht
Plätze optisch hervor; weitere Anmeldungen bleiben möglich, solange die
Eruptionsgrenze von 40 Personen nicht erreicht ist.

Im aktiven Phasenthread können angemeldete Personen eine Basiszerstörung über
ein Modal bestätigen. Der konfigurierbare Modaltext wird angezeigt. Pro Person
und Eruption wird die Bestätigung datenbankseitig nur einmal angenommen, auch
wenn die Person mehreren Phasen angehört. Die Gesamtübersicht zeigt die
Teilnehmendenzahl und Phasen; eine separate Übersicht zählt bestätigte
Zerstörungen und offene Zerstörungen anhand der tatsächlich angemeldeten
Personen, nicht anhand der Obergrenze 40. Der Bot pingt die QS-Rolle nicht
automatisch. Ein Moderator kann einen abgeschlossenen Lauf mit `/queue reset`
bestätigt bereinigen und dabei den nächsten lokalen Start festlegen. Der Reset
entfernt nur gespeicherte Queue-Übersichtsnachrichten und die referenzierten
Phasenthreads; die Queue-Grundkonfiguration bleibt erhalten. Optional kann die
konfigurierte QS-Rolle dabei von Teilnehmenden entfernt werden. Drei getrennte,
standardmäßig deaktivierte Erinnerungen können für Eruptionsstart, Eruptionsende
und Phasenstart eingestellt werden; ihre Zustellung bleibt über Bot-Neustarts
gespeichert und Erwähnungen sind jeweils auf die QS-Rolle beziehungsweise
Phasenteilnehmenden begrenzt. `/queue remove` entfernt nur die aktuelle Queue-Konfiguration;
gespeicherte Eruptionen, Anmeldungen und Bestätigungen bleiben erhalten.
Historische Einstellungen der früheren Queue-Modi bleiben als Legacy-Daten in
der Datenbank erhalten und werden nicht mehr ausgeführt oder in QS-Phasen
umgedeutet. Der Bot benötigt das Erstellen privater Threads, das Verwalten von
Threads sowie **Manage Roles** mit passender Rollenposition.

### Spendenübersichten

Mit `/donation setup` öffnest du im aktuellen Textkanal das interaktive
Setup-Menü. Zuerst wählst du **Einfache Spende** oder **Rush-Spende**. Im Menü
konfigurierst du Titel und Beschreibung, die Anzahl der letzten Einträge
(1–20, Standard 20), ob das kanalbezogene All-Time-Spendenranking (Charts)
angezeigt wird und optional einen JSON-Exportkanal.
Bei einfachen Spenden sind Einheit und optionale feste Betragsauswahl einstellbar;
neu eingerichtete einfache Spenden verwenden standardmäßig vier Credit-Buttons:
`10.000`, `100.000`, `1.000.000` und `8.000.000` Credits. Die festen Werte
können im Setup angepasst werden; ohne feste Werte bleibt die freie Eingabe
verfügbar.

Rush-Spenden verwenden fest die Optionen **1h**, **8h** und **24h** sowie
Kristalle als Einheit. Der Start wird mit Datum und Uhrzeit in
`Europe/Berlin` festgelegt. Ein Rush-Zeitraum dauert neun Tage; Spenden sind bis
einschließlich acht Tage nach dem Start möglich. Die Preise richten sich nach
der seit dem Start vergangenen Zeit: 0–72h, 72–144h und 144–192h. Die
Kristallpreise je Option und Zone sind:

| Option | 0–72h | 72–144h | 144–192h |
| --- | ---: | ---: | ---: |
| 1h | 28 | 56 | 84 |
| 8h | 223 | 445 | 667 |
| 24h | 667 | 1.334 | 2.001 |

Die Übersicht zeigt die drei Preiszonen und hebt die aktuell geltende Zone
hervor. Überschreitet eine Option eine Zonengrenze, erhöht sich der Preis der
aktuellen Zone nach `(1 + (x / 24)) * aktueller Preis`, wobei `x` die Stunden
der Spende in der nächsten Zone aufgerundet auf angefangene Stunden bezeichnet;
das Ergebnis wird kaufmännisch auf ganze Kristalle gerundet. Die
Rush-Schaltflächen **1h**, **8h** und **24h**
stehen direkt bei der Übersicht und werden außerhalb des zulässigen Zeitraums
ausgeblendet. Vor dem Speichern wird der berechnete Preis bestätigt. Die
Übersicht zeigt die Spenden und Zeitersparnis des aktuellen Zyklus. Das
optionale separate Ranking bleibt kanalbezogen und zählt alle Zyklen; bei
Rush-Spenden zeigt es je Person sowohl die Kristallmenge als auch die
eingesparte Zeit. Beträge werden mit Punkten als Tausendertrennzeichen
dargestellt (zum Beispiel `1.000.000`).

Du kannst `/donation setup` in mehreren Kanälen ausführen, um getrennte
Spenden-Systeme einzurichten. Bei aktiviertem JSON-Export wird `/donation reset`
vor dem Zykluswechsel eine Datei mit allen Spenden des aktuellen Zyklus in den
konfigurierten Kanal senden. Das kurze JSON enthält Systemname, Quellkanal,
Zyklus sowie je Spende Mitglied, Betrag, Einheit und Zeitpunkt; Rush-Spenden
enthalten zusätzlich die Zeitersparnis. Scheitert der Export, wird der Reset
abgebrochen. Ohne Exportkanal wird der Reset wie gewohnt ausgeführt.
`/donation reset` startet den aktuellen Zyklus neu; bei Rush-Spenden legst du
dabei den neuen Start fest. Frühere Einträge bleiben im All-Time-Ranking
enthalten. `/donation remove` und
`/donation delete` entfernen nach Bestätigung Einrichtung, Bot-Nachrichten und
alle Spenden des aktuellen Kanals unwiderruflich. Damit das Ranking
vergleichbar bleibt, kann die Einheit nach dem ersten Spenden-Eintrag nicht
mehr geändert werden.

## Installation und Start

Führe Befehle aus dem Projektverzeichnis aus. Das ist wichtig, weil `configuration.json`, die Datenbank und das Log anhand des aktuellen Arbeitsverzeichnisses angesprochen werden.

### Automatische Installation

Die Installationsskripte bündeln separat ausführbare Etappen: virtuelle Umgebung erstellen, Abhängigkeiten installieren, optional den Token konfigurieren und den automatischen Start einrichten. Linux installiert und startet einen systemd-Dienst; Windows registriert eine Aufgabenplaner-Aufgabe, die beim Anmelden des aktuellen Benutzers startet und sofort gestartet wird. Prüfe ein Skript, bevor du es ausführst.

**Windows (PowerShell):**

```powershell
.\scripts\win\install.ps1
```

**Linux:**

```bash
bash scripts/linux/install.bash
```

Unter Windows läuft die Aufgabe im aktuellen Benutzerkontext, damit sie auf den Token in dessen Registry zugreifen kann. Sie startet beim Benutzer-Login und nicht vor der Anmeldung. Die Skripte `scripts/win/start_bot_service.ps1` und `scripts/win/stop_bot_service.ps1` starten beziehungsweise stoppen sie; Stoppen entfernt die Aufgabe nicht.

Die Etappen können einzeln ausgeführt werden:

| Etappe | Windows (PowerShell) | Linux (Bash) |
| --- | --- | --- |
| Virtuelle Umgebung erstellen | `.\scripts\win\create_venv.ps1` | `bash scripts/linux/create_venv.bash` |
| Abhängigkeiten installieren | `.\scripts\win\install_dependencies.ps1` | `bash scripts/linux/install_dependencies.bash` |
| Token optional konfigurieren | `.\scripts\win\configure_token.ps1` | `bash scripts/linux/configure_token.bash` |
| Automatischen Start einrichten | `.\scripts\win\install_service.ps1` | `bash scripts/linux/install_service.bash` |

**Test-Branch (Linux):** Dieser Branch ist für einen Test-Bot parallel zum produktiven Bot gedacht. Die Linux-Skripte verwenden daher standardmäßig den Dienst `discordbot-test.service` und die Token-Datei `~/.config/hsbot-test/config` (wird per `EnvironmentFile` an den Dienst übergeben). Klone den Branch in ein eigenes Verzeichnis (eigene `venv`), nutze einen eigenen Bot-Token und überschreibe bei Bedarf `HMWZ_SERVICE_NAME` bzw. `HMWZ_TOKEN_FILE`. Der produktive `discordbot.service` bleibt unberührt.

Die Dienstinstallation unter Linux benötigt `systemd` und `sudo`; führe das Installationsskript als Bot-Benutzer aus, nicht als root. Sie installiert `discordbot.service`, aktiviert ihn beim Systemstart und startet ihn. Verwende `scripts/linux/start_bot_service.bash` zum Neustart und `scripts/linux/stop_bot_service.bash` zum Stoppen; der Dienst bleibt für den nächsten Systemstart aktiviert.

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

Alle Bot-Befehle sind Discord-Slash-Commands. Registrierungen werden unter `/registration` verwaltet; Einrichtung und Konfiguration liegen unter `/registration setup`. Verknüpfte Ingame-Accounts werden guildweit unter `/account` verwaltet.

### Übersicht und allgemeine Moderation

| Befehl | Beschreibung |
| --- | --- |
| `/about-bot` | Zeigt Informationen über den Bot an. Die Antwort ist standardmäßig privat. |
| `/purge` | Bereinigt Nachrichten im aktuellen Textkanal oder Thread. `limit` ist standardmäßig `500`; `ignore_bots` und `ignore_pinned` sind standardmäßig aktiviert. |

### Registrierung

| Befehl | Beschreibung |
| --- | --- |
| `/account account-add account:<Account>` | Verknüpft einen Ingame-Account mit deinem Discord-Mitglied. Ein Account kann pro Server nur einem Discord-Mitglied zugeordnet sein. |
| `/account account-remove account:<Account>` | Entfernt einen verknüpften Ingame-Account sowie dessen WZ-Anmeldungen und die zugehörigen Discord-Rollen, sofern kein anderer deiner Accounts diese Rollen benötigt. |
| `/account account-list` | Zeigt deinen Discord-Anzeigenamen als Account sowie alle verknüpften Ingame-Accounts an. |
| `/registration register account:<Account> role:<Anmeldungsrolle>` | Meldet einen deiner verknüpften Ingame-Accounts für die angegebene konfigurierte Rolle an. |
| `/registration deregister account:<Account>` | Meldet den Account von seiner aktuellen Anmeldungsrolle ab. Die Rolle wird automatisch aus der Registrierung ermittelt und nur entfernt, wenn kein weiterer Account dieses Mitglieds dafür registriert ist. |
| `/registration csv` | Erstellt einen CSV-Export der Registrierungen und hängt ihn an die Antwort an. Die Datei enthält Discord-Name, Anzeigename, Ingame-Account, Rolle, Zeitstempel und Rollenscore. |
| `/registration reset` | Setzt die nicht permanenten Registrierungen im aktuellen Anmeldungskanal zurück. |

`/registration reset` wirkt destruktiv. Prüfe den aktuellen Anmeldungskanal und sichere benötigte Informationen, bevor du den Befehl ausführst.

### WZ- und QS-Module

| Befehl | Beschreibung |
| --- | --- |
| `/wz setup` | Öffnet das private WZ-Menü mit direkt sichtbarer Konfiguration und Aktionen zum Hinzufügen und Entfernen von WZ-Rollen und WZ-Kanälen. |
| `/wz reset-channels` | Bereinigt nach Bestätigung die konfigurierten WZ-Kanäle. |
| `/wz reset-roles` | Entfernt nach Bestätigung konfigurierte WZ-Rollen von Servermitgliedern; ausgewählte Ausnahmen bleiben erhalten. |
| `/qs setup` | Öffnet das private QS-Menü mit direkt sichtbarer Konfiguration und Aktionen zum Hinzufügen und Entfernen von QS-Rollen und QS-Kanälen. |
| `/qs reset-channels` | Bereinigt nach Bestätigung die konfigurierten QS-Kanäle. |
| `/qs reset-roles` | Entfernt nach Bestätigung die im aktuellen QS-Kanal konfigurierten Rollen von Servermitgliedern. |

Verknüpfe Accounts mit `account-add`, bevor du sie anmeldest. Registrierungen über die Übersichtsschaltflächen bleiben Discord-Mitglied-bezogen; die Commands `register` und `deregister` verwalten gezielt den angegebenen Ingame-Account. Vorhandene Registrierungen bleiben beim Datenbank-Upgrade erhalten.

### Einrichtung

Die Einrichtungs- und Entfernen-Befehle setzen für den ausführenden Benutzer **Manage Roles**, **Manage Messages** und **Manage Channels** voraus.

| Befehl | Beschreibung |
| --- | --- |
| `/registration setup` | Öffnet im aktuellen Kanal ein privates Dialogmenü zum Bearbeiten von Titel und Text, Hinzufügen permanenter oder nicht permanenter Rollen sowie zum Festlegen oder Deaktivieren des guildweiten JSON-Exportkanals. |
| `/registration remove` | Entfernt nach Bestätigung die Anmeldung im aktuellen Kanal einschließlich Teilnahmen, vergebener Rollen, Übersichten und zugehöriger Konfiguration. |

Antworten auf Setup-Befehle und Auswahlen sind privat. Bestätigungsdialoge verschwinden nach Abschluss oder spätestens nach drei Minuten; kurzlebige Ergebnisnachrichten werden nach zehn Sekunden entfernt.

## Konfiguration

Die Datei [`configuration.json`](./configuration.json) liegt im Projektstamm. Fehlende Dateien werden beim Start mit Standardwerten erzeugt. Die darin enthaltenen Abschnitte sind:

| Abschnitt | Schlüssel | Bedeutung |
| --- | --- | --- |
| `bot` | `prefix`, `delay_seconds`, `token_env` | Allgemeine Standardwerte für Bot-Präfix, Verzögerung und Token-Variablennamen. Der aktuelle Bot verwendet Slash-Commands; das eigentliche Token-Lesen erfolgt über `WZ_BOT_TOKEN` und `Token`. |
| `database` | `folder`, `filename` | Speicherort der SQLite-Datenbank. Standard: `data/data.db`. |
| `monitoring` | `interval_seconds`, `cpu_threshold`, `memory_threshold`, `disk_threshold`, `temperature_threshold` | Intervall und Warnschwellen der optionalen Ressourcenüberwachung. |
| `wz_registration` | `max_registration_roles`, `min_registration_roles`, `default_title`, `default_description` | Grenzwerte und Standardtexte der WZ-Registrierung. Standardmäßig sind höchstens vier und mindestens eine Registrierungsrolle vorgesehen. |
| `hs.qs` | `max_registration_roles`, `default_title`, `default_description` | Standardwerte der QS-Registrierung. Maximal vier Rollen sind zulässig. |

Die einzelnen WZ-Anmeldungen mit ihren Kanälen, Rollen, Anmeldungen und Bereinigungskanälen werden in SQLite gespeichert, nicht in `configuration.json`. Neue Standardwerte liegen in `hs.wz`; der bisherige Schlüssel `wz_registration` wird für vorhandene Konfigurationsdateien weiterhin gelesen. Verändere die Datei bei gestopptem Bot und sichere vor Änderungen oder Upgrades sowohl sie als auch `data/data.db`.

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
  hmwz/
    hm_client/                  Discord-Client, Commands und Monitoring
      repositories/             Serverdatenzugriff
    modules/                    Modulsystem
      registration/             Botweite Registrierungsbasis
        commands/               Gemeinsame Registrierungsbefehle
        i18n/                   Übersetzungen der Anmeldungsfunktion
        models/                 Allgemeine Registrierungsmodelle
        repositories/           Gemeinsamer Registrierungsdatenzugriff
      donation/                 Spendenübersichten und persistente Spenden
        models/                 Fachliche Spenden- und Kanalwerte
        repositories/           SQLite-Persistenz der Spenden
      queue/                    QS-Eruptionen und Phasenqueues
        models/                 Eruptions- und Phasenmodelle
        repositories/           SQLite-Persistenz der QS-Phasenqueues
      hs/
        account/                Guildweite Account-Verwaltung
        qs/                     QS-spezifische Funktionen und Commands
          repositories/         QS-Registrierungsdatenzugriff
        i18n/                   gemeinsame HS-Übersetzungen
        wz/                     WZ-Kanalverwaltung und Commands
          repositories/         WZ-Konfiguration und Bereinigungskanäle
    hm_models/                  gemeinsame Daten- und Embed-Modelle
    ui/                         gemeinsame Discord-UI-Komponenten
    i18n/                       gemeinsame Übersetzungen
    configuration.py            Laden der Laufzeitkonfiguration
    sqlite_db.py                asynchroner SQLite-Zugriff
requirements.txt                Python-Abhängigkeiten
pyproject.toml                  Paket-, Hatch-Build- und optionale Entwicklungsabhängigkeiten
configuration.json              Laufzeitkonfiguration
```

`src/bot.py` ist ein schlanker Kompatibilitätseinstiegspunkt, der das Paket `hmwz` startet. Er verändert den Python-Importpfad nicht. Das Paket kann außerdem installiert und mit dem Kommando `hmwz` gestartet werden. `hs.wz`, `hs.qs` und `hs.account` sind getrennte Submodule. Das botweite `registration`-Modul stellt gemeinsame Registrierungsbefehle, Modelle und Logik bereit; QS-spezifische Commands und Datenzugriff liegen bei `hs.qs`. WZ und QS speichern ihre Registrierungen weiterhin in getrennten Tabellen.

## Entwicklung und Tests

Für lokale Entwicklung und Debugging kann die virtuelle Umgebung wie oben angelegt werden. Mit `python -m pip install -e ".[monitoring]"` wird das Paket samt optionalem Ressourcenmonitoring installierbar; anschließend startet `hmwz` den Bot. Alternativ funktioniert aus dem Projektstamm weiterhin `python src/bot.py`. Für die Entwicklung installiere Hatch und führe `hatch run test` für die Tests inklusive Coverage-Bericht oder `hatch run check` für Linting, Formatprüfung, Typprüfung und Tests aus. Einzelne Hatch-Befehle sind `hatch run lint`, `hatch run format`, `hatch run format-check` und `hatch run typecheck`. Die Skripte für Windows und Linux installieren weiterhin `requirements.txt` und verwenden den Kompatibilitätseinstiegspunkt.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [`LICENSE`](./LICENSE).
