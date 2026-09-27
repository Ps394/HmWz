from discord.app_commands import command, locale_str
from discord import Interaction, TextChannel
from i18n import CommandLocalizations, t

__all__ = [
    "Purge"
]

@command(
    name="purge",
    description=locale_str(
        CommandLocalizations.get("en", {}).get("wz.purge.description", "Delete messages in the current channel"),
        key="wz.purge.description"
    )
)
async def Purge(interaction: Interaction, limit: int = 500, ignore_bots: bool = True, ignore_pinned: bool = True, ephemeral: bool = True):
    channel = interaction.channel

    # Purging can take longer than the 3s interaction token timeout, so defer first
    await interaction.response.defer(ephemeral=ephemeral)

    if channel is not None and isinstance(channel, TextChannel):
        deleted = await channel.purge(
            limit=limit,
            check=lambda m: (not ignore_bots or not m.author.bot) and (not ignore_pinned or not m.pinned),
            reason=f"Purged by {interaction.user}"
        )
    message = t(interaction, 'wz.purge.message', deleted_count=len(deleted))
    if ignore_pinned:
        message += t(interaction, 'wz.purge.ignored_pinned')
    if ignore_bots:
        message += t(interaction, 'wz.purge.ignored_bots')

    await interaction.followup.send(
        message,
        ephemeral=ephemeral
    )




