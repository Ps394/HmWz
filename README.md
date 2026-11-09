# HmWz

**HmWz** ist ein modularer Discord-Bot für WZ-Anmeldungen, Qs-Planung und
Spendenübersichten im Spiel **Hadestar**. Er stellt interaktive Übersichten
bereit, verwaltet Rollen und speichert Einstellungen sowie Daten serverbezogen
in einer SQLite-Datenbank.

![Beispiel einer Registrierungsübersicht](assets/registration.png)

## Funktionen

- **Registrierungen:** Mehrere Anmeldungen pro Server und Kanal, mit
  konfigurierbaren Rollen sowie An- und Abmeldung über Discord.
- **Spielkonten:** Verknüpfe Ingame-Accounts mit deinem Discord-Mitglied und
  verwalte Registrierungen pro Account.
- **WZ-Verwaltung:** Verwalte WZ-Rollen und Bereinigungskanäle unabhängig von
  den Registrierungen.
- **Qs-Planung:** Richte Eruptionen mit mehreren Phasen ein. Mitglieder können
  sich anmelden und zerstörte Basen melden. Benachrichtigungen sind konfigurierbar.
- **Spendenübersichten:** Erfasse Credit-/Ressourcenspenden oder Rush-Spenden
  mit Bestätigung, Historie und optionalem Ziel.
- **Exporte und Werkzeuge:** Exportiere Registrierungen und Spendenzyklen.
  Moderationsbefehle helfen bei Kanalbereinigung und Serverzeitzone.
- **Lokalisierung und Monitoring:** Slash-Commands unterstützen deutsche und
  englische Lokalisierungen. Optionales Monitoring protokolliert
  Ressourcen-Schwellwertüberschreitungen.

## Dokumentation

- [Installation und Konfiguration](INSTALLATION.md)
- [Slash-Commands und Parameter](COMMANDS.md)

## Projektstruktur

```text
assets/                         Beispielbilder und Vorlagen
scripts/
  linux/                        Linux-Installation und systemd-Steuerung
  win/                          Windows-Installation und Aufgabenplaner
src/
  bot.py                        Einstiegspunkt
  hmwz/
    client/                     Discord-Client, Commands und Monitoring
    i18n/                       Übersetzungen und Command-Lokalisierungen
    modules/
      donation/                 Spendenübersichten, Historie und Exporte
      registration/             Registrierungen, Rollen und Exporte
      hs/
        account/                Account-Kommandos und Account-Datenzugriff
        qs/                     Qs-Planung und Basenmeldungen
        wz/                     WZ-Kanal- und Rollenverwaltung
    ui/                         Gemeinsame Discord-Dialoge und Komponenten
tests/                          Unit- und Integrationstests
configuration.json              Laufzeitkonfiguration
requirements.txt                Laufzeitabhängigkeiten
pyproject.toml                  Paket-, Hatch-, Lint- und Testkonfiguration
```

## Mitwirken

Hinweise zum Einrichten der Entwicklungsumgebung und zum Ausführen der Tests
stehen in der [Installationsanleitung](INSTALLATION.md#entwicklungsumgebung-und-tests).

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [`LICENSE`](LICENSE).
