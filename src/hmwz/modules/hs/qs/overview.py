"""Event-wide Qs overview message, base listing and persistent signup view."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.embeds import create_embed

from .models import BASE_TOTAL, BaseReport, Configuration, Phase
from .phases.embeds import phase_label, report_name
from .phases.signups.views import PhaseButton, PhaseUnregisterButton

if TYPE_CHECKING:
    from .module import QsModule


def overview_embed(
    guild: discord.Guild,
    configuration: Configuration,
    phases: tuple[Phase, ...],
    members: dict[int, tuple[int, ...]],
    destroyed: int,
) -> discord.Embed:
    """Show signup counts, schedule, thread links and event-wide base progress."""
    embed = create_embed(
        title=t(guild, "qs.event.title"),
        description=t(
            guild,
            "qs.event.summary",
            start=f"<t:{configuration.eruption_start}:F>",
            end=f"<t:{configuration.eruption_end}:F>",
            destroyed=destroyed,
            total=BASE_TOTAL,
        ),
    )
    for phase in phases:
        embed.add_field(
            name=phase_label(guild, phase),
            value=(
                "👥 **"
                + t(guild, "qs.event.signup_count", count=len(members[phase.index]))
                + "**\n"
                + f"<t:{phase.starts_at}:F> – <t:{phase.ends_at}:t>\n"
                + (f"<#{phase.thread_id}>\n" if phase.thread_id is not None else "")
            ),
            inline=False,
        )
    return embed


def bases_embeds(
    guild: discord.Guild, reports: tuple[BaseReport, ...]
) -> list[discord.Embed]:
    """List every reported base in bounded embeds without truncating entries."""
    lines = [
        f"{index}. "
        + t(
            guild,
            "qs.event.base_entry",
            member=report_name(guild, report),
            phase=report.phase_index,
        )
        for index, report in enumerate(reports, 1)
    ]
    pages: list[str] = [""]
    for line in lines:
        if len(pages[-1]) + len(line) + 1 > 3000:
            pages.append("")
        pages[-1] += line + "\n"
    return [
        create_embed(
            title=t(
                guild, "qs.event.bases_title", destroyed=len(reports), total=BASE_TOTAL
            ),
            description=page or t(guild, "qs.event.no_bases"),
        )
        for page in pages
    ]


class OverviewView(discord.ui.View):
    """Persistent signup and unregister buttons on the main overview."""

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        phases: tuple[Phase, ...],
    ) -> None:
        super().__init__(timeout=None)
        for phase in phases:
            self.add_item(PhaseButton(module, channel_id, phase))
        for phase in phases:
            self.add_item(PhaseUnregisterButton(module, channel_id, phase))
