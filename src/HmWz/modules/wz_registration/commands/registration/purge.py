import logging

import discord
from discord import HTTPException, Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


class PurgeConfirmationView(discord.ui.View):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        owner_id: int,
        channels: tuple[tuple[int, discord.TextChannel | None], ...],
        ephemeral: bool,
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.owner_id = owner_id
        self.channels = channels
        self.ephemeral = ephemeral
        self.message: discord.Message | None = None

        confirm_button, cancel_button = self.children
        if isinstance(confirm_button, discord.ui.Button):
            confirm_button.label = t(guild, "wz.registration.purge.confirm_button")
        if isinstance(cancel_button, discord.ui.Button):
            cancel_button.label = t(guild, "wz.registration.purge.cancel_button")

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.registration.purge.confirmation_owner"),
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.delete()
            except HTTPException:
                logger.warning("Failed to delete timed-out WZ purge confirmation.")

    async def _delete_dialog(self, interaction: Interaction) -> None:
        try:
            await interaction.delete_original_response()
        except HTTPException:
            logger.warning("Failed to delete WZ purge confirmation dialog.")

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(
        self, interaction: Interaction, button: discord.ui.Button
    ) -> None:
        button.disabled = True
        await interaction.response.defer(ephemeral=self.ephemeral)
        self.stop()
        await self._delete_dialog(interaction)

        try:
            deleted_count = 0
            failed_channels: list[int] = []
            channel_results: list[str] = []
            for channel_id, channel in self.channels:
                if channel is None:
                    failed_channels.append(channel_id)
                    channel_results.append(
                        t(
                            interaction,
                            "wz.registration.purge.channel_failed",
                            channel=t(
                                interaction,
                                "wz.registration.purge.unavailable_channel",
                                channel_id=channel_id,
                            ),
                        )
                    )
                    continue
                try:
                    deleted = await channel.purge(
                        limit=500,
                        check=lambda message: (
                            not message.pinned and not message.author.bot
                        ),
                        reason="WZ Registration Purge",
                    )
                    deleted_count += len(deleted)
                    channel_results.append(
                        t(
                            interaction,
                            "wz.registration.purge.channel_success",
                            channel=channel.mention,
                            deleted_count=len(deleted),
                        )
                    )
                except HTTPException:
                    logger.exception(
                        "Failed to purge WZ channel %s in guild %s.",
                        channel_id,
                        self.guild.id,
                    )
                    failed_channels.append(channel_id)
                    channel_results.append(
                        t(
                            interaction,
                            "wz.registration.purge.channel_failed",
                            channel=channel.mention,
                        )
                    )

            await interaction.followup.send(
                t(
                    interaction,
                    "wz.registration.purge.success",
                    deleted_count=deleted_count,
                    failed_count=len(failed_channels),
                ),
                embed=discord.Embed(description="\n".join(channel_results)),
                ephemeral=self.ephemeral,
            )
            if failed_channels:
                logger.warning(
                    "WZ purge completed with inaccessible/failed channels in guild %s: %s",
                    self.guild.id,
                    ", ".join(map(str, failed_channels)),
                )
        except Exception:
            logger.exception("WZ configured-channel purge failed.")
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.error"), ephemeral=True
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(
        self, interaction: Interaction, _button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.defer()
        await self._delete_dialog(interaction)


@app_commands.command(
    name="purge-list",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.purge", "-"
        ),
        key="wz.registration.purge.description",
    ),
)
@app_commands.checks.bot_has_permissions(moderate_members=True, manage_messages=True)
@app_commands.describe(
    ephemeral=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("parameter.description.ephemeral", "-"),
        key="ephemeral.description",
    )
)
@app_commands.checks.cooldown(1, 30, key=lambda interaction: interaction.guild_id)
async def purge(interaction: Interaction, ephemeral: bool = True) -> None:
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        configured_channels = await module.purge_channels.get(guild=guild)
        if not configured_channels:
            await interaction.followup.send(
                t(interaction, "wz.registration.purge.no_channels"),
                ephemeral=ephemeral,
            )
            return

        channels: list[tuple[int, discord.TextChannel | None]] = []
        channel_names: list[str] = []
        for configured in configured_channels:
            channel = await utils.fetch_channel(guild, configured.channel_id)
            channels.append((configured.channel_id, channel))
            channel_names.append(
                channel.mention
                if channel is not None
                else t(
                    interaction,
                    "wz.registration.purge.unavailable_channel",
                    channel_id=configured.channel_id,
                )
            )

        view = PurgeConfirmationView(
            guild=guild,
            owner_id=interaction.user.id,
            channels=tuple(channels),
            ephemeral=ephemeral,
        )
        view.message = await interaction.followup.send(
            embed=discord.Embed(
                description=t(
                    interaction,
                    "wz.registration.purge.confirmation",
                    channel_names="\n".join(f"• {name}" for name in channel_names),
                )
            ),
            view=view,
            ephemeral=ephemeral,
            wait=True,
        )
    except Exception:
        logger.exception("WZ configured-channel purge failed.")
        await interaction.followup.send(
            t(interaction, "wz.registration.purge.error"), ephemeral=True
        )
