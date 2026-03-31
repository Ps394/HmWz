from typing import Dict
from ..emojis import Emojis

locals: Dict[str, Dict[str, str]] = {
    "de": {
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
    },
        "en": {
        "command.error.generic": f"{Emojis.ERROR.value} An error occurred while executing the command.",
        "command.error.permissions": f"{Emojis.WARNING.value} You do not have the required permissions to execute this command.",
        "command.error.cooldown": f"{Emojis.ERROR.value} Please wait {{retry_after}} seconds before using this command again.",
        "command.error.bot_permissions": f"{Emojis.ERROR.value} I lack the required permissions to execute this command.",
        "command.error.not_found": f"{Emojis.WARNING.value} The requested command or resource was not found.",
        "command.error.invalid_input": f"{Emojis.WARNING.value} Invalid input. Please check your entries and try again.",
        "command.error.unexpected": f"{Emojis.ERROR.value} An unexpected error occurred.",
        "wz.registration.error.not_configured": f"{Emojis.WARNING.value} The WZ registration is not configured.",
        # About-Me
        "wz.about.title": "### {bot_name}",
        "wz.about.line1": "- I am a Discord bot written in Python, built specifically for managing WZ registrations.",
        "wz.about.line2": "- My goal is to make registrations easier by providing automated processes, overviews, and workflows.",
        "wz.about.line3": "- I am released under the MIT License, so you can use, modify, and redistribute me for free as long as the original copyright and license notices are kept.",
        "wz.about.line4": "- My GitHub page is public, and everyone is welcome to review the code, report issues, or contribute to the project.",
        "wz.about.link": "  - [HmWZ GitHub Repository](https://github.com/Ps394/HmWz)",
        # Wz Registration CSV
        "wz.registration.csv.success": f"{Emojis.SUCCESS.value} The registrations have been exported as a CSV file.",
        "wz.registration.csv.error": f"{Emojis.ERROR.value} An error occurred while exporting the registrations as a CSV file.",
        "wz.registration.csv.no_registrations": f"{Emojis.WARNING.value} There are no registrations to export.",
        # Wz Registration Reset
        "wz.registration.reset.success": f"{Emojis.SUCCESS.value} All non-permanent registrations have been reset.",
        "wz.registration.reset.error": f"{Emojis.ERROR.value} An error occurred while resetting the registrations.",
       # Wz Setup Configure
        "wz.setup.configure.success": f"{Emojis.SUCCESS.value} WZ registration has been configured successfully.\nChannel: {{channel_name}}",
        "wz.setup.configure.error": f"{Emojis.ERROR.value} An error occurred while configuring the WZ registration.",
        "wz.setup.configure.error_role_hierarchy": f"{Emojis.ERROR.value} The specified role is higher than the bot's role. Please choose a different role or change the bot's role hierarchy.",
        "wz.setup.configure.error_no_configured_role": f"{Emojis.ERROR.value} At least one role must be set for WZ registration if no channel is configured.",

        # Wz Setup Roles
        "wz.setup.roles.add.error": f"{Emojis.ERROR.value} An error occurred while adding the role to the WZ registration.",
        "wz.setup.roles.add.max_roles": f"{Emojis.WARNING.value} A maximum of {{max_roles}} roles can be set for WZ registration.",
        "wz.setup.roles.add.success": f"{Emojis.SUCCESS.value} Role {{role_name}} has been added to the WZ registration.",
        "wz.setup.roles.add.error.role_hierarchy": f"{Emojis.ERROR.value} The specified role is higher than the bot's role. Please choose a different role or change the bot's role hierarchy.",
        "wz.setup.roles.remove.error": f"{Emojis.ERROR.value} An error occurred while removing the role from the WZ registration.",   
        "wz.setup.roles.remove.unknown_role": f"{Emojis.WARNING.value} Unknown role. Please choose a role from the autocomplete.",
        "wz.setup.roles.remove.min_roles": f"{Emojis.WARNING.value} At least one role must be set for WZ registration.",
        "wz.setup.roles.remove.success": f"{Emojis.SUCCESS.value} Role {{role_name}} has been removed from the WZ registration.",
        "wz.setup.roles.remove.unexpected": f"{Emojis.ERROR.value} An unexpected error occurred while removing the role from the WZ registration.",  
        
        # Wz Setup Message
        "wz.setup.message.success": f"{Emojis.SUCCESS.value} Message for WZ registration has been set successfully.",
        "wz.setup.message.no_input": f"{Emojis.ERROR.value} Please provide at least one of the options: title, message or message_upload.",
        "wz.setup.message.two_messages": f"{Emojis.ERROR.value} Please provide only one of the options: message or message_upload. title can optionally be provided with either of them.",
        "wz.setup.message.error": f"{Emojis.ERROR.value} An error occurred while setting the message for WZ registration.",
        "wz.setup.message.error_file_type": f"{Emojis.ERROR.value} Invalid file type. Please upload a text file (.txt).",

        # Registration Overview
        "wz.overview.registration.new_registration": f"{Emojis.REGISTER.value} Signed up with **{{role_name}}** successfully.",
        "wz.overview.registration.update_registration": f"{Emojis.REREGISTER.value} Updated to **{{role_name}}** successfully.",
        "wz.overview.registration.remove_registration": f"{Emojis.UNREGISTER.value} Signed out from **{{role_name}}** successfully.",
        "wz.overview.registration.error_registration" : f"{Emojis.ERROR.value} Error processing registration."
    
    }
}
"""Enthält alle statischen Texte, die in den Befehlen verwendet werden. 
Die Texte sind in verschiedenen Sprachen organisiert, um die Lokalisierung zu unterstützen. 
Die `CommandLocalizations`-Datenstruktur enthält Übersetzungen für Befehlsbeschreibungen und andere statische Texte, während die `RuntimeMessages`-Datenstruktur Übersetzungen für Nachrichten enthält, die zur Laufzeit generiert werden.
""" 
