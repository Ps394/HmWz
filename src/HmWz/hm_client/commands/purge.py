from discord import Interaction, TextChannel, Thread, app_commands
from discord.app_commands import command, describe, locale_str

from hmwz.i18n import CommandLocalizations, t

__all__ = ["Purge"]


@command(
    name="purge",
    description=locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.purge", "Delete messages in the current channel"
        ),
        key="wz.purge.description",
    ),
)
@app_commands.checks.bot_has_permissions(moderate_members=True, manage_messages=True)
@describe(
    limit=locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.purge.limit", "-"
        ),
        key="wz.purge.limit.description",
    ),
    ignore_bots=locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.purge.ignore_bots", "-"
        ),
        key="wz.purge.ignore_bots.description",
    ),
    ignore_pinned=locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.purge.ignore_pinned", "-"
        ),
        key="wz.purge.ignore_pinned.description",
    ),
    ephemeral=locale_str(
        CommandLocalizations.get("en", {}).get("parameter.description.ephemeral", "-"),
        key="ephemeral.description",
    ),
)
async def Purge(
    interaction: Interaction,
    limit: int = 500,
    ignore_bots: bool = True,
    ignore_pinned: bool = True,
    ephemeral: bool = True,
):
    channel = interaction.channel

    # Purging can take longer than the 3s interaction token timeout, so defer first
    await interaction.response.defer(ephemeral=ephemeral)

    if not isinstance(channel, (TextChannel, Thread)):
        await interaction.followup.send(
            t(interaction, "command.error.invalid_input"), ephemeral=ephemeral
        )
        return

    deleted = await channel.purge(
        limit=limit,
        check=lambda m: (
            (not ignore_bots or not m.author.bot)
            and (not ignore_pinned or not m.pinned)
        ),
        reason=f"Purged by {interaction.user}",
    )
    message = t(interaction, "wz.purge.message", deleted_count=len(deleted))
    if ignore_pinned:
        message += t(interaction, "wz.purge.ignored_pinned")
    if ignore_bots:
        message += t(interaction, "wz.purge.ignored_bots")

    await interaction.followup.send(message, ephemeral=ephemeral)
