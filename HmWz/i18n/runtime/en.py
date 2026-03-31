from ..type import Translation
from ...emojis import Emojis

translation : Translation = {
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
