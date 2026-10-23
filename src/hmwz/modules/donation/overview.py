from __future__ import annotations

import discord

from hmwz.i18n import t

from .repository import DonationRecord, DonationType


class DonationOverview:
    """Creates the donation summary embed for one channel."""

    @staticmethod
    def create_embed(
        guild: discord.Guild,
        donation_types: tuple[DonationType, ...],
        donations: tuple[DonationRecord, ...],
    ) -> discord.Embed:
        """Build an overview showing configured types and recent donations."""
        embed = discord.Embed(
            title=t(guild, "donation.overview.title"),
            description=t(guild, "donation.overview.description"),
            color=discord.Color.gold(),
        )
        type_lines = [
            f"**{donation_type.name}**"
            + (
                f" ({t(guild, 'donation.overview.second_field')}: "
                f"{donation_type.extra_field})"
                if donation_type.extra_field
                else ""
            )
            for donation_type in donation_types
        ]
        type_value = "\n".join(type_lines)
        if len(type_value) > 1024:
            type_value = type_value[:1020].rsplit("\n", maxsplit=1)[0] + "\n..."
        embed.add_field(
            name=t(guild, "donation.overview.types"),
            value=type_value or t(guild, "donation.overview.no_types"),
            inline=False,
        )

        lines = [
            f"**{record.member_name}** — {record.amount} {record.type_name}"
            + (
                f" · {record.extra_label}: {record.extra_value}"
                if record.extra_label and record.extra_value
                else ""
            )
            for record in donations
        ]
        history = "\n".join(lines) or t(guild, "donation.overview.no_donations")
        if len(history) > 1024:
            history = history[:1020].rsplit("\n", maxsplit=1)[0] + "\n..."
        embed.add_field(
            name=t(guild, "donation.overview.recent"),
            value=history,
            inline=False,
        )
        if len(donations) == 20:
            embed.set_footer(text=t(guild, "donation.overview.recent_limit"))
        return embed
