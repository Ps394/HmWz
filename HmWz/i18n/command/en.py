from ..type import Translation

translation : Translation = {
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
    }