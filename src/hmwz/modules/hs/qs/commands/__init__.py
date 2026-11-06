"""Qs setup and intentional role pings."""

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.messages import send_followup, send_interaction_response, defer_interaction

from ..module import QsModule
from ..setup import setup_view
from ..views import BaseReportConfirmation
from hmwz.utils.text import escape_discord_text
from .maintenance import QsMaintenanceConfirmation


async def get_module(interaction: discord.Interaction) -> QsModule | None:
    """Resolve the independent module in a guild text channel."""
    manager = getattr(interaction.client, "module_manager", None)
    if (
        interaction.guild is None
        or manager is None
        or not isinstance(interaction.channel, discord.TextChannel)
    ):
        await send_interaction_response(
            interaction, t(interaction, "qs.event.not_configured")
        )
        return None
    return await manager.get_module(interaction.guild, QsModule)


@app_commands.guild_only()
@app_commands.checks.bot_has_permissions(
    view_channel=True,
    send_messages=True,
    embed_links=True,
    read_message_history=True,
    create_public_threads=True,
    send_messages_in_threads=True,
    manage_threads=True,
)
class QsGroup(app_commands.Group):
    """Expose Qs event planning independently from queues and registrations."""

    def __init__(self) -> None:
        super().__init__(
            name="qs",
            description=app_commands.locale_str(
                "Qs event commands", key="qs.event.group"
            ),
        )

    async def _report_dialog(
        self,
        interaction: discord.Interaction,
        player: discord.Member,
        phase: int | None,
    ) -> None:
        module = await get_module(interaction)
        if module is None or interaction.channel_id is None:
            return
        if not await module.authorize_moderation(interaction, interaction.channel_id):
            return
        reports = await module.qs.reports(module.guild.id, interaction.channel_id)
        if phase is None:
            report = next(
                (item for item in reports if item.member_id == player.id), None
            )
            if report is None:
                await send_interaction_response(
                    interaction, t(interaction, "qs.event.withdraw_missing")
                )
                return
            phase_index = report.phase_index
        else:
            phase_index = phase
            if not any(
                item.index == phase
                for item in await module.qs.phases(
                    module.guild.id, interaction.channel_id
                )
            ):
                await send_interaction_response(
                    interaction, t(interaction, "qs.event.not_configured")
                )
                return
        view = BaseReportConfirmation(
            module,
            interaction.channel_id,
            phase_index,
            interaction.user.id,
            withdraw_member_id=player.id if phase is None else None,
            report_member=player if phase is not None else None,
            moderation=True,
        )
        view.message = await send_interaction_response(
            interaction,
            t(
                interaction,
                "qs.event.withdraw_confirmation"
                if phase is None
                else "qs.event.moderator_report_confirmation",
                member=escape_discord_text(player.display_name),
                phase=phase_index,
            ),
            view=view,
        )

    @app_commands.command(
        name="report",
        description=app_commands.locale_str(
            "Add a base report for a player", key="qs.admin.report"
        ),
    )
    @app_commands.checks.has_any_role(*MODERATOR_ROLES)
    async def report(
        self,
        interaction: discord.Interaction,
        player: discord.Member,
        phase: app_commands.Range[int, 1, 5],
    ) -> None:
        """Confirm a moderator-created player report in the configured main channel."""
        await self._report_dialog(interaction, player, phase)

    @app_commands.command(
        name="withdraw",
        description=app_commands.locale_str(
            "Retract a player's base report", key="qs.admin.withdraw"
        ),
    )
    @app_commands.checks.has_any_role(*MODERATOR_ROLES)
    async def withdraw(
        self, interaction: discord.Interaction, player: discord.Member
    ) -> None:
        """Confirm withdrawal of a player's report from this channel's eruption."""
        await self._report_dialog(interaction, player, None)

    @app_commands.command(
        name="setup",
        description=app_commands.locale_str(
            "Configure a Qs eruption and four or five phases", key="qs.event.setup"
        ),
    )
    @app_commands.checks.has_any_role(*MODERATOR_ROLES)
    async def setup(self, interaction: discord.Interaction) -> None:
        """Open a private setup draft with explicit role and hour selection."""
        module = await get_module(interaction)
        if module is None or interaction.channel_id is None:
            return
        if not await module.sync():
            await send_interaction_response(
                interaction, t(interaction, "qs.event.setup_failed")
            )
            return
        view = await setup_view(module, interaction.channel_id, interaction.user.id)
        view.message = await send_interaction_response(
            interaction, embed=view.embed(), view=view
        )

    @app_commands.command(
        name="remove",
        description=app_commands.locale_str(
            "Remove the Qs tool, its threads and data", key="qs.admin.remove"
        ),
    )
    @app_commands.checks.has_any_role(*MODERATOR_ROLES)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, manage_threads=True)
    async def remove(self, interaction: discord.Interaction) -> None:
        """Show a removal preview before deleting any Qs resources."""
        module = await get_module(interaction)
        if module is None or interaction.channel_id is None:
            return
        if await module.qs.get(module.guild.id, interaction.channel_id) is None:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.not_configured")
            )
            return
        view = QsMaintenanceConfirmation(
            module, interaction.channel_id, interaction.user.id, action="remove"
        )
        view.message = await send_interaction_response(
            interaction,
            t(interaction, "qs.admin.remove_warning"),
            view=view,
        )

    @app_commands.command(
        name="reset",
        description=app_commands.locale_str(
            "Clean Qs channels and configure a new eruption schedule",
            key="qs.admin.reset",
        ),
    )
    @app_commands.checks.has_any_role(*MODERATOR_ROLES)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, manage_threads=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        """Choose new timestamps and phase durations before confirming the reset."""
        module = await get_module(interaction)
        if module is None or interaction.channel_id is None:
            return
        configuration = await module.qs.get(module.guild.id, interaction.channel_id)
        if configuration is None or configuration.state == "removing":
            await send_interaction_response(
                interaction, t(interaction, "qs.event.not_configured")
            )
            return
        view = await setup_view(
            module, interaction.channel_id, interaction.user.id, reset_mode=True
        )
        view.message = await send_interaction_response(
            interaction,
            embed=view.embed(),
            view=view,
        )

    @app_commands.command(
        name="ping",
        description=app_commands.locale_str(
            "Ping this channel's configured Qs role", key="qs.event.ping_command"
        ),
    )
    @app_commands.checks.has_any_role(*MODERATOR_ROLES)
    @app_commands.checks.cooldown(
        1, 60, key=lambda interaction: (interaction.guild_id, interaction.channel_id)
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        """Intentionally notify only the channel's Qs role."""
        module = await get_module(interaction)
        if module is None or interaction.channel_id is None:
            return
        await defer_interaction(interaction, thinking=True)
        success = await module.ping(interaction.channel_id)
        await send_followup(
            interaction,
            t(interaction, "qs.event.ping_sent" if success else "qs.event.ping_failed"),
        )
