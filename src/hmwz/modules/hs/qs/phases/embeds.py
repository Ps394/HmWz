"""Bounded phase labels and the embeds shown inside a phase thread."""

from collections.abc import Mapping
from datetime import datetime

import discord

from hmwz.i18n import t
from hmwz.ui.components.timestamp_input import resolve_timezone
from hmwz.ui.embeds import create_embed
from hmwz.utils.text import escape_discord_text

from ..models import BaseReport, MemberSignup, Phase
from ..models.constants import PHASE_GOAL


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
    """Show the linked game account or the reporting member's display name."""
    if report.game_account is not None:
        return escape_discord_text(report.game_account[:32])
    member = guild.get_member(report.member_id)
    name = member.display_name if member is not None else report.display_name
    if not name:
        name = t(guild, "qs.event.unknown_player")
    return escape_discord_text(name[:32])


def member_list(
    context: discord.Guild,
    members: tuple[int | MemberSignup, ...],
    accounts: Mapping[int, str] | None = None,
) -> str:
    """Show selected accounts and mark entries beyond the phase goal."""
    lines: list[str] = []
    for index, signup in enumerate(members[:32], 1):
        if isinstance(signup, MemberSignup):
            member = signup.member_id
            account = signup.game_account
        else:
            member = signup
            account = accounts.get(member) if accounts is not None else None
        marker = "🎯" if index <= PHASE_GOAL else "➕"
        if account:
            name = escape_discord_text(account[:24])
            line = t(
                context,
                "qs.event.member_signup_account",
                marker=marker,
                index=index,
                account=name,
                member=member,
            )
        else:
            line = t(
                context,
                "qs.event.member_signup_main",
                marker=marker,
                index=index,
                member=member,
            )
        if len("\n".join((*lines, line))) > 850:
            break
        lines.append(line)
    result = "\n".join(lines)
    remaining = len(members) - len(lines)
    if remaining:
        result += ("\n" if result else "") + t(
            context, "qs.event.more", count=remaining
        )
    return result or t(context, "qs.event.no_members")


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
            t(
                guild,
                "qs.event.phase_summary",
                start=f"<t:{phase.starts_at}:F>",
                end=f"<t:{phase.ends_at}:F>",
            )
            + "\n\n"
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
    guild: discord.Guild,
    phase: Phase,
    members: tuple[int | MemberSignup, ...],
    accounts: Mapping[int, str] | None = None,
) -> discord.Embed:
    """Show a phase's participant list as a standalone embed."""
    return create_embed(
        title=t(
            guild,
            "qs.event.phase_signup_title",
            phase=phase_label(guild, phase),
        ),
        description=member_list(guild, members, accounts),
    )
