"""Render a structured embed for donation configuration."""

import discord

from hmwz.i18n import t
from hmwz.ui.embeds import create_embed

from ....type.rush.pricing import RUSH_PERIOD_DURATION
from ....type.rush.pricing import rush_end_at
from ....type.rush.overview import add_target_field
from .draft import DonationSetupDraft


def donation_setup_panel(
    draft: DonationSetupDraft, interaction: discord.Interaction
) -> discord.Embed:
    """Show channel, content, type-specific inputs, display settings, and export."""
    embed = create_embed(
        title=t(interaction, "donation.setup.title"),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name=t(interaction, "donation.setup.channel"),
        value=f"<#{draft.channel_id}>",
        inline=True,
    )
    embed.add_field(
        name=t(interaction, "donation.setup.kind"),
        value=t(
            interaction,
            "donation.type.credit.name"
            if draft.kind == "simple"
            else "donation.type.rush.name",
        ),
        inline=True,
    )
    embed.add_field(
        name=t(interaction, "donation.setup.overview_title"),
        value=draft.title or t(interaction, "donation.setup.default_title"),
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "donation.setup.overview_text"),
        value=(
            draft.description[:1021] + "..."
            if len(draft.description) > 1024
            else draft.description or t(interaction, "donation.setup.not_configured")
        ),
        inline=False,
    )
    embed.add_field(
        name=t(interaction, "donation.setup.unit"),
        value=draft.unit or t(interaction, "donation.setup.not_configured"),
        inline=True,
    )
    if draft.kind == "simple":
        embed.add_field(
            name=t(interaction, "donation.type.credit.choices"),
            value=(
                "\n".join(draft.choices)[:1024]
                if draft.choices
                else t(interaction, "donation.type.credit.free_entry")
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name=t(interaction, "donation.setup.input_timezone"),
            value=draft.timezone_name
            + "\n"
            + t(interaction, "donation.setup.input_timezone_hint"),
            inline=False,
        )
        embed.add_field(
            name=t(interaction, "donation.type.rush.options"),
            value=", ".join(draft.time_reductions),
            inline=True,
        )
        embed.add_field(
            name=t(interaction, "donation.setup.pricing"),
            value=t(interaction, "donation.type.rush.pricing"),
            inline=False,
        )
        start = draft.rush_start_at
        end = rush_end_at(start, draft.accelerated_hours) if start is not None else None
        for key, timestamp in (
            ("donation.type.rush.overview.start", start),
            ("donation.type.rush.overview.end", end),
        ):
            embed.add_field(
                name=t(interaction, key),
                value=(
                    discord.utils.format_dt(timestamp, "F")
                    if timestamp is not None
                    else t(interaction, "donation.setup.not_configured")
                ),
                inline=False,
            )
        embed.add_field(
            name=t(interaction, "donation.type.rush.overview.duration"),
            value=t(
                interaction,
                "donation.type.rush.duration",
                days=RUSH_PERIOD_DURATION.days,
                hours=int(RUSH_PERIOD_DURATION.total_seconds() // 3600),
            ),
            inline=True,
        )
        if draft.target_at is not None and end is not None:
            add_target_field(embed, interaction, draft.target_at, end)
        else:
            embed.add_field(
                name=t(interaction, "donation.type.rush.overview.target"),
                value=t(interaction, "donation.setup.not_configured"),
                inline=False,
            )
    for key, enabled in (
        ("donation.overview.donations_status", draft.donations_enabled),
        ("donation.setup.history", draft.show_donations),
        ("donation.ranking.title", draft.show_ranking),
    ):
        embed.add_field(
            name=t(interaction, key),
            value=t(
                interaction,
                "donation.setup.enabled" if enabled else "donation.setup.disabled",
            ),
            inline=True,
        )
    embed.add_field(
        name=t(interaction, "donation.setup.export_channel"),
        value=_export_channel_status(draft, interaction),
        inline=False,
    )
    return embed


def _export_channel_status(
    draft: DonationSetupDraft, interaction: discord.Interaction
) -> str:
    if draft.export_channel_id is None:
        return t(interaction, "donation.setup.disabled")
    channel = draft.module.guild.get_channel(draft.export_channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel.mention
    return t(
        interaction,
        "donation.setup.export_channel_unavailable",
        channel_id=draft.export_channel_id,
    )
