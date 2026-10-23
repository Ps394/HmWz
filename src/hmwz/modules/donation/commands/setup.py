from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import t
from hmwz.modules.donation.module import DonationModule

_logger = logging.getLogger(__name__)


@checks.has_permissions(manage_channels=True)
@checks.bot_has_permissions(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
)
class DonationSetupGroup(Group):
    """Administrative commands for donation channels and types."""

    def __init__(self) -> None:
        super().__init__(
            name="setup",
            description=locale_str("Spendenkanäle und Spendenarten einrichten"),
        )
        self.add_command(add_type)
        self.add_command(remove_type)
        self.add_command(configure_channel)
        self.add_command(remove_channel)


@app_commands.command(
    name="art-hinzufuegen",
    description="Eine Spendenart hinzufügen",
)
@app_commands.describe(
    name="Name der Spendenart, zum Beispiel Credits oder Kristalle",
    zusatzfeld="Optionales zweites Feld, zum Beispiel Zeit",
)
async def add_type(
    interaction: discord.Interaction, name: str, zusatzfeld: str | None = None
) -> None:
    """Configure a donation type with one or two donor-provided values."""
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    manager = getattr(interaction.client, "module_manager", None)
    cleaned_name = name.strip()
    cleaned_extra = zusatzfeld.strip() if zusatzfeld else None
    if (
        guild is None
        or manager is None
        or not cleaned_name
        or len(cleaned_name) > 100
        or (zusatzfeld is not None and not cleaned_extra)
        or (cleaned_extra is not None and len(cleaned_extra) > 45)
    ):
        await _respond(interaction, t(interaction, "donation.error.invalid_type"))
        return

    module: DonationModule = await manager.get_module(guild, DonationModule)
    if len(await module.donations.get_types(guild=guild)) >= 25:
        await _respond(interaction, t(interaction, "donation.error.too_many_types"))
        return
    if not await module.donations.add_type(
        guild=guild, name=cleaned_name, extra_field=cleaned_extra
    ):
        await _respond(interaction, t(interaction, "donation.error.type_exists"))
        return

    refresh_success = await _refresh_overviews(module)
    await _respond(
        interaction,
        t(
            interaction,
            (
                "donation.setup.type_added"
                if refresh_success
                else "donation.setup.type_added_refresh_failed"
            ),
            name=cleaned_name,
        ),
    )


@app_commands.command(
    name="art-entfernen",
    description="Eine Spendenart entfernen",
)
@app_commands.describe(name="Name der Spendenart, die entfernt werden soll")
async def remove_type(interaction: discord.Interaction, name: str) -> None:
    """Remove a configured donation type while preserving past donations."""
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or manager is None:
        await _respond(interaction, t(interaction, "donation.error.invalid_type"))
        return
    module: DonationModule = await manager.get_module(guild, DonationModule)
    if not await module.donations.remove_type(guild=guild, name=name.strip()):
        await _respond(interaction, t(interaction, "donation.error.type_missing"))
        return
    refresh_success = await _refresh_overviews(module)
    await _respond(
        interaction,
        t(
            interaction,
            (
                "donation.setup.type_removed"
                if refresh_success
                else "donation.setup.type_removed_refresh_failed"
            ),
            name=name.strip(),
        ),
    )


@app_commands.command(
    name="kanal",
    description="Spendenübersicht im aktuellen Kanal einrichten",
)
async def configure_channel(interaction: discord.Interaction) -> None:
    """Enable donations in the current text channel."""
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    channel = interaction.channel
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or manager is None or not isinstance(channel, discord.TextChannel):
        await _respond(interaction, t(interaction, "donation.error.text_channel_only"))
        return
    module: DonationModule = await manager.get_module(guild, DonationModule)
    if not await module.donations.get_types(guild=guild):
        await _respond(
            interaction, t(interaction, "donation.error.configure_type_first")
        )
        return
    if not await module.configure_channel(channel.id):
        await _respond(interaction, t(interaction, "donation.error.channel_setup"))
        return
    await _respond(
        interaction,
        t(
            interaction,
            "donation.setup.channel_added",
            channel_name=channel.mention,
        ),
    )


@app_commands.command(
    name="kanal-entfernen",
    description="Spendenübersicht im aktuellen Kanal deaktivieren",
)
async def remove_channel(interaction: discord.Interaction) -> None:
    """Disable donations in the current channel without deleting history."""
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await _respond(interaction, t(interaction, "donation.error.not_configured"))
        return
    module: DonationModule = await manager.get_module(guild, DonationModule)
    if not await module.remove_channel(channel_id):
        await _respond(interaction, t(interaction, "donation.error.not_configured"))
        return
    await _respond(interaction, t(interaction, "donation.setup.channel_removed"))


async def _refresh_overviews(module: DonationModule) -> bool:
    """Refresh every configured overview after a donation type change."""
    results = [
        await module.compose_overview(channel_id)
        for channel_id in await module.donations.get_channels(guild=module.guild)
    ]
    if not all(results):
        _logger.error(
            "%s Failed to refresh every donation overview after a type change.",
            module.guild.name,
        )
        return False
    return True


async def _respond(interaction: discord.Interaction, message: str) -> None:
    """Send an ephemeral follow-up after a setup command has been deferred."""
    await interaction.followup.send(message, ephemeral=True)
