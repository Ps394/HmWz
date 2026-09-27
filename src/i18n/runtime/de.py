from ..type import Translation
import hmEmojis

translation : Translation = {
        "command.error.generic": f"{hmEmojis.ERROR} Es ist ein Fehler bei der Ausführung des Befehls aufgetreten.",
        "command.error.permissions": f"{hmEmojis.WARNING} Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.",
        "command.error.cooldown": f"{hmEmojis.ERROR} Warte {{retry_after}} Sekunden, bevor du diesen Befehl erneut verwenden kannst.",
        "command.error.bot_permissions": f"{hmEmojis.ERROR} Mir fehlen die erforderlichen Berechtigungen, um diesen Befehl auszuführen.",
        "command.error.not_found": f"{hmEmojis.WARNING} Der angeforderte Befehl oder die Ressource wurde nicht gefunden.",
        "command.error.invalid_input": f"{hmEmojis.WARNING} Ungültige Eingabe. Bitte überprüfe deine Eingaben und versuche es erneut.",
        "command.error.unexpected": f"{hmEmojis.ERROR} Ein unerwarteter Fehler ist aufgetreten.",
        "wz.registration.error.not_configured": f"{hmEmojis.WARNING} Die WZ-Registrierung ist nicht konfiguriert.",
        "wz.purge.message": f"{hmEmojis.DELETE} {{deleted_count}} Nachrichten wurden gelöscht.",
        "wz.purge.ignored_pinned": " Angeheftete Nachrichten wurden ignoriert.",
        "wz.purge.ignored_bots": " Nachrichten von Bots wurden ignoriert.",
        # About-Me 
        "wz.about.title": "### {bot_name}",
        "wz.about.line1": "- Ich bin ein in Python geschriebener Discord-Bot, der speziell für die Verwaltung von WZ-Registrierungen entwickelt wurde.",
        "wz.about.line2": "- Meine Aufgabe ist es, Anmeldungen komfortabel zu gestalten, indem ich automatisierte Prozesse, Übersichten und Ausdrücke bereitstelle.",
        "wz.about.line3": "- Ich stehe unter der MIT-Lizenz, was bedeutet, dass du mich kostenlos nutzen, modifizieren und weiterverbreiten kannst, solange du die ursprünglichen Urheberrechtsvermerke und Lizenzhinweise beibehältst.",
        "wz.about.line4": "- Meine Github-Seite ist öffentlich zugänglich, und ich lade alle ein, den Code zu prüfen, Fehler zu melden oder zum Projekt beizutragen.",
        "wz.about.link": "- [HmWZ GitHub Repository](https://github.com/Ps394/HmWz)",
        # Wz Registration CSV
        "wz.registration.csv.success": f"{hmEmojis.SUCCESS} Die Registrierungen wurden als CSV-Datei exportiert.",
        "wz.registration.csv.error": f"{hmEmojis.ERROR} Es ist ein Fehler beim Exportieren der Registrierungen als CSV-Datei aufgetreten.",
        "wz.registration.csv.no_registrations": f"{hmEmojis.WARNING} Es sind keine Registrierungen zum Exportieren vorhanden.",
        # Wz Registration Reset
        "wz.registration.reset.success": f"{hmEmojis.SUCCESS} Alle nicht permanenten Registrierungen wurden zurückgesetzt.",
        "wz.registration.reset.error": f"{hmEmojis.ERROR} Beim Zurücksetzen der Registrierungen ist ein Fehler aufgetreten.",
        # Wz Setup Configure
        "wz.setup.configure.success": f"{hmEmojis.SUCCESS} WZ-Registrierung wurde erfolgreich eingerichtet. \nChannel: {{channel_name}}",
        "wz.setup.configure.error": f"{hmEmojis.ERROR} Fehler beim Einrichten der WZ-Registrierung.",
        "wz.setup.configure.error_role_hierarchy": f"{hmEmojis.ERROR} Die angegebene Rolle ist höher als die Bot-Rolle. Bitte wähle eine andere Rolle oder ändere die Bot-Rollenhierarchie.",
        "wz.setup.configure.error_no_configured_role": f"{hmEmojis.ERROR} Es muss mindestens eine Rolle für die WZ-Registrierung festgelegt sein, wenn kein Kanal konfiguriert ist.",

        # Wz Setup Roles
        "wz.setup.roles.add.error": f"{hmEmojis.ERROR} Fehler beim Hinzufügen der Rolle zur WZ-Registrierung.",
        "wz.setup.roles.add.max_roles": f"{hmEmojis.WARNING} Es können maximal {{max_roles}} Rollen für die WZ-Registrierung festgelegt werden.",
        "wz.setup.roles.add.success": f"{hmEmojis.SUCCESS} Rolle {{role_name}} wurde zur WZ-Registrierung hinzugefügt.",
        "wz.setup.roles.add.error.role_hierarchy": f"{hmEmojis.ERROR} Die angegebene Rolle ist höher als die Bot-Rolle. Bitte wähle eine andere Rolle oder ändere die Bot-Rollenhierarchie.",
        "wz.setup.roles.remove.error": f"{hmEmojis.ERROR} Fehler beim Entfernen der Rolle aus der WZ-Registrierung.",   
        "wz.setup.roles.remove.unknown_role": f"{hmEmojis.WARNING} Unbekannte Rolle. Bitte wähle eine Rolle aus der Autovervollständigung aus.",
        "wz.setup.roles.remove.min_roles": f"{hmEmojis.WARNING} Es muss mindestens eine Rolle für die WZ-Registrierung festgelegt sein.",
        "wz.setup.roles.remove.success": f"{hmEmojis.SUCCESS} Rolle {{role_name}} wurde aus der WZ-Registrierung entfernt.",
        "wz.setup.roles.remove.unexpected": f"{hmEmojis.ERROR} Unerwarteter Fehler beim Entfernen der Rolle aus der WZ-Registrierung.",

        # Wz Setup Message
        "wz.setup.message.success": f"{hmEmojis.SUCCESS} Nachricht für die WZ-Registrierung wurde erfolgreich festgelegt.",
        "wz.setup.message.no_input": f"{hmEmojis.ERROR} Übergebe zumindest eine der Optionen: title, message oder message_upload.",
        "wz.setup.message.two_messages": f"{hmEmojis.ERROR} Bitte übergebe nur eine der Optionen: message oder message_upload. title kann optional mit einer der beiden übergeben werden.",
        "wz.setup.message.error": f"{hmEmojis.ERROR} Fehler beim Festlegen der Nachricht für die WZ-Registrierung.",
        "wz.setup.message.error_file_type": f"{hmEmojis.ERROR} Ungültiger Dateityp. Bitte lade eine Textdatei (.txt) hoch.",

        # Registration Overview
        "wz.overview.default_title": "Anmeldung",
        "wz.overview.default_description": "Bitte registriere dich fuer die Teilnahme am WZ-Event.",
        "wz.overview.list.title": "{page}. Anmeldungen: {total} ( {perma_emoji}: {permanent_count} | {normal_emoji}: {non_permanent_count} )",
        "wz.overview.registration.new_registration": f"{hmEmojis.REGISTER} Anmeldung mit **{{role_name}}** erfolgreich.",
        "wz.overview.registration.update_registration": f"{hmEmojis.REREGISTER} Aktualisierung auf **{{role_name}}** erfolgreich.",
        "wz.overview.registration.remove_registration": f"{hmEmojis.UNREGISTER} Abmeldung von **{{role_name}}** erfolgreich.",
        "wz.overview.registration.error_registration" : f"{hmEmojis.ERROR} Fehler bei der Verarbeitung der Anmeldung."
}
