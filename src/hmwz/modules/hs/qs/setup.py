"""Private Qs setup using shared ephemeral and entity selection components."""

from __future__ import annotations

import re
from datetime import datetime
from dataclasses import replace
from typing import Literal

import discord

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.components.timestamp_input import (
    parse_local_datetime,
    resolve_timezone,
)
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import (
    defer_interaction,
    send_modal,
    edit_interaction_response,
    send_followup,
    send_interaction_response,
)
from hmwz.ui.components.localized import LocalizedButton, LocalizedSelect

from .models import PHASE_COUNT, PingSettings, phase_starts, validate_schedule
from .models.ping_settings import PING_EVENTS, PingEvent
from .module import QsModule


def can_manage(member: discord.Member | discord.User) -> bool:
    """Match the project's moderator/officer role convention."""
    return isinstance(member, discord.Member) and any(
        role.name in MODERATOR_ROLES for role in member.roles
    )


class PhaseSelect(LocalizedSelect):
    """Select which configured phase is being edited."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(
            panel.module.guild,
            "qs.event.choose_phase",
            row=1,
            options=[
                discord.SelectOption(
                    label=t(panel.module.guild, "qs.event.phase", index=index),
                    value=str(index),
                    default=index == panel.selected_phase,
                )
                for index in range(1, len(panel.hours) + 1)
            ],
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        """Switch the edited phase without changing its start hour."""
        self.panel.selected_phase = int(self.values[0])
        await self.panel.update(interaction)


class QsRoleSelection(EntitySelectionView):
    """Reuse the project picker for a single existing Qs ping role."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(
            owner_id=panel.owner_id,
            kind="role",
            max_selected=1,
            allowed_ids=[
                role.id for role in panel.module.guild.roles if not role.is_default()
            ],
            placeholder=t(panel.module.guild, "qs.event.choose_role"),
            owner_message=t(panel.module.guild, "qs.event.owner"),
            invalid_message=t(panel.module.guild, "qs.event.invalid_role"),
        )
        self.panel = panel
        self.message = panel.message
        self.add_item(SetupButton(panel, "back", 4))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Recheck moderator privileges as well as ownership in the role picker."""
        return await self.panel.interaction_check(interaction)

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        """Return to setup once a role has been selected."""
        if not self.selected_ids:
            await self.send_temporary_response(
                interaction, t(interaction, "qs.event.invalid_role")
            )
            return
        self.panel.role_id = next(iter(self.selected_ids))
        self.stop()
        await self.panel.update(interaction)


class DateModal(discord.ui.Modal):
    """Collect a separate local date and time for the eruption start."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(title=t(panel.module.guild, "qs.event.date_title"))
        self.panel = panel
        local_start = datetime.fromtimestamp(
            panel.eruption_start, resolve_timezone(panel.timezone)
        )
        self.date_input = discord.ui.TextInput(
            label=t(panel.module.guild, "qs.event.date"),
            default=local_start.strftime("%Y-%m-%d"),
            min_length=10,
            max_length=10,
        )
        self.time_input = discord.ui.TextInput(
            label=t(panel.module.guild, "qs.event.eruption_time"),
            default=local_start.strftime("%H:%M"),
            min_length=5,
            max_length=5,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Reject invalid, missing or ambiguous local phase times."""
        if not await self.panel.interaction_check(interaction):
            return
        date_input = self.date_input.value.strip()
        time_input = self.time_input.value.strip()
        try:
            if (
                re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_input) is None
                or re.fullmatch(r"\d{2}:\d{2}", time_input) is None
            ):
                raise ValueError("Enter date as YYYY-MM-DD and time as HH:MM.")
            instant = parse_local_datetime(
                f"{date_input} {time_input}", self.panel.timezone
            )
        except ValueError:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.invalid_eruption_time")
            )
            return
        eruption_start = int(instant.timestamp())
        date = (
            instant.astimezone(resolve_timezone(self.panel.timezone)).date().isoformat()
        )
        try:
            validate_schedule(
                eruption_start,
                phase_starts(
                    date,
                    tuple(self.panel.hours),
                    self.panel.timezone,
                    minutes=tuple(self.panel.minutes),
                    eruption_start=eruption_start,
                ),
                tuple(self.panel.durations),
            )
        except ValueError:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.invalid_schedule")
            )
            return
        self.panel.date = date
        self.panel.eruption_start = eruption_start
        await self.panel.update(interaction)


class PhaseTimeModal(discord.ui.Modal):
    """Edit the selected phase's local start hour and minute."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(title=t(panel.module.guild, "qs.event.time_title"))
        self.panel = panel
        self.phase_index = panel.selected_phase
        index = self.phase_index - 1
        self.hour = discord.ui.TextInput(
            label=t(panel.module.guild, "qs.event.start_hour"),
            default=f"{panel.hours[index]:02}",
            min_length=1,
            max_length=2,
        )
        self.minute = discord.ui.TextInput(
            label=t(panel.module.guild, "qs.event.start_minute"),
            default=f"{panel.minutes[index]:02}",
            min_length=1,
            max_length=2,
        )
        self.add_item(self.hour)
        self.add_item(self.minute)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Validate both numeric fields before updating the unsaved draft."""
        if not await self.panel.interaction_check(interaction):
            return
        hour_text, minute_text = self.hour.value.strip(), self.minute.value.strip()
        if (
            not hour_text.isascii()
            or not hour_text.isdigit()
            or not minute_text.isascii()
            or not minute_text.isdigit()
        ):
            await send_interaction_response(
                interaction, t(interaction, "qs.event.invalid_phase_time")
            )
            return
        hour, minute = int(hour_text), int(minute_text)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.invalid_phase_time")
            )
            return
        index = self.phase_index - 1
        self.panel.hours[index] = hour
        self.panel.minutes[index] = minute
        await self.panel.update(interaction)


class PhaseTimeButton(LocalizedButton):
    """Open numeric inputs for the selected phase's start time."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(
            panel.module.guild,
            "qs.event.choose_time",
            row=2,
            emoji="🕒",
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the time modal for the currently selected phase."""
        if not await self.panel.interaction_check(interaction):
            return
        await send_modal(interaction, PhaseTimeModal(self.panel))


class DurationSelect(LocalizedSelect):
    """Select a one-, two- or three-hour duration."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(
            panel.module.guild,
            "qs.admin.duration",
            row=3,
            options=[
                discord.SelectOption(
                    label=f"{duration} h",
                    value=str(duration),
                    default=duration == panel.durations[panel.selected_phase - 1],
                )
                for duration in (1, 2, 3)
            ],
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        """Change only the selected phase's draft duration."""
        self.panel.durations[self.panel.selected_phase - 1] = int(self.values[0])
        await self.panel.update(interaction)


class QsSetupView(EphemeralView):
    """Owner-bound role, date and phase editor with explicit saving."""

    def __init__(
        self,
        module: QsModule,
        channel_id: int,
        owner_id: int,
        *,
        date: str,
        timezone: str,
        hours: tuple[int, ...],
        minutes: tuple[int, ...],
        role_id: int | None,
        eruption_start: int,
        durations: tuple[int, ...],
        reset_mode: bool = False,
        ping_settings: PingSettings = PingSettings(),
    ) -> None:
        super().__init__(timeout=600)
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.date = date
        self.timezone = timezone
        self.hours = list(hours)
        self.minutes = list(minutes)
        self.role_id = role_id
        self.eruption_start = eruption_start
        self.durations = list(durations)
        self.reset_mode = reset_mode
        self.ping_settings = ping_settings
        self.page: Literal["menu", "phases", "pings"] = "menu"
        self.selected_phase = 1
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        if self.page == "phases":
            self.add_item(PhaseSelect(self))
            self.add_item(PhaseTimeButton(self))
            self.add_item(DurationSelect(self))
            self.add_item(SetupButton(self, "back", 4))
        elif self.page == "pings":
            for index, event in enumerate(PING_EVENTS):
                self.add_item(PingButton(self, event, index // 2))
            self.add_item(SetupButton(self, "back", 2))
        elif self.reset_mode:
            for action in ("date", "phases"):
                self.add_item(SetupButton(self, action, 0))
            for action in ("save", "cancel"):
                self.add_item(SetupButton(self, action, 2))
        else:
            for action, row in (
                ("role", 0),
                ("date", 0),
                ("phases", 0),
                ("pings", 1),
                ("save", 2),
                ("cancel", 2),
            ):
                self.add_item(SetupButton(self, action, row))

    def content(self) -> str:
        """Show all configured phase windows before committing configuration."""
        try:
            starts = phase_starts(
                self.date,
                tuple(self.hours),
                self.timezone,
                minutes=tuple(self.minutes),
                eruption_start=self.eruption_start,
            )
            schedule = "\n".join(
                f"{t(self.module.guild, 'qs.event.phase', index=index)}: "
                f"<t:{start}:F> – "
                f"<t:{start + duration * 3600}:F> ({duration} h)"
                for index, (start, duration) in enumerate(
                    zip(starts, self.durations, strict=True), 1
                )
            )
        except ValueError:
            schedule = "\n".join(
                f"{t(self.module.guild, 'qs.event.phase', index=index)}: "
                f"{hour:02}:{minute:02} · {duration} h"
                for index, (hour, minute, duration) in enumerate(
                    zip(self.hours, self.minutes, self.durations, strict=True), 1
                )
            )
        return t(
            self.module.guild,
            "qs.event.setup_summary",
            date=self.date,
            timezone=self.timezone,
            role=f"<@&{self.role_id}>"
            if self.role_id
            else t(self.module.guild, "qs.event.none"),
            schedule=schedule,
        )

    def embed(self) -> discord.Embed:
        """Render a structured settings summary like the registration setup panel."""
        embed = create_embed(
            title=t(
                self.module.guild,
                "qs.admin.reset_title" if self.reset_mode else "qs.admin.setup_title",
            )
        )
        for key, value in (
            ("channel", f"<#{self.channel_id}>"),
            (
                "role",
                f"<@&{self.role_id}>"
                if self.role_id
                else t(self.module.guild, "qs.event.none"),
            ),
            ("eruption_start", f"<t:{self.eruption_start}:F>"),
            ("eruption_end", f"<t:{self.eruption_start + 86400}:F>"),
            ("phase_date", f"{self.date} ({self.timezone})"),
        ):
            embed.add_field(
                name=t(self.module.guild, f"qs.admin.{key}"), value=value, inline=False
            )
        for index, (hour, duration) in enumerate(
            zip(self.hours, self.durations, strict=True), 1
        ):
            try:
                start = phase_starts(
                    self.date,
                    tuple(self.hours),
                    self.timezone,
                    minutes=tuple(self.minutes),
                    eruption_start=self.eruption_start,
                )[index - 1]
                value = (
                    f"<t:{start}:F> – <t:{start + duration * 3600}:F> · {duration} h"
                )
            except ValueError:
                value = f"{hour:02}:{self.minutes[index - 1]:02} · {duration} h\n{t(self.module.guild, 'qs.event.invalid_schedule')}"
            embed.add_field(
                name=t(self.module.guild, "qs.event.phase", index=index),
                value=value,
                inline=True,
            )
        embed.add_field(
            name=t(self.module.guild, "qs.admin.pings"),
            value="\n".join(
                f"{'🔔' if self.ping_settings.is_enabled(event) else '🔕'} "
                f"{t(self.module.guild, f'qs.admin.ping_setting_{event}')}: "
                f"{t(self.module.guild, 'qs.admin.enabled' if self.ping_settings.is_enabled(event) else 'qs.admin.disabled')}"
                for event in PING_EVENTS
            )
            + "\n\n"
            + t(self.module.guild, "qs.admin.pings_summary"),
            inline=False,
        )
        embed.add_field(
            name=t(self.module.guild, "qs.admin.draft"),
            value=t(self.module.guild, "qs.admin.draft_summary"),
            inline=False,
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Recheck ownership and moderator roles on every setup action."""
        if interaction.user.id == self.owner_id and can_manage(interaction.user):
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.event.owner")
        )
        return False

    async def update(self, interaction: discord.Interaction) -> None:
        """Redraw selectors and the complete draft without committing it."""
        self._rebuild()
        await edit_interaction_response(
            interaction, content=None, embed=self.embed(), view=self
        )


class PingButton(LocalizedButton):
    """Toggle one automatic notification in the unsaved draft."""

    def __init__(self, panel: QsSetupView, event: PingEvent, row: int) -> None:
        enabled = panel.ping_settings.is_enabled(event)
        super().__init__(
            panel.module.guild,
            f"qs.admin.ping_setting_{event}",
            row=row,
            emoji="🔔" if enabled else "🔕",
            style=discord.ButtonStyle.success
            if enabled
            else discord.ButtonStyle.secondary,
        )
        self.panel = panel
        self.event = event

    async def callback(self, interaction: discord.Interaction) -> None:
        """Update the preview without persisting the notification switch."""
        if not await self.panel.interaction_check(interaction):
            return
        self.panel.ping_settings = replace(
            self.panel.ping_settings,
            **{self.event: not self.panel.ping_settings.is_enabled(self.event)},
        )
        await self.panel.update(interaction)


class SetupButton(LocalizedButton):
    """Edit draft metadata or save the complete event."""

    def __init__(self, panel: QsSetupView, action: str, row: int) -> None:
        super().__init__(
            panel.module.guild,
            "qs.event.setup_confirmation"
            if action == "save" and panel.reset_mode
            else f"qs.event.setup_{action}",
            row=row,
            emoji={
                "role": "👥",
                "date": "📅",
                "phases": "⚙️",
                "pings": "🔔",
                "save": "✅",
                "cancel": "❌",
                "back": "↩️",
            }[action],
            style=discord.ButtonStyle.danger
            if action == "save" and panel.reset_mode
            else discord.ButtonStyle.success
            if action == "save"
            else discord.ButtonStyle.secondary,
        )
        self.panel = panel
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open shared pickers or persist the fully validated setup."""
        if not await self.panel.interaction_check(interaction):
            return
        if self.action == "cancel":
            await self.panel.dismiss(interaction)
            return
        if self.action in ("phases", "pings", "back"):
            if self.action == "phases":
                self.panel.page = "phases"
            elif self.action == "pings":
                self.panel.page = "pings"
            else:
                self.panel.page = "menu"
            if self.view is not None and self.view is not self.panel:
                self.view.stop()
            await self.panel.update(interaction)
            return
        if self.action == "date":
            await send_modal(interaction, DateModal(self.panel))
            return
        if self.action == "role":
            if not any(not role.is_default() for role in self.panel.module.guild.roles):
                await send_interaction_response(
                    interaction, t(interaction, "qs.event.invalid_role")
                )
                return
            await edit_interaction_response(
                interaction,
                content=t(interaction, "qs.event.choose_role"),
                embed=self.panel.embed(),
                view=QsRoleSelection(self.panel),
            )
            return
        if self.panel.role_id is None:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.invalid_role")
            )
            return
        try:
            validate_schedule(
                self.panel.eruption_start,
                phase_starts(
                    self.panel.date,
                    tuple(self.panel.hours),
                    self.panel.timezone,
                    minutes=tuple(self.panel.minutes),
                    eruption_start=self.panel.eruption_start,
                ),
                tuple(self.panel.durations),
            )
        except ValueError:
            await send_interaction_response(
                interaction, t(interaction, "qs.event.invalid_schedule")
            )
            return
        if self.panel.reset_mode:
            from .commands.maintenance import QsMaintenanceConfirmation

            view = QsMaintenanceConfirmation(
                self.panel.module,
                self.panel.channel_id,
                self.panel.owner_id,
                action="reset",
                date=self.panel.date,
                hours=tuple(self.panel.hours),
                minutes=tuple(self.panel.minutes),
                eruption_start=self.panel.eruption_start,
                durations=tuple(self.panel.durations),
            )
            view.message = self.panel.message
            await edit_interaction_response(
                interaction,
                content=t(interaction, "qs.admin.reset_warning"),
                embed=self.panel.embed(),
                view=view,
            )
            self.panel.stop()
            return
        await defer_interaction(interaction, thinking=True)
        success = await self.panel.module.configure(
            self.panel.channel_id,
            self.panel.role_id,
            self.panel.date,
            tuple(self.panel.hours),
            minutes=tuple(self.panel.minutes),
            eruption_start=self.panel.eruption_start,
            durations=tuple(self.panel.durations),
            ping_settings=self.panel.ping_settings,
        )
        if success:
            await self.panel.finish(interaction, t(interaction, "qs.event.saved"))
        else:
            await send_followup(interaction, t(interaction, "qs.event.setup_failed"))


async def setup_view(
    module: QsModule, channel_id: int, owner_id: int, *, reset_mode: bool = False
) -> QsSetupView:
    """Load an existing event draft or choose sensible editable defaults."""
    configuration = await module.qs.get(module.guild.id, channel_id)
    timezone = await module.client.get_guild_timezone(module.guild.id)
    phases = await module.qs.phases(module.guild.id, channel_id)
    phases_by_index = {phase.index: phase for phase in phases}
    default_hours = (0, 2, 4, 6, 8)
    eruption_start = (
        configuration.eruption_start
        if configuration is not None
        else int(
            datetime.now(resolve_timezone(timezone))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
    )
    return QsSetupView(
        module,
        channel_id,
        owner_id,
        date=datetime.fromtimestamp(eruption_start, resolve_timezone(timezone))
        .date()
        .isoformat(),
        timezone=timezone,
        hours=tuple(
            datetime.fromtimestamp(
                phases_by_index[index].starts_at, resolve_timezone(timezone)
            ).hour
            if index in phases_by_index
            else default_hours[index - 1]
            for index in range(1, PHASE_COUNT + 1)
        ),
        minutes=tuple(
            datetime.fromtimestamp(
                phases_by_index[index].starts_at, resolve_timezone(timezone)
            ).minute
            if index in phases_by_index
            else 0
            for index in range(1, PHASE_COUNT + 1)
        ),
        role_id=configuration.role_id if configuration is not None else None,
        eruption_start=eruption_start,
        durations=tuple(
            phases_by_index[index].duration_hours if index in phases_by_index else 2
            for index in range(1, PHASE_COUNT + 1)
        ),
        reset_mode=reset_mode,
        ping_settings=configuration.ping_settings
        if configuration is not None
        else PingSettings(),
    )
