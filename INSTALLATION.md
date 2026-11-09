# Installation

Diese Anleitung beschreibt Voraussetzungen, Discord-Einrichtung, Installation
und Start von HmWz. Die Befehlsreferenz steht in der
[COMMANDS.md](COMMANDS.md). Funktionen und Projektinformationen findest du in
der [README.md](README.md).

## Voraussetzungen

- Python **3.12 oder neuer**
- Eine Discord-Application mit Bot sowie ein Server, auf dem du den Bot
  installieren darfst
- Für die automatischen Installationsskripte: PowerShell unter Windows oder
  Bash unter Linux

## Discord-Bot einrichten

1. Erstelle im [Discord Developer Portal](https://discord.com/developers/applications)
   eine Application und darin einen Bot. Behandle den Bot-Token wie ein Passwort.
2. Aktiviere unter **Bot → Privileged Gateway Intents** den **Server Members
   Intent** und den **Message Content Intent**. Der Bot verwendet außerdem den
   `guilds`-Intent.
3. Erstelle unter **OAuth2 → URL Generator** eine Einladungs-URL mit den Scopes
   `bot` und `applications.commands`, und lade den Bot auf deinen Server ein.
4. Gewähre die für deine Funktionen erforderlichen Rechte. Typischerweise sind
   das **View Channels**, **Send Messages**, **Embed Links**, **Read Message
   History**, **Manage Roles**, **Manage Messages**, **Manage Channels** und
   **Attach Files**. Für Qs werden zusätzlich unter anderem
   **Create Public Threads**, **Send Messages in Threads** und **Manage Threads**
   benötigt. Kanalberechtigungen können Serverrechte einschränken.
5. Setze die Bot-Rolle in der Server-Rollenliste oberhalb der Rollen, die der
   Bot vergeben oder entfernen soll. Discord erlaubt keine Verwaltung
   gleichrangiger oder höherer Rollen.
6. Moderator- und Einrichtungskommandos prüfen standardmäßig auf die Rollen
   **Offiziere** oder **Moderator**. Die Namen müssen zu den Rollen auf deinem
   Server passen. Du kannst sie in `configuration.json` unter `moderator_roles`
   anpassen.

## Automatische Installation

Führe die Befehle im Projektverzeichnis aus. Die Skripte richten die virtuelle
Umgebung und Abhängigkeiten ein, fragen optional den Bot-Token ab und können
einen automatischen Start einrichten.

**Windows (PowerShell):**

```powershell
.\scripts\win\install.ps1
```

**Linux:**

```bash
bash scripts/linux/install.bash
```

Die Schritte können auch einzeln ausgeführt werden:

| Schritt | Windows (PowerShell) | Linux (Bash) |
| --- | --- | --- |
| Virtuelle Umgebung | `.\scripts\win\create_venv.ps1` | `bash scripts/linux/create_venv.bash` |
| Abhängigkeiten installieren | `.\scripts\win\install_dependencies.ps1` | `bash scripts/linux/install_dependencies.bash` |
| Token speichern | `.\scripts\win\configure_token.ps1` | `bash scripts/linux/configure_token.bash` |
| Automatischen Start einrichten | `.\scripts\win\install_service.ps1` | `bash scripts/linux/install_service.bash` |

Unter Windows registriert das Installationsskript eine
Aufgabenplaner-Aufgabe für den aktuellen Benutzer, die bei dessen Anmeldung
startet. Unter Linux wird ein systemd-Dienst eingerichtet und gestartet. Dafür
werden `systemd` und `sudo` benötigt. Führe das Linux-Installationsskript als
Bot-Benutzer und nicht als `root` aus. Skripte zum manuellen Starten und Stoppen
liegen in `scripts/win/` beziehungsweise `scripts/linux/`.

Prüfe Skripte, bevor du sie ausführst. Lokal gespeicherte Tokens sind vertraulich
zu behandeln. Wenn ein Token veröffentlicht wurde, erneuere ihn im Developer
Portal.

## Manuelle Installation

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

Alternativ kannst du das Paket installieren und den Konsolenbefehl verwenden:

```bash
python -m pip install .
hmwz
```

Der Token wird zuerst aus der Umgebungsvariable `WZ_BOT_TOKEN` gelesen. Als
Alternative unterstützen die Installationsskripte die Windows-Registry des
aktuellen Benutzers und unter Linux die Datei `~/.config/hsbot/config`. Setze
Umgebungsvariablen für einen dauerhaft laufenden Dienst in dessen eigener
Umgebung.

## Konfiguration und Laufzeitdaten

Die Laufzeitkonfiguration liegt in `configuration.json` im Projektstamm. Fehlt
die Datei, versucht die Anwendung beim Start eine Datei mit Standardwerten zu
erzeugen. Ändere die Konfiguration möglichst bei gestopptem Bot. Wichtige
Einstellungen sind:

- `moderator_roles`: Rollennamen, die Moderations- und Einrichtungskommandos
  verwenden dürfen.
- `database.folder` und `database.filename`: Speicherort der SQLite-Datenbank.
  Standard ist `data/data.db`.
- `monitoring`: Messintervall und Warnschwellen für CPU, Arbeitsspeicher,
  Datenträger und Temperatur.
- `hs.wz`: Standardwerte der WZ-Registrierung, einschließlich maximaler und
  minimaler Rollenanzahl, Titel und Beschreibung.

Konfiguration, Datenbank und Logdatei werden relativ zum aktuellen
Arbeitsverzeichnis gespeichert. Starte den Bot daher im Projektverzeichnis und
stelle bei Diensten sicher, dass deren Arbeitsverzeichnis stimmt. Die Datenbank
enthält Servereinstellungen, Rollen- und Kanalzuordnungen, Anmeldungen und
Spenden. Sichere vor Updates sowohl `configuration.json` als auch die
Datenbank. Logs und Datenbank können Discord-IDs und Nutzungsdaten enthalten.
schütze Zugriffsrechte, Backups und Speicherorte entsprechend und veröffentliche
diese Dateien nicht.

Der Einstiegspunkt schreibt `bot.log` im Projektverzeichnis. Nach dem Start
meldet der Bot seine Slash-Commands global bei Discord an. Neue Commands können
einige Zeit brauchen, bis sie in Discord erscheinen.

## Entwicklungsumgebung und Tests

Voraussetzung ist Python **3.12 oder neuer**. Installiere die Projektabhängigkeiten
für die Entwicklung einschließlich Hatch:

```bash
python -m pip install -e ".[dev,monitoring]"
```

Führe die Tests mit folgendem Befehl aus:

```bash
hatch run test
```

Für die vollständigen Prüfungen (Linting, Formatkontrolle, Typprüfung und Tests):

```bash
hatch run check
```

Einzelne Prüfungen lassen sich mit `hatch run lint`, `hatch run format-check`
und `hatch run typecheck` starten. `hatch run format` formatiert den Quellcode
und die Tests.