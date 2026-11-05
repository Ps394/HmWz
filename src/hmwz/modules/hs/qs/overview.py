"""Bounded Qs overview, participation and destroyed-base embeds."""

import discord
from datetime import datetime

from hmwz.i18n import t
from hmwz.ui.embeds import create_embed
from hmwz.ui.components.timestamp_input import resolve_timezone
from hmwz.utils.text import escape_discord_text

from .models import BASE_TOTAL, BaseReport, Configuration, Phase
from .models.constants import PHASE_GOAL


def phase_label(context: discord.Guild | discord.Interaction, phase: Phase) -> str:
    """Return the localized phase label."""
    return t(context, "qs.event.phase", index=phase.index)


def phase_period(phase: Phase, timezone: str) -> str:
    """Format the phase's start and end hours in the configured timezone."""
    zone = resolve_timezone(timezone)
    start = datetime.fromtimestamp(phase.starts_at, zone).strftime("%H:%M")
    end = datetime.fromtimestamp(phase.ends_at, zone).strftime("%H:%M")
    return f"{start} – {end}"


def phase_title(context: discord.Guild, phase: Phase, timezone: str) -> str:
    """Combine the phase number and its configured local time range."""
    return f"{phase_label(context, phase)} - {phase_period(phase, timezone)}"


def report_name(guild: discord.Guild, report: BaseReport) -> str:
    """Show the player's current display name or the stored submission name."""
    member = guild.get_member(report.member_id)
    name = member.display_name if member is not None else report.display_name
    if not name:
        name = t(guild, "qs.event.unknown_player")
    return escape_discord_text(name[:32])


def member_list(context: discord.Guild, members: tuple[int, ...]) -> str:
    """Show bounded mentions and an explicit count for additional participants."""
    visible = members[:32]
    result = "\n".join(
        f"{index}. <@{member}>" for index, member in enumerate(visible, 1)
    )
    if len(members) > len(visible):
        result += "\n" + t(context, "qs.event.more", count=len(members) - len(visible))
    return result or t(context, "qs.event.no_members")


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
            role=f"<@&{configuration.role_id}>",
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


def phase_embed(
    guild: discord.Guild,
    phase: Phase,
    reports: tuple[BaseReport, ...],
) -> discord.Embed:
    """Show phase progress and destroyed-base reports."""
    phase_reports = tuple(
        report for report in reports if report.phase_index == phase.index
    )
    embed = create_embed(
        title=phase_label(guild, phase),
        description=(
            f"<t:{phase.starts_at}:F> – <t:{phase.ends_at}:F>\n"
            + t(
                guild,
                "qs.event.phase_progress",
                destroyed=len(phase_reports),
                total=PHASE_GOAL,
            )
        ),
    )
    names = "\n".join(
        f"{index}. {report_name(guild, report)}"
        for index, report in enumerate(phase_reports[:12], 1)
    )
    if len(phase_reports) > 12:
        names += "\n" + t(guild, "qs.event.more", count=len(phase_reports) - 12)
    embed.add_field(
        name=t(guild, "qs.event.phase_bases"),
        value=names or t(guild, "qs.event.none"),
        inline=False,
    )
    return embed


def participants_embed(
    guild: discord.Guild, phase: Phase, members: tuple[int, ...]
) -> discord.Embed:
    """Show a phase's participant list as a standalone embed."""
    embed = create_embed(title=phase_label(guild, phase))
    embed.add_field(
        name=t(guild, "qs.event.members", count=len(members)),
        value=member_list(guild, members),
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
