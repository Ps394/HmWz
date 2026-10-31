# HmWz

**HmWz** ist ein modularer Discord-Bot zur Verwaltung von WZ-Anmeldungen für das Spiel **Hadestar**. Er veröffentlicht pro Server eine interaktive Registrierungsübersicht, vergibt die dazugehörigen Discord-Rollen und hält Registrierungen und Einstellungen in einer lokalen SQLite-Datenbank fest.

Diese README beschreibt den aktuellen Projektstand, die Einrichtung auf einem Discord-Server, alle verfügbaren Befehle sowie Installation und Betrieb.

![Beispiel einer Bot-Übersicht](assets/registration.png)

## Funktionen

- Mehrere voneinander unabhängige Anmeldungen im Registrierungsmodul pro Server,
  jeweils mit eigenem Anmeldungskanal, Rollen und Übersicht.
- Eigenständige WZ-Kanal- und Rollenverwaltung pro Server mit bestätigten Resets.
- QS-Anmeldungen auf der allgemeinen Registrierungsbasis, mit bis zu vier
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
- Verwaltung der Anmeldungsnachricht; unabhängig davon verwaltet WZ seine
  für einen Reset zu bereinigenden Textkanäle.
- CSV-Export und Zurücksetzen nicht permanenter Registrierungen.
- Separate Bereinigungsbefehle für konfigurierte Kanäle und für den aktuellen Textkanal.
- Speicherung von Servereinstellungen, Ingame-Accounts und Registrierungen in
  SQLite; Discord-Namen werden bei Bedarf aus der Guild bezogen und nicht separat
  zwischengespeichert.
- `WzGameAccounts` verknüpft Ingame-Accountnamen mit Discord-Mitgliedern.
- Deutsche und englische Command-Lokalisierungen.
- Optionales Ressourcenmonitoring mit `psutil`; Messwerte und Schwellwertüberschreitungen erscheinen im Log.

## Application-Emojis

Beim Start gleicht der Bot die Bilder in `src/hmwz/emojis/assets/` mit den
Emojis seiner Discord-Application ab. Fehlende Emojis werden automatisch
hochgeladen; bestehende Namen werden wiederverwendet, nicht ersetzt oder
gelöscht. Die Emojis sind serverübergreifend für den Bot verfügbar und benötigen
keine Emoji-Slots oder Emoji-Verwaltungsrechte auf den einzelnen Servern.

- Unterstützt werden PNG, JPEG und GIF mit höchstens 256 KiB pro Datei.
- Dateinamen ohne Endung sind die Discord-Emoji-Namen: 2 bis 32 Zeichen aus
  Buchstaben (ASCII), Zahlen und Unterstrichen. Namen müssen auch unabhängig
  von Groß-/Kleinschreibung eindeutig sein.
- `credit.png` und `cristall.png` werden für Credits und Kristalle in
  Spendenbuttons, Ranglisten und Spendenhistorien verwendet.
- Weitere gemeinsame Symbole können über gleichnamige Bilder ergänzt werden,
  etwa `success.png`, `delete.png`, `perma_registration.png` oder
  `normal_registration.png`. Upload-Fehler werden protokolliert; der Bot
  verwendet dann weiterhin die jeweiligen Unicode-Symbole.
- Nach dem Hinzufügen neuer Bilder den Bot neu starten. Zum Austausch eines
  Bildes zuerst das betreffende Application-Emoji im Developer Portal löschen.

Module können `emojis.get("credit", module.client)` aus `hmwz.emojis` für
Button-Emoji-Eigenschaften und Nachrichtentext verwenden. `emojis.render(text,
module.client)` ersetzt gemeinsame Unicode-Symbole durch verfügbare
Application-Emojis. In Button-Labels und Modal-Eingabefeldern bleiben Unicode
und Klartext erhalten, da Discord dort keine Custom-Emoji-Mentions darstellt.

## Wiederverwendbare Overviews

`hmwz.modules.overview.OverviewModule` ist ein direkt instanziierbarer Baustein,
den ein anderes Guild-Modul besitzen und verwenden kann. Er wird nicht separat
vom Modulmanager erzeugt. Das besitzende Modul initialisiert ihn und delegiert
bei Bedarf Lifecycle-Ereignisse:

```python
from hmwz.modules.overview import OverviewButton, OverviewModule

class FeatureModule:
    def __init__(self, guild, client):
        self.overview = OverviewModule(guild, client)

    async def sync(self, startup=False):
        return await self.overview.sync(startup=startup)

    async def ensure(self):
        self.overview.register_handler(
            overview_id="my_feature",
            button_id="action",
            handler=self.handle_action,
        )
        return await self.overview.ensure()

    async def publish_overview(self, channel_id):
        return await self.overview.publish(
            overview_id="my_feature",
            channel_id=channel_id,
            title="Meine Übersicht",
            description="Beschreibung der Übersicht",
            buttons=(OverviewButton(button_id="action", label="Ausführen"),),
        )

    async def on_guild_remove(self, guild):
        return await self.overview.on_guild_remove(guild)
```

`publish` legt die Nachricht an oder aktualisiert die vorhandene; `delete`
entfernt Nachricht und Konfiguration. Die `overview_id` muss pro Guild
eindeutig sein. Die Übersicht und ihre Schaltflächen werden beim Start aus
SQLite wiederhergestellt. Handler werden vom besitzenden Modul vor `ensure`
erneut registriert. Da der Manager nur registrierte Module kennt, muss das
besitzende Modul relevante Guild- und Message-Ereignisse an den Baustein
weiterleiten; insbesondere sollte es `on_guild_remove` aufrufen, damit
Nachrichten beim Verlassen einer Guild bereinigt werden.

## Alte WZ-Datenbank übernehmen

Das Skript [db-merge.py](src/hmwz/modules/registration/db-merge.py) überträgt die
alten Tabellen `WzRegistration`, `WzRoles`, `WzRegistrations` und `WzList` innerhalb
derselben SQLite-Datei in das aktuelle Registration-/Overview-Schema.
Vorher den Bot stoppen und die Projektabhängigkeiten installieren. Zunächst
eine Vorschau ausführen, danach ohne `--dry-run` übernehmen:

```powershell
.\.venv\Scripts\python.exe .\src\hmwz\modules\registration\db-merge.py .\data\data.db --dry-run
.\.venv\Scripts\python.exe .\src\hmwz\modules\registration\db-merge.py .\data\data.db
```

- Vor Änderungen wird neben der Datenbank eine zeitgestempelte `.bak`-Datei
  über die SQLite-Backup-API erstellt (einschließlich WAL-Daten).
- Der Merge läuft in einer Transaktion; Fehler rollen alle Änderungen zurück.
  Die Vorschau schreibt keine dauerhaften Änderungen und erstellt kein Backup.
- Bestehende nicht leere Zielwerte bleiben erhalten; fehlende Werte werden
  ergänzt. Konflikte werden als Warnungen protokolliert. Wiederholungen erzeugen
  keine zusätzlichen Datensätze.
- `Account` wird unverändert als `Alias` übernommen, einschließlich ALT-Anmeldungen,
  Zeitstempeln und vorhandenen Mitglieds-/Rollennamen. Aliase erzeugen nicht
  automatisch neue Ingame-Accountverknüpfungen.
- Nachrichten-IDs, Titel und Texte werden als `registration-<Kanal>` bzw.
  `registration-<Kanal>-list-<Seite>` übernommen. Alte Listenseiten werden nach
  Nachrichten-ID sortiert; der Bot erzeugt Rollenbuttons und aktualisiert die
  Listen beim nächsten Synchronisieren.
- Ohne eindeutigen Anmeldungskanal bleiben Rollen/Anmeldungen unter `Channel=0`
  erhalten und benötigen eine manuelle Zuordnung. Nicht zuordenbare Übersichten
  werden gemeldet und bleiben in den Quelltabellen erhalten.
- Quelltabellen und andere Module werden nicht gelöscht. Bereits vorhandene
  Registration-Zieltabellen müssen das aktuelle kanalbezogene Schema besitzen.

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
Uhrzeiten bei der Herbstumstellung werden abgewiesen. Datum, Uhrzeit und
IANA-Zeitzone werden über Discord-Auswahlen festgelegt und in der Übersicht
zusätzlich als Discord-Zeitstempel angezeigt. Vergangene Startzeitpunkte werden
nicht verschoben; bereits begonnene Eruptionen werden beim Botstart idempotent
wieder aufgenommen. Die Eruption dauert exakt 24 Stunden.

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
konfigurierte QS-Rolle dabei von Teilnehmenden entfernt werden. Reset und Remove
speichern einen dauerhaften Bereinigungsauftrag samt Ressourcen-IDs und
Einzelschrittstatus. Fehlen Discord-Ressourcen, gelten sie als erledigt;
vorübergehende API- oder Berechtigungsfehler bleiben offen und werden regelmäßig
erneut versucht sowie nach Botstart oder erneutem Command fortgesetzt. Ein Reset
meldet erst dann Erfolg, wenn Bereinigung, neuer Lauf und dessen
Übersichten/Phasenthreads abgeschlossen sind. `/queue remove` deaktiviert die Queue
sofort und löscht Konfiguration,
Eruptionen, Anmeldungen, Zerstörungen und Erinnerungen, behält aber offene
Discord-Bereinigungsschritte bis zu deren erfolgreichem Abschluss. Drei getrennte,
standardmäßig deaktivierte Erinnerungen können für Eruptionsstart, Eruptionsende
und Phasenstart eingestellt werden; ihre Zustellung bleibt über Bot-Neustarts
gespeichert und Erwähnungen sind jeweils auf die QS-Rolle beziehungsweise
Phasenteilnehmenden begrenzt.
Historische Einstellungen der früheren Queue-Modi bleiben als Legacy-Daten in
der Datenbank erhalten und werden nicht mehr ausgeführt oder in QS-Phasen
umgedeutet. Der Bot benötigt das Erstellen privater Threads, das Verwalten von
Threads sowie **Manage Roles** mit passender Rollenposition.

### Spendenübersichten

Mit `/donation setup` öffnest du im aktuellen Textkanal das interaktive
Setup-Menü. Zuerst wählst du **Einfache Spende** oder **Rush-Spende**. Im Menü
konfigurierst du Titel und Beschreibung, ob die Spendenhistorie und das
kanalbezogene All-Time-Spendenranking (Charts) angezeigt werden, ob Spenden
angenommen werden und optional einen JSON-Exportkanal.
Das Setup zeigt wie das Registrationsmodul ein gegliedertes Embed mit Kanal,
Spendenart, Titel, Beschreibung, Eingabeoptionen und Anzeige-/Exportstatus.
All-Time-Spendencharts sind bei neuen Einrichtungen **standardmäßig deaktiviert**
und können im Setup eingeblendet werden. Bestehende Chart-Einstellungen bleiben
erhalten.
Bei einfachen Spenden sind Einheit und optionale feste Betragsauswahl einstellbar;
neu eingerichtete einfache Spenden verwenden standardmäßig vier Credit-Buttons:
`10.000`, `100.000`, `1.000.000` und `8.000.000` Credits. Die festen Werte
können im Setup angepasst werden; ohne feste Werte bleibt die freie Eingabe
verfügbar.
Auch Credit-Spenden werden erst nach ausdrücklicher Bestätigung gespeichert.
Ihre Übersicht und Historie zeigen keine Zeitersparnis. Jede neue Spende eines
Nutzers entfernt und entwertet dessen vorherige offene Bestätigung, auch
kanalübergreifend innerhalb desselben Servers.

Rush-Spenden verwenden fest die Optionen **1h**, **8h** und **24h** sowie
Kristalle als Einheit. Im Rush-Setup wählst du einmal die **Zeitzone der Zeiteingabe**
aus dem Dropdown (z. B. Berlin); sie wird pro Einrichtung gespeichert und auch
beim Reset verwendet. Bestehende Einstellungen bleiben erhalten; ohne Auswahl
gilt UTC. Eine Änderung der Eingabezeitzone verschiebt keine gespeicherten Zeitpunkte.
Der gemeinsame UI-Helper nimmt Start und Ziel bequem als **Datum und Uhrzeit**
entgegen, z. B. `31.10.2026 12:30` oder `2026-10-31 12:30`.
Tag und Monat dürfen auch einstellig sein, z. B. `2026-11-3 22:57`
oder `3.11.2026 22:57`; dies gilt auch beim Reset und für die Zielzeit im Setup.
Die Felder zeigen ihre Zeitzone an und sind mit dem aktuellen Wert vorbelegt.
Neue Startvorschläge verwenden volle Minuten, damit Zielzeiten bequem auf dem
Ganzstundenraster liegen. Sekunden sind optional; vorhandene genaue Zeitpunkte
(einschließlich Sekundenbruchteilen) bleiben erhalten. Alternativ funktionieren weiterhin **Discord-Zeitstempel**
(zum Beispiel `<t:1793448000:F>`) und **Unix-Sekunden** (`1793448000`);
diese absoluten Zeitstempel werden nicht durch die Eingabezeitzone umgerechnet.
Regionale Zeitzonen berücksichtigen Sommerzeit automatisch. Nicht existierende
Ortszeiten werden abgewiesen; bei doppelt vorkommenden Ortszeiten muss ein
eindeutiger Discord-/Unix-Zeitstempel eingegeben werden.
Der Helper erzeugt Discord-Zeitstempel im Format `<t:1793403130:F>`.
Setup und öffentliche Spendenübersicht
zeigen Start und beschleunigtes Ende als Discord-Zeitstempel an; Discord stellt
diese automatisch in der lokalen Zeitzone jedes Nutzers dar. Bereits gespeicherte
Startzeitpunkte bleiben unverändert. Ein Rush-Zeitraum dauert
neun Tage; bisher gespendete Beschleunigungen verkürzen diesen Zeitraum.
Eine Spende ist nur möglich, wenn danach mindestens 24 Stunden bis zum
beschleunigten Rush-Ende verbleiben. Die Preise richten sich ausschließlich
nach den bereits gespendeten Beschleunigungsstunden des aktuellen Zyklus,
nicht nach der seit dem Start vergangenen Zeit.

Über **Zielzeit** kannst du im Rush-Setup einen optionalen Zeitpunkt
festlegen; ein leeres Feld entfernt das Ziel. Die Zielzeit wird in Setup und
öffentlicher Übersicht gesondert **hervorgehoben**. Sie muss nach dem Start und
spätestens 24 Stunden vor dem ursprünglichen Ende und nicht nach dem bereits
beschleunigten Ende liegen. Beliebige Minuten und Sekunden sind zulässig:
Die Wunschzeit wird auf den nächsten erreichbaren Zeitpunkt des Stundenrasters
der Startzeit **aufgerundet**, niemals auf einen früheren Zeitpunkt.
Reset und Setup speichern und zeigen diese gerundete Zielzeit. Dadurch ist
sie mit 1h-Spenden exakt erreichbar. Die angezeigte Endzeit lautet immer
**Start + 216h − gespendete Stunden**.
Bei Start `2026-10-31 10:57` wird beispielsweise `2026-11-3 22:00` zu
`2026-11-3 22:57`; eine bereits passende Zeit bleibt unverändert.
Bei Zeitzonenübergängen ist der tatsächliche Abstand in UTC maßgeblich.
Bei Start am **31.10.2026 10:00** liegt die späteste Zielzeit somit am
**08.11.2026 10:00** (bei gleichbleibendem UTC-Offset).
Nur Optionen, die das Ende nicht vor die Zielzeit verschieben, bleiben zugänglich.
Bei Gleichstand erscheint **Ziel erreicht**, und alle Beschleunigungsbuttons
verschwinden. Auch bereits geöffnete Bestätigungen werden beim Speichern erneut
gegen das aktuelle Ziel geprüft. Die zusätzliche 24-Stunden-Grenze gilt weiterhin;
zu spät begonnene Spenden können das Ziel deshalb möglicherweise nicht mehr erreichen.

| Option | Basispreis | Faktor 2 | Faktor 3 |
| --- | ---: | ---: | ---: |
| 1h | 28 | 56 | 84 |
| 8h | 223 | 446 | 669 |
| 24h | 667 | 1.334 | 2.001 |

Die Berechnung folgt der Formel aus
[`calculated-price.py`](src/hmwz/modules/donation/calculated-price.py):
Unter 72 bereits beschleunigten Stunden gilt grundsätzlich Faktor **1**.
Im Bereich 48–72 Stunden gilt nur dann
`1 + (bisherige Stunden - 48) / 24`, wenn die bisherigen Stunden **plus
gewählte Spendendauer strikt über 72 Stunden** liegen. Von 72 bis 144 Stunden
gilt grundsätzlich Faktor **2**; im Bereich über 120 bis unter 144 Stunden
gilt entsprechend `2 + (bisherige Stunden - 120) / 24`, wenn die Spende
**strikt über 144 Stunden** führt. Ab 144 Stunden gilt Faktor **3**.
Genaues Erreichen einer Grenze löst keinen Übergangszuschlag aus.
Der Basispreis jeder Option wird mit dem Faktor multipliziert und auf ganze
Kristalle **aufgerundet**. Nach dem Speichern werden die gespendeten Stunden
zum Beschleunigungsstand des Zyklus addiert.
Beispiel: Nach 50 beschleunigten Stunden kosten 24h **723**, 8h **223** und
1h **28** Kristalle. Maßgeblich ist die implementierte Referenzformel, nicht
die teilweise abweichenden Beispielkommentare der Referenzdatei.
Die Rush-Schaltflächen **1h**, **8h** und **24h**
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
Bei konfigurierter Zielzeit enthalten Rush-Snapshots zusätzlich `target_at` und
die tatsächliche beschleunigte Endzeit `end_at` als ISO-Zeitstempel.
Mit `/donation snapshot` exportierst du denselben vollständigen aktuellen
Zyklus ohne Reset in den konfigurierten JSON-Exportkanal. Dieser Befehl
erfordert die Berechtigung „Kanäle verwalten“ und einen eingerichteten
Exportkanal. Manuelle Exporte haben den Typ `snapshot`, Reset-Exporte
`cycle-reset`; Beträge werden ohne Genauigkeitsverlust als Zeichenketten
exportiert. Beim Bot-Start oder nach einzelnen Spenden erfolgt kein Export.
Die Implementierungen sind nach Spendenart getrennt:
[`type/credit/`](src/hmwz/modules/donation/type/credit/) enthält Betragseingabe,
Credit-Validierung, Werte-Setup und Reset-Bestätigung;
[`type/rush/`](src/hmwz/modules/donation/type/rush/) enthält Preisberechnung,
Rush-Bestätigung, Zeitvalidierung, Zeitstempel-Setup, Reset und
Rush-Zeitdarstellung. Das gemeinsame Modul leitet die Abläufe an die
konfigurierte Spendenart weiter. SQLite-Repository, Kanalmodelle,
Ranking/Spendenhistorie und JSON-Snapshots bleiben gemeinsam.
`/donation reset` startet den aktuellen Zyklus neu; bei Rush-Spenden legst du
dabei den neuen Start und optional eine neue Zielzeit fest. Ein leeres Zielzeitfeld
setzt den neuen Zyklus ohne Ziel auf; die alte absolute Zielzeit wird nicht
übernommen. Frühere Einträge bleiben im All-Time-Ranking
enthalten. `/donation remove` entfernt nach Bestätigung Einrichtung,
Bot-Nachrichten und alle Spenden des aktuellen Kanals unwiderruflich. Damit das Ranking
vergleichbar bleibt, kann die Einheit nach dem ersten Spenden-Eintrag nicht
mehr geändert werden.

## Installation und Start

Führe Befehle aus dem Projektverzeichnis aus. Das ist wichtig, weil `configuration.json`, die Datenbank und das Log anhand des aktuellen Arbeitsverzeichnisses angesprochen werden.

### Automatische Installation

Die Installationsskripte bündeln separat ausführbare Etappen: virtuelle Umgebung erstellen, Abhängigkeiten installieren, optional den Token konfigurieren und den automatischen Start einrichten. Beim Einrichten kannst du den systemd-Dienstnamen (Linux) beziehungsweise den Aufgabennamen (Windows) festlegen. Linux installiert und startet einen systemd-Dienst; Windows registriert eine Aufgabenplaner-Aufgabe, die beim Anmelden des aktuellen Benutzers startet und sofort gestartet wird. Prüfe ein Skript, bevor du es ausführst.

**Windows (PowerShell):**

```powershell
.\scripts\win\install.ps1
```

**Linux:**

```bash
bash scripts/linux/install.bash
```

Unter Windows läuft die Aufgabe im aktuellen Benutzerkontext, damit sie auf den Token in dessen Registry zugreifen kann. Sie startet beim Benutzer-Login und nicht vor der Anmeldung. Der konfigurierte Name wird für die Start-/Stop-Skripte gespeichert; alternativ kannst du ihn als Parameter `-TaskName` angeben. Stoppen entfernt die Aufgabe nicht.

Die Etappen können einzeln ausgeführt werden:

| Etappe | Windows (PowerShell) | Linux (Bash) |
| --- | --- | --- |
| Virtuelle Umgebung erstellen | `.\scripts\win\create_venv.ps1` | `bash scripts/linux/create_venv.bash` |
| Abhängigkeiten installieren | `.\scripts\win\install_dependencies.ps1` | `bash scripts/linux/install_dependencies.bash` |
| Token optional konfigurieren | `.\scripts\win\configure_token.ps1` | `bash scripts/linux/configure_token.bash` |
| Automatischen Start einrichten | `.\scripts\win\install_service.ps1` | `bash scripts/linux/install_service.bash` |

**Test-Branch (Linux):** Dieser Branch ist für einen Test-Bot parallel zum produktiven Bot gedacht. Der vorgeschlagene Dienstname ist `discordbot-test.service`; bei der Installation kannst du einen anderen wählen. Klone den Branch in ein eigenes Verzeichnis (eigene `venv`) und nutze einen eigenen Bot-Token. `HMWZ_SERVICE_NAME` kann den Dienstnamen vorgeben; `HMWZ_TOKEN_FILE` übergibt optional eine Umgebungsdatei an systemd und muss auf eine vorhandene Datei mit absolutem Pfad zeigen. Ist die Variable leer oder nicht gesetzt, wird keine `EnvironmentFile`-Zeile in die Unit geschrieben. Der konfigurierte Dienstname wird für die Start-/Stop-Skripte gespeichert. Der produktive `discordbot.service` bleibt unberührt.

Die Dienstinstallation unter Linux benötigt `systemd` und `sudo`; führe das Installationsskript als Bot-Benutzer aus, nicht als root. Sie aktiviert den gewählten Dienst beim Systemstart und startet ihn. Verwende `scripts/linux/start_bot_service.bash` zum Neustart und `scripts/linux/stop_bot_service.bash` zum Stoppen; optional kannst du den Dienstnamen als erstes Argument übergeben. Der Dienst bleibt nach dem Stoppen für den nächsten Systemstart aktiviert.

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

`hs.wz.WzModule` ist eine eigenständige, beim Modulmanager registrierte
Kanal- und Rollenverwaltung mit einer gemeinsamen Konfiguration pro Server.
Es benötigt keine Anmeldung und verwendet weder Tabellen noch Übersichten des
`registration`-Moduls. Kanäle liegen in `HsWzChannels`, Rollen in `HsWzRoles`.
Das WZ-Modul verwendet `Channel`, `ChannelRepository` und `module.channels`
für seine Bereinigungskanäle;
vorhandene Daten aus `WzPurgeChannels` werden bei der Schemamigration übernommen.
Die Discord-API-Methode `channel.purge()` bleibt für die Nachrichtenbereinigung
unverändert.

Es sind höchstens 25 WZ-Kanäle und 25 WZ-Rollen pro Server konfigurierbar.
WZ-Rollen haben keine Permanenz-Unterscheidung und können vollständig aus der
Konfiguration entfernt werden. Die frühere `Permanent`-Spalte wird beim
Schema-Upgrade entfernt; die gespeicherten Rollen bleiben erhalten.

Das private WZ-Setup zeigt WZ-Rollen und Bereinigungskanäle in getrennten
Embed-Feldern mit Zählern und Limits.
Die Aktionsschaltflächen sind nach Rollen und Kanälen gruppiert;
„Aktualisieren“ lädt den aktuellen Stand, „Schließen“ beendet das Menü.
Beim Hinzufügen verwendet die Rollen- und Kanalauswahl native
Discord-Auswahlfelder wie das Registrierungs-Setup. Beim Entfernen werden
ausschließlich konfigurierte Elemente angezeigt; historische Listen mit mehr
als 25 Einträgen werden seitenweise dargestellt. Eine Vorschau zeigt die
Auswahl, bevor sie geprüft und bestätigt wird.
Änderungen werden weiterhin erst nach Bestätigung angewendet.

Der wiederverwendbare UI-Helper
[`EntitySelectionView`](src/hmwz/ui/components/entity_selection.py) stellt
native oder gefilterte Rollen- und Textkanalauswahl, Eigentümerprüfung, zulässige IDs,
Auswahllimits und gespeicherte Auswahlwerte bereit. Native Auswahlfelder können
auch nicht zulässige Server-Elemente anzeigen; der Helper weist diese ausdrücklich
ab. Die Modulaktionen prüfen vor dem Speichern erneut den aktuellen Zustand.

Alle WZ-Rückmeldungen und Dialogaktualisierungen verwenden die gemeinsamen
Helper in `hmwz.ui.messages` beziehungsweise `EphemeralView`. Diese bereiten
Nachrichteninhalte mit den Projekt-Emojis auf; Ergebnis- und Fehlermeldungen
werden nur kurzzeitig angezeigt. Discord-Fehler der Dialog-Helper werden an
die aufrufende Fehlerbehandlung weitergegeben.

Bereits in `Registration_Roles` gespeicherte Rollen werden nicht automatisch
als WZ-Rollen übernommen, da sie zu unabhängigen Registrierungen gehören.
WZ-Rollen werden über `/wz setup` konfiguriert. Ingame-Accounts werden vom
Account-Modul weiterhin über das allgemeine Registrierungsmodul verwaltet.

| Befehl | Beschreibung |
| --- | --- |
| `/wz setup` | Öffnet das private WZ-Menü mit direkt sichtbarer Konfiguration und Aktionen zum Hinzufügen und Entfernen von WZ-Rollen und WZ-Kanälen. |
| `/wz reset-channels` | Bereinigt nach Bestätigung die konfigurierten WZ-Kanäle. |
| `/wz reset-roles` | Entfernt nach Bestätigung konfigurierte WZ-Rollen von Servermitgliedern; ausgewählte Ausnahmen bleiben erhalten. |
| `/qs setup` | Öffnet das private QS-Menü mit direkt sichtbarer Konfiguration und Aktionen zum Hinzufügen und Entfernen von QS-Rollen und QS-Kanälen. |
| `/qs reset-channels` | Bereinigt nach Bestätigung die konfigurierten QS-Kanäle. |
| `/qs reset-roles` | Entfernt nach Bestätigung die im aktuellen QS-Kanal konfigurierten Rollen von Servermitgliedern. |

Bei beiden WZ-Reset-Befehlen lassen sich konfigurierte Rollen beziehungsweise
Kanäle als Ausnahmen auswählen. Die Embed-Vorschau trennt betroffene und
ignorierte Elemente mit Zählern; sind alle Elemente ausgenommen, ist die
Bestätigung deaktiviert. Ausnahmen gelten nur für den aktuellen Reset und
ändern die gespeicherte Konfiguration nicht. Beim Kanal-Reset bleiben
angepinnte Nachrichten standardmäßig ausgenommen; dies ist separat umschaltbar.

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

Anmeldungen und ihre Einstellungen werden vom Registrierungsmodul in SQLite gespeichert. Die unabhängigen WZ-Kanäle und -Rollen liegen in eigenen Tabellen, nicht in `configuration.json`. Neue Standardwerte liegen in `hs.wz`; der bisherige Schlüssel `wz_registration` wird für vorhandene Konfigurationsdateien weiterhin gelesen. Verändere die Datei bei gestopptem Bot und sichere vor Änderungen oder Upgrades sowohl sie als auch `data/data.db`.

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
        commands/setup/config/  Setup-Befehl, Entwurf, Konfigurationsanzeige und Views
        models/                 Fachliche Spenden- und Kanalwerte
        repositories/           SQLite-Persistenz der Spenden
        snapshot/               Aufbau und Export vollständiger Zyklus-Snapshots
        type/
          credit/               Credit-Abläufe, Betragseingabe, Validierung und Setup
          rush/                 Rush-Abläufe, Preise, Zeitvalidierung, Setup und Reset
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

`src/bot.py` ist ein schlanker Kompatibilitätseinstiegspunkt, der das Paket `hmwz` startet. Er verändert den Python-Importpfad nicht. Das Paket kann außerdem installiert und mit dem Kommando `hmwz` gestartet werden. `hs.wz`, `hs.qs` und `hs.account` sind getrennte Submodule. Das botweite `registration`-Modul stellt Registrierungsbefehle, Modelle und Logik bereit; QS-spezifische Commands liegen bei `hs.qs`. `hs.wz.WzModule` erbt nur von der Modulbasis und verwaltet ausschließlich seine eigenen Kanal- und Rollentabellen.

## Entwicklung und Tests

Für lokale Entwicklung und Debugging kann die virtuelle Umgebung wie oben angelegt werden. Mit `python -m pip install -e ".[monitoring]"` wird das Paket samt optionalem Ressourcenmonitoring installierbar; anschließend startet `hmwz` den Bot. Alternativ funktioniert aus dem Projektstamm weiterhin `python src/bot.py`. Für die Entwicklung installiere Hatch und führe `hatch run test` für die Tests inklusive Coverage-Bericht oder `hatch run check` für Linting, Formatprüfung, Typprüfung und Tests aus. Einzelne Hatch-Befehle sind `hatch run lint`, `hatch run format`, `hatch run format-check` und `hatch run typecheck`. Die Skripte für Windows und Linux installieren weiterhin `requirements.txt` und verwenden den Kompatibilitätseinstiegspunkt.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [`LICENSE`](./LICENSE).
