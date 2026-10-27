from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import t
from hmwz.ui.embeds import create_embed

from .common import command_description, get_member_context

logger = logging.getLogger(__name__)
_ACCOUNT_EMBED_DESCRIPTION_LIMIT = 3500


@app_commands.command(
    name="account-list",
    description=command_description(
        "command.description.wz.registration.account_list",
        "List your linked in-game accounts",
    ),
)
@app_commands.checks.cooldown(1, 10, key=lambda interaction: interaction.user.id)
async def account_list(interaction: Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        context = await get_member_context(interaction)
        if context is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return
        guild, member, module = context
        accounts = await module.game_accounts.get(guild=guild, member=member.id)
        if not accounts:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.none"), ephemeral=True
            )
            return
        intro = t(
            interaction,
            "wz.registration.account.list_description",
            display_name=discord.utils.escape_mentions(member.display_name),
        )
        display_account = discord.utils.escape_markdown(
            member.display_name.replace("\r", " ").replace("\n", " ")
        )
        display_name_line = t(
            interaction,
            "wz.registration.account.list_display_name",
            display_name=display_account,
        )
        pages: list[list[str]] = [[display_name_line]]
        page_length = len(intro) + len(display_name_line) + 3
        for index, record in enumerate(accounts, 2):
            account_name = discord.utils.escape_markdown(
                record.account.replace("\r", " ").replace("\n", " ")
            )
            line = f"**{index}.** {account_name}"
            if (
                pages[-1]
                and page_length + len(line) + 1 > _ACCOUNT_EMBED_DESCRIPTION_LIMIT
            ):
                pages.append([])
                page_length = len(intro) + 2
            pages[-1].append(line)
            page_length += len(line) + 1

        avatar = member.display_avatar
        color = member.color if member.color.value else discord.Color.blurple()
        for page in pages:
            description = f"{intro}\n\n" + "\n".join(page)
            embed = create_embed(
                title=t(interaction, "wz.registration.account.list_title"),
                description=description,
                color=color,
                client_avatar=avatar,
            )
            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except Exception:
        logger.exception(
            "%s Failed to list linked game accounts.",
            utils.log_interaction(interaction),
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
