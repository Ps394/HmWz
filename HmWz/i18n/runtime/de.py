from ..type import Translation
from ...emojis import Emojis

translation : Translation = {
        "command.error.generic": f"{Emojis.ERROR.value} Es ist ein Fehler bei der Ausführung des Befehls aufgetreten.",
        "command.error.permissions": f"{Emojis.WARNING.value} Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.",
        "command.error.cooldown": f"{Emojis.ERROR.value} Warte {{retry_after}} Sekunden, bevor du diesen Befehl erneut verwenden kannst.",
        "command.error.bot_permissions": f"{Emojis.ERROR.value} Mir fehlen die erforderlichen Berechtigungen, um diesen Befehl auszuführen.",
        "command.error.not_found": f"{Emojis.WARNING.value} Der angeforderte Befehl oder die Ressource wurde nicht gefunden.",
        "command.error.invalid_input": f"{Emojis.WARNING.value} Ungültige Eingabe. Bitte überprüfe deine Eingaben und versuche es erneut.",
        "command.error.unexpected": f"{Emojis.ERROR.value} Ein unerwarteter Fehler ist aufgetreten.",
        "wz.registration.error.not_configured": f"{Emojis.WARNING.value} Die WZ-Registrierung ist nicht konfiguriert.",
        # About-Me 
        "wz.about.title": "### {bot_name}",
        "wz.about.line1": "- Ich bin ein in Python geschriebener Discord-Bot, der speziell für die Verwaltung von WZ-Registrierungen entwickelt wurde.",
        "wz.about.line2": "- Meine Aufgabe ist es, Anmeldungen komfortabel zu gestalten, indem ich automatisierte Prozesse, Übersichten und Ausdrücke bereitstelle.",
        "wz.about.line3": "- Ich stehe unter der MIT-Lizenz, was bedeutet, dass du mich kostenlos nutzen, modifizieren und weiterverbreiten kannst, solange du die ursprünglichen Urheberrechtsvermerke und Lizenzhinweise beibehältst.",
        "wz.about.line4": "- Meine Github-Seite ist öffentlich zugänglich, und ich lade alle ein, den Code zu prüfen, Fehler zu melden oder zum Projekt beizutragen.",
        "wz.about.link": "  - [HmWZ GitHub Repository](https://github.com/Ps394/HmWz)",
        # Wz Registration CSV
        "wz.registration.csv.success": f"{Emojis.SUCCESS.value} Die Registrierungen wurden als CSV-Datei exportiert.",
        "wz.registration.csv.error": f"{Emojis.ERROR.value} Es ist ein Fehler beim Exportieren der Registrierungen als CSV-Datei aufgetreten.",
        "wz.registration.csv.no_registrations": f"{Emojis.WARNING.value} Es sind keine Registrierungen zum Exportieren vorhanden.",
        # Wz Registration Reset
        "wz.registration.reset.success": f"{Emojis.SUCCESS.value} Alle nicht permanenten Registrierungen wurden zurückgesetzt.",
        "wz.registration.reset.error": f"{Emojis.ERROR.value} Beim Zurücksetzen der Registrierungen ist ein Fehler aufgetreten.",
        # Wz Setup Configure
        "wz.setup.configure.success": f"{Emojis.SUCCESS.value} WZ-Registrierung wurde erfolgreich eingerichtet. \nChannel: {{channel_name}}",
        "wz.setup.configure.error": f"{Emojis.ERROR.value} Fehler beim Einrichten der WZ-Registrierung.",
        "wz.setup.configure.error_role_hierarchy": f"{Emojis.ERROR.value} Die angegebene Rolle ist höher als die Bot-Rolle. Bitte wähle eine andere Rolle oder ändere die Bot-Rollenhierarchie.",
        "wz.setup.configure.error_no_configured_role": f"{Emojis.ERROR.value} Es muss mindestens eine Rolle für die WZ-Registrierung festgelegt sein, wenn kein Kanal konfiguriert ist.",

        # Wz Setup Roles
        "wz.setup.roles.add.error": f"{Emojis.ERROR.value} Fehler beim Hinzufügen der Rolle zur WZ-Registrierung.",
        "wz.setup.roles.add.max_roles": f"{Emojis.WARNING.value} Es können maximal {{max_roles}} Rollen für die WZ-Registrierung festgelegt werden.",
        "wz.setup.roles.add.success": f"{Emojis.SUCCESS.value} Rolle {{role_name}} wurde zur WZ-Registrierung hinzugefügt.",
        "wz.setup.roles.add.error.role_hierarchy": f"{Emojis.ERROR.value} Die angegebene Rolle ist höher als die Bot-Rolle. Bitte wähle eine andere Rolle oder ändere die Bot-Rollenhierarchie.",
        "wz.setup.roles.remove.error": f"{Emojis.ERROR.value} Fehler beim Entfernen der Rolle aus der WZ-Registrierung.",   
        "wz.setup.roles.remove.unknown_role": f"{Emojis.WARNING.value} Unbekannte Rolle. Bitte wähle eine Rolle aus der Autovervollständigung aus.",
        "wz.setup.roles.remove.min_roles": f"{Emojis.WARNING.value} Es muss mindestens eine Rolle für die WZ-Registrierung festgelegt sein.",
        "wz.setup.roles.remove.success": f"{Emojis.SUCCESS.value} Rolle {{role_name}} wurde aus der WZ-Registrierung entfernt.",
        "wz.setup.roles.remove.unexpected": f"{Emojis.ERROR.value} Unerwarteter Fehler beim Entfernen der Rolle aus der WZ-Registrierung.",

        # Wz Setup Message
        "wz.setup.message.success": f"{Emojis.SUCCESS.value} Nachricht für die WZ-Registrierung wurde erfolgreich festgelegt.",
        "wz.setup.message.no_input": f"{Emojis.ERROR.value} Übergebe zumindest eine der Optionen: title, message oder message_upload.",
        "wz.setup.message.two_messages": f"{Emojis.ERROR.value} Bitte übergebe nur eine der Optionen: message oder message_upload. title kann optional mit einer der beiden übergeben werden.",
        "wz.setup.message.error": f"{Emojis.ERROR.value} Fehler beim Festlegen der Nachricht für die WZ-Registrierung.",
        "wz.setup.message.error_file_type": f"{Emojis.ERROR.value} Ungültiger Dateityp. Bitte lade eine Textdatei (.txt) hoch.",

        # Registration Overview
        "wz.overview.registration.new_registration": f"{Emojis.REGISTER.value} Anmeldung mit **{{role_name}}** erfolgreich.",
        "wz.overview.registration.update_registration": f"{Emojis.REREGISTER.value} Aktualisierung auf **{{role_name}}** erfolgreich.",
        "wz.overview.registration.remove_registration": f"{Emojis.UNREGISTER.value} Abmeldung von **{{role_name}}** erfolgreich.",
        "wz.overview.registration.error_registration" : f"{Emojis.ERROR.value} Fehler bei der Verarbeitung der Anmeldung."
}
