from typing import Dict


locals: Dict[str, Dict[str, str]] = {
    "de": {
        "ephemeral.description": "Festlegen, ob die Antwort privat sein soll",
        # Wz Group
        "wz.group.description": "HmWz - Alle Befehle rund um die WZ-Registrierung",
        "wz.about.description": "Über den Bot",
        # Wz Registration 
        "wz.registration.group.description": "Befehle für die WZ-Registrierung",
        "wz.registration.csv.description": "Gibt die Registrierungen als CSV-Datei aus",
        "wz.registration.reset.description": "Entfernt nicht permanente Registrierungen.",
        # Wz Setup 
        "wz.setup.group.description": "Setup-Befehle für die WZ-Registrierung",
    
        "wz.setup.configure.description": "Einrichten der WZ-Registrierung für diesen Server",
        "wz.setup.configure.channel.description": "Registrierungskanal",
        "wz.setup.configure.role.description": "Registrierungsrolle (optional, sofern mindestens eine vorhanden ist)",
    
        "wz.setup.roles.add.description": "Anmeldungsrolle hinzufügen (maximal 4 Rollen möglich)",
        "wz.setup.roles.add.role.description": "Registrierungsrolle",
        "wz.setup.roles.add.permanent.description": "True für Permanente Rollen (optional, Standard: false)",
        "wz.setup.roles.remove.description": "Entfernt eine Registrierungsrolle",
        "wz.setup.roles.remove.role.description": "Registrierungsrolle, die entfernt werden soll",
        
        "wz.setup.message.description": "Lege die Nachricht für die WZ-Registrierung fest.",
        "wz.setup.message.title.description": "Titel für die Nachricht (max. 256 Zeichen)",
        "wz.setup.message.message.description": "Text für die Nachricht (max. 4096 Zeichen)",
        "wz.setup.message.message_upload.description": "TXT-Datei (UTF-8 codiert) mit der Nachricht (max. 4096 Zeichen)",
    },
    "en": {
        "ephemeral.description": "Set whether the response should be ephemeral",
        # Wz 
        "wz.group.description": "HmWz - All commands related to WZ registration",
        "wz.about.description": "Information about the bot and its features",
        # Wz Registration 
        "wz.registration.group.description": "Commands for WZ registration",
        "wz.registration.csv.description": "Export registrations as CSV",
        "wz.registration.reset.description": "Remove non-permanent registrations.",
        # Wz Setup
        "wz.setup.group.description": "Setup commands for WZ registration",
                
        "wz.setup.configure.description": "Configure the WZ registration for this server",
        "wz.setup.configure.channel.description": "Registration channel",
        "wz.setup.configure.role.description": "Registration role (optional if at least one already exists)",

        "wz.setup.roles.add.description": "Add registration role (max 4 roles possible)",
        "wz.setup.roles.add.role.description": "Registration role",
        "wz.setup.roles.add.permanent.description": "True for permanent roles (optional, default: false)",
        "wz.setup.roles.remove.description": "Remove a registration role",
        "wz.setup.roles.remove.role.description": "Registration role to remove",

        "wz.setup.message.description": "Set the message for the WZ registration.",
        "wz.setup.message.title.description": "Title for the message (max. 256 characters)",
        "wz.setup.message.message.description": "Text for the message (max. 4096 characters)",
        "wz.setup.message.message_upload.description": "TXT file (UTF-8 encoded) containing the message (max. 4096 characters)",
    },
}
"""Enthält alle statischen Texte, die in den Befehlen verwendet werden. 
Die Texte sind in verschiedenen Sprachen organisiert, um die Lokalisierung zu unterstützen.
Die `CommandLocalizations`-Datenstruktur enthält Übersetzungen für Befehlsbeschreibungen und andere statische Texte, während die `RuntimeMessages`-Datenstruktur Übersetzungen für Nachrichten enthält, die zur Laufzeit generiert werden.
"""