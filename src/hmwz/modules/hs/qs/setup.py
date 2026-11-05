"""Private Qs setup using shared ephemeral and entity selection components."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import replace
from typing import Literal

import discord

from hmwz.i18n import t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.ui.components.timestamp_input import TimestampInput, resolve_timezone
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import (
    defer_interaction,
    send_modal,
    edit_interaction_response,
    send_followup,
    send_interaction_response,
)
from hmwz.ui.components.localized import LocalizedButton, LocalizedSelect

from .models import PingSettings, phase_starts, validate_schedule
from .models.ping_settings import PING_EVENTS, PingEvent
from .module import QsModule


def can_manage(member: discord.Member | discord.User) -> bool:
    """Match the project's moderator/officer role convention."""
    return isinstance(member, discord.Member) and any(
        role.name
        in {"Offiziere", "offiziere", "Moderator", "moderator", "officier", "Officier"}
        for role in member.roles
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


class HourSelect(LocalizedSelect):
    """Offer every whole-hour start from midnight to 23:00."""

    def __init__(self, panel: QsSetupView) -> None:
        current = panel.hours[panel.selected_phase - 1]
        duration = panel.durations[panel.selected_phase - 1]
        super().__init__(
            panel.module.guild,
            "qs.event.choose_hour",
            row=2,
            options=[
                discord.SelectOption(
                    label=f"{hour:02}:00 – {(hour + duration) % 24:02}:00",
                    value=str(hour),
                    default=hour == current,
                )
                for hour in range(24)
            ],
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        """Set the selected phase's whole-hour start."""
        self.panel.hours[self.panel.selected_phase - 1] = int(self.values[0])
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
    """Collect an event date using the guild's configured timezone."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(title=t(panel.module.guild, "qs.event.date_title"))
        self.panel = panel
        self.eruption = TimestampInput(
            panel.module.guild,
            label=t(panel.module.guild, "qs.admin.eruption_start"),
            timezone_name=panel.timezone,
            value=datetime.fromtimestamp(panel.eruption_start, UTC),
        )
        self.add_item(self.eruption)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Reject invalid, missing or ambiguous local phase times."""
        if not await self.panel.interaction_check(interaction):
            return
        try:
            instant = self.eruption.parse()
            if instant is None:
                raise ValueError("Eruption start required.")
            eruption_start = int(instant.timestamp())
            date = (
                instant.astimezone(resolve_timezone(self.panel.timezone))
                .date()
                .isoformat()
            )
            validate_schedule(
                eruption_start,
                phase_starts(
                    date,
                    tuple(self.panel.hours),
                    self.panel.timezone,
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


class PhaseCountSelect(LocalizedSelect):
    """Select four or five phases in the setup draft."""

    def __init__(self, panel: QsSetupView) -> None:
        super().__init__(
            panel.module.guild,
            "qs.admin.phase_count",
            row=0,
            options=[
                discord.SelectOption(
                    label=str(count),
                    value=str(count),
                    default=count == len(panel.hours),
                )
                for count in (4, 5)
            ],
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction) -> None:
        """Change draft phase count; destructive changes happen only on save/reset."""
        count = int(self.values[0])
        if count == 5 and len(self.panel.hours) == 4:
            self.panel.hours.append(self.panel.hours[-1])
            self.panel.durations.append(2)
        else:
            self.panel.hours = self.panel.hours[:count]
            self.panel.durations = self.panel.durations[:count]
        self.panel.selected_phase = min(self.panel.selected_phase, count)
        await self.panel.update(interaction)


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
            self.add_item(PhaseCountSelect(self))
            self.add_item(PhaseSelect(self))
            self.add_item(HourSelect(self))
            self.add_item(DurationSelect(self))
            self.add_item(SetupButton(self, "back", 4))
        elif self.page == "pings":
            for index, event in enumerate(PING_EVENTS):
                self.add_item(PingButton(self, event, index // 2))
            self.add_item(SetupButton(self, "back", 2))
        elif self.reset_mode:
            for action in ("date", "phases", "save"):
                self.add_item(SetupButton(self, action, 0))
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
        """Show the chosen hours and durations before committing configuration."""
        schedule = "\n".join(
            f"{t(self.module.guild, 'qs.event.phase', index=index)}: "
            f"{hour:02}:00 – {(hour + duration) % 24:02}:00 ({duration} h)"
            for index, (hour, duration) in enumerate(
                zip(self.hours, self.durations, strict=True), 1
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
                    eruption_start=self.eruption_start,
                )[index - 1]
                value = (
                    f"<t:{start}:F> – <t:{start + duration * 3600}:F> · {duration} h"
                )
            except ValueError:
                value = f"{hour:02}:00 · {duration} h\n{t(self.module.guild, 'qs.event.invalid_schedule')}"
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
            datetime.fromtimestamp(phase.starts_at, resolve_timezone(timezone)).hour
            for phase in phases
        )
        if phases
        else (0, 2, 4, 6, 8),
        role_id=configuration.role_id if configuration is not None else None,
        eruption_start=eruption_start,
        durations=tuple(phase.duration_hours for phase in phases)
        if phases
        else (2,) * 5,
        reset_mode=reset_mode,
        ping_settings=configuration.ping_settings
        if configuration is not None
        else PingSettings(),
    )
