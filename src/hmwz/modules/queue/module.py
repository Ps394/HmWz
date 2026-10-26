from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

from hmwz import sqlite_db
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .models import (
    Eruption,
    PhaseParticipant,
    QueueConfiguration,
    QueuePhase,
    QueueReminder,
)
from .repositories import QueueRepository
from .rules import phase_schedule
from .views import (
    BaseDestructionModal,
    PhaseThreadView,
    QueueOverviewView,
)

_logger = logging.getLogger(__name__)


@register
class QueueModule(BasicModule):
    """Coordinate QS eruption registration and one-time base destruction."""

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("QS phase queue requires a database.")
        self.queues = QueueRepository(self.database)
        self._registered_views: set[tuple[str, int]] = set()
        self._reminder_task: asyncio.Task[None] | None = None

    async def sync(self, startup: bool = False) -> bool:
        return await self.queues.ensure_schema()

    async def ensure(self) -> bool:
        if not await self.queues.ensure_schema():
            return False
        if self._reminder_task is None or self._reminder_task.done():
            self._reminder_task = asyncio.create_task(self._reminder_loop())
        now = discord.utils.utcnow().timestamp()
        success = True
        for configuration in await self.queues.get_all(guild=self.guild):
            eruption = await self.queues.get_current_eruption(
                guild=self.guild,
                channel_id=configuration.channel_id,
                now=now,
            )
            if eruption is None:
                continue
            if not await self.compose_overviews(configuration, eruption):
                success = False
            for phase in await self.queues.get_phases(eruption.id):
                if not await self._ensure_phase_thread(
                    configuration,
                    eruption,
                    phase,
                ):
                    success = False
        return success

    async def configure_queue(
        self,
        *,
        channel_id: int,
        title: str,
        description: str,
        role_id: int,
        modal_prompt: str,
        start_date: str,
        timezone_name: str,
        phase_hours: tuple[tuple[str, int], ...],
        start_time: str = "00:00",
        remove_role_on_reset: bool = False,
        reminder_settings: tuple[bool, int, bool, int, bool, int] = (
            False,
            60,
            False,
            60,
            False,
            15,
        ),
    ) -> str:
        if not title.strip() or len(title) > 256 or len(description) > 4000:
            return "invalid"
        if not modal_prompt.strip() or len(modal_prompt) > 45:
            return "invalid"
        role = self.guild.get_role(role_id)
        if role is None or role.is_default():
            return "invalid"
        if not self._valid_reminder_settings(reminder_settings, phase_hours):
            return "invalid_schedule"
        schedule = phase_schedule(start_date, timezone_name, phase_hours, start_time)
        if schedule is None:
            return "invalid_schedule"
        starts_at, ends_at, phases = schedule
        now = discord.utils.utcnow().timestamp()
        if starts_at <= now:
            active = await self.queues.get_current_eruption(
                guild=self.guild, channel_id=channel_id, now=now
            )
            if active is None or active.starts_at != starts_at:
                return "past"
        if not await self.queues.ensure_schema():
            return "error"
        eruption_id = await self.queues.create_eruption(
            guild=self.guild,
            channel_id=channel_id,
            title=title.strip(),
            description=description.strip(),
            role_id=role_id,
            modal_prompt=modal_prompt.strip(),
            starts_at=starts_at,
            ends_at=ends_at,
            timezone_name=timezone_name,
            phases=phases,
            created_at=now,
            phase_hours=phase_hours,
            remove_role_on_reset=remove_role_on_reset,
            reminder_settings=reminder_settings,
        )
        if eruption_id == "active_exists":
            active = await self.queues.get_current_eruption(
                guild=self.guild, channel_id=channel_id, now=now
            )
            if active is None:
                return "active_exists"
            current_phases = await self.queues.get_phases(active.id)
            if (
                active.starts_at != starts_at
                or active.ends_at != ends_at
                or tuple((phase.starts_at, phase.ends_at) for phase in current_phases)
                != phases
            ):
                return "active_exists"
            current_configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            if current_configuration is None:
                return "error"
            if (
                current_configuration.title != title.strip()
                or current_configuration.description != description.strip()
                or current_configuration.role_id != role_id
                or current_configuration.modal_prompt != modal_prompt.strip()
            ):
                return "active_exists"
            updated = await self.queues.update_settings_for_eruption(
                guild=self.guild,
                configuration=current_configuration,
                title=title.strip(),
                description=description.strip(),
                role_id=role_id,
                modal_prompt=modal_prompt.strip(),
                timezone_name=timezone_name,
                phase_hours=phase_hours,
                remove_role_on_reset=remove_role_on_reset,
                reminder_settings=reminder_settings,
                eruption_id=active.id,
                now=now,
            )
            return "settings_saved" if updated else "error"
        if eruption_id == "error":
            return "error"
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        eruption = await self.queues.get_eruption(
            guild=self.guild,
            eruption_id=eruption_id,
        )
        if configuration is None or eruption is None:
            return "error"
        if not await self.compose_overviews(configuration, eruption):
            return "discord_error"
        for phase in await self.queues.get_phases(eruption_id):
            if not await self._ensure_phase_thread(configuration, eruption, phase):
                return "discord_error"
        return "saved"

    @staticmethod
    def _valid_reminder_settings(
        settings: tuple[bool, int, bool, int, bool, int],
        phases: tuple[tuple[str, int], ...],
    ) -> bool:
        start_on, start_min, end_on, end_min, phase_on, phase_min = settings
        return (
            1 <= start_min < 1440
            and 1 <= end_min < 1440
            and 1
            <= phase_min
            < min((duration * 60 for _, duration in phases), default=0)
        )

    async def reset_queue(
        self,
        configuration: QueueConfiguration,
        eruption: Eruption,
        starts_at: float,
        ends_at: float,
        phases: tuple[tuple[float, float], ...],
    ) -> str:
        if not configuration.phase_hours:
            return "failed"
        if configuration.remove_role_on_reset:
            role = self.guild.get_role(configuration.role_id)
            if role is None:
                _logger.error(
                    "%s Cannot reset queue: configured QS role %s is missing.",
                    self.guild.name,
                    configuration.role_id,
                )
                return "failed"
            try:
                members = self.guild.fetch_members(limit=None)
                async for member in members:
                    if role not in member.roles:
                        continue
                    try:
                        await member.remove_roles(role, reason="QS queue reset")
                    except discord.HTTPException:
                        _logger.exception(
                            "Could not remove QS role from member %s.", member.id
                        )
                        return "failed"
            except discord.HTTPException:
                _logger.exception("Could not enumerate guild members for QS reset.")
                return "failed"

        channel = self.guild.get_channel(configuration.channel_id)
        if not isinstance(channel, discord.TextChannel):
            _logger.error(
                "QS reset target channel %s is unavailable.", configuration.channel_id
            )
            return "failed"
        message_ids = {
            value
            for value in (
                configuration.message_id,
                configuration.destruction_message_id,
            )
            if value is not None
        }
        try:
            for message_id in message_ids:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except discord.NotFound:
                    pass
            for phase in await self.queues.get_phases(eruption.id):
                if phase.thread_id is None:
                    continue
                thread = self.guild.get_channel_or_thread(phase.thread_id)
                if thread is None:
                    try:
                        thread = await self.guild.fetch_channel(phase.thread_id)
                    except discord.NotFound:
                        continue
                if not isinstance(thread, discord.Thread):
                    _logger.error(
                        "QS reset reference %s does not resolve to a thread.",
                        phase.thread_id,
                    )
                    return "failed"
                if phase.message_id is not None:
                    try:
                        await thread.get_partial_message(phase.message_id).delete()
                    except discord.NotFound:
                        pass
                await thread.delete(reason="QS queue reset")
        except discord.HTTPException:
            _logger.exception(
                "%s Discord cleanup failed during QS reset; runtime data retained.",
                self.guild.name,
            )
            return "failed"
        reset = await self.queues.reset_eruption(
            guild=self.guild,
            configuration=configuration,
            old_eruption_id=eruption.id,
            starts_at=starts_at,
            ends_at=ends_at,
            phases=phases,
            now=discord.utils.utcnow().timestamp(),
        )
        if not reset:
            return "failed"
        updated = await self.queues.get(
            guild=self.guild, channel_id=configuration.channel_id
        )
        upcoming = await self.queues.get_current_eruption(
            guild=self.guild,
            channel_id=configuration.channel_id,
            now=discord.utils.utcnow().timestamp(),
        )
        if updated is None or upcoming is None:
            return "partial"
        if not await self.compose_overviews(updated, upcoming):
            return "partial"
        for phase in await self.queues.get_phases(upcoming.id):
            if not await self._ensure_phase_thread(updated, upcoming, phase):
                return "partial"
        return "saved"

    async def _reminder_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = discord.utils.utcnow().timestamp()
            try:
                for reminder in await self.queues.due_reminders(now):
                    if not await self.queues.claim_reminder(reminder, now):
                        continue
                    try:
                        success = await self._send_reminder(reminder, now)
                    except discord.HTTPException:
                        _logger.exception(
                            "Failed to deliver QS reminder %s.", reminder.kind
                        )
                        success = False
                    await self.queues.finish_reminder(
                        reminder, success=success, retry_at=now + 60
                    )
            except Exception:
                _logger.exception("QS reminder polling failed.")

    async def _send_reminder(self, reminder: QueueReminder, now: float) -> bool:
        # Fetch the reminder's current event details immediately before delivery.
        event = await self.queues.get_eruption(
            guild=self.guild, eruption_id=reminder.eruption_id
        )
        if event is None or now >= reminder.event_at:
            await self.queues.skip_reminder(reminder)
            return True
        config = await self.queues.get(guild=self.guild, channel_id=event.channel_id)
        if config is None:
            return False
        if reminder.phase_id is None:
            enabled = (
                config.eruption_start_reminder_enabled
                if reminder.kind == "eruption_start"
                else config.eruption_end_reminder_enabled
            )
            actual_time = (
                event.starts_at if reminder.kind == "eruption_start" else event.ends_at
            )
            if not enabled or actual_time != reminder.event_at:
                await self.queues.skip_reminder(reminder)
                return True
            channel = self.guild.get_channel(event.channel_id)
            if not isinstance(channel, discord.TextChannel):
                return False
            role = self.guild.get_role(config.role_id)
            label = "start" if reminder.kind == "eruption_start" else "end"
            content = t(
                self.guild,
                f"queue.reminder.eruption_{label}",
                role=f"<@&{role.id}>" if role is not None else "",
            )
            allowed = (
                discord.AllowedMentions(roles=[role])
                if role
                else discord.AllowedMentions.none()
            )
            await channel.send(content, allowed_mentions=allowed)
            return True
        phase = next(
            (
                phase
                for phase in await self.queues.get_phases(event.id)
                if phase.index == reminder.phase_id
            ),
            None,
        )
        if (
            not config.phase_start_reminder_enabled
            or phase is None
            or phase.thread_id is None
            or phase.starts_at != reminder.event_at
        ):
            await self.queues.skip_reminder(reminder)
            return True
        thread = self.guild.get_channel_or_thread(phase.thread_id)
        if not isinstance(thread, discord.Thread):
            return False
        members = await self.queues.phase_participants(phase.id)
        allowed = discord.AllowedMentions(
            users=[discord.Object(id=member_id) for member_id in members]
        )
        mentions = " ".join(f"<@{member_id}>" for member_id in members)
        await thread.send(
            t(self.guild, "queue.reminder.phase_start", members=mentions),
            allowed_mentions=allowed,
        )
        return True

    async def remove_queue(self, channel_id: int) -> bool:
        return await self.queues.remove_configuration(
            guild=self.guild,
            channel_id=channel_id,
        )

    async def toggle_phase_signup(
        self,
        interaction: discord.Interaction,
        eruption_id: int,
        phase_id: int,
    ) -> None:
        eruption = await self.queues.get_eruption(
            guild=self.guild,
            eruption_id=eruption_id,
        )
        configuration = (
            await self.queues.get(
                guild=self.guild,
                channel_id=eruption.channel_id,
            )
            if eruption is not None
            else None
        )
        member = interaction.user
        if (
            configuration is None
            or configuration.mode != "qs_phases"
            or not isinstance(member, discord.Member)
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_signup"),
                ephemeral=True,
            )
            return
        role = self.guild.get_role(configuration.role_id)
        phase = await self.queues.get_phase(phase_id)
        if (
            role is None
            or phase is None
            or phase.eruption_id != eruption_id
            or eruption is None
            or eruption.channel_id != configuration.channel_id
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_signup"),
                ephemeral=True,
            )
            return
        role_managed = role not in member.roles
        result = await self.queues.join_phase(
            guild=self.guild,
            eruption_id=eruption_id,
            phase_id=phase_id,
            member_id=member.id,
            joined_at=discord.utils.utcnow().timestamp(),
            role_managed=role_managed,
        )
        if result == "full":
            await interaction.response.send_message(
                t(interaction, "queue.error.participant_limit"),
                ephemeral=True,
            )
            return
        if result == "closed":
            await interaction.response.send_message(
                t(interaction, "queue.error.eruption_closed"),
                ephemeral=True,
            )
            return
        if result == "phase_closed":
            await interaction.response.send_message(
                t(interaction, "queue.error.phase_closed"),
                ephemeral=True,
            )
            return
        if result == "error":
            await interaction.response.send_message(
                t(interaction, "queue.error.signup_failed"),
                ephemeral=True,
            )
            return

        discord_error = False
        thread = (
            self.guild.get_channel_or_thread(phase.thread_id)
            if phase.thread_id is not None
            else None
        )
        if isinstance(thread, discord.Thread):
            try:
                if result == "joined":
                    if role_managed:
                        await member.add_roles(role, reason="QS phase registration")
                    await thread.add_user(member)
                elif result.startswith("left"):
                    await thread.remove_user(member)
                    if result == "left_final_role_managed" and role in member.roles:
                        await member.remove_roles(
                            role,
                            reason="QS phase registration ended",
                        )
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to synchronize QS role or phase thread membership.",
                    self.guild.name,
                )
                discord_error = True

        await interaction.response.send_message(
            t(
                interaction,
                "queue.error.discord_sync"
                if discord_error
                else f"queue.signup.{result}",
            ),
            ephemeral=True,
        )
        await self.refresh_eruption(configuration, eruption)

    async def open_destruction_modal(
        self,
        interaction: discord.Interaction,
        eruption_id: int,
        phase_id: int,
    ) -> None:
        phase = await self.queues.get_phase(phase_id)
        eruption = await self.queues.get_eruption(
            guild=self.guild,
            eruption_id=eruption_id,
        )
        configuration = (
            await self.queues.get(guild=self.guild, channel_id=eruption.channel_id)
            if eruption is not None
            else None
        )
        if (
            phase is None
            or phase.eruption_id != eruption_id
            or configuration is None
            or configuration.mode != "qs_phases"
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_signup"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            BaseDestructionModal(
                self,
                eruption_id,
                phase_id,
                configuration.modal_prompt,
            )
        )

    async def confirm_destruction(
        self,
        interaction: discord.Interaction,
        eruption_id: int,
        phase_id: int,
        details: str,
    ) -> None:
        result = await self.queues.record_destruction(
            guild=self.guild,
            eruption_id=eruption_id,
            phase_id=phase_id,
            member_id=interaction.user.id,
            confirmed_at=discord.utils.utcnow().timestamp(),
            details=details.strip(),
        )
        await interaction.response.send_message(
            t(interaction, f"queue.destruction.{result}"),
            ephemeral=True,
        )
        eruption = await self.queues.get_eruption(
            guild=self.guild,
            eruption_id=eruption_id,
        )
        if eruption is not None:
            configuration = await self.queues.get(
                guild=self.guild,
                channel_id=eruption.channel_id,
            )
            if configuration is not None:
                await self.refresh_eruption(configuration, eruption)

    async def refresh_eruption(
        self,
        configuration: QueueConfiguration,
        eruption: Eruption,
    ) -> None:
        await self.compose_overviews(configuration, eruption)
        for phase in await self.queues.get_phases(eruption.id):
            await self._ensure_phase_thread(configuration, eruption, phase)

    async def compose_overviews(
        self,
        configuration: QueueConfiguration,
        eruption: Eruption,
    ) -> bool:
        channel = self.guild.get_channel(configuration.channel_id)
        if not isinstance(channel, discord.TextChannel):
            _logger.error(
                "%s QS queue channel %s is missing or is not a text channel.",
                self.guild.name,
                configuration.channel_id,
            )
            return False
        phases = await self.queues.get_phases(eruption.id)
        participants, destroyed = await self.queues.get_eruption_counts(eruption.id)
        start = self._discord_timestamp(eruption.starts_at)
        end = self._discord_timestamp(eruption.ends_at)
        role = self.guild.get_role(configuration.role_id)
        phase_lines = [
            t(
                self.guild,
                "queue.overview.phase",
                index=phase.index,
                start=self._discord_timestamp(phase.starts_at),
                end=self._discord_timestamp(phase.ends_at),
            )
            for phase in phases
        ]
        embed = discord.Embed(
            title=configuration.title[:256],
            description=configuration.description[:4000],
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=t(self.guild, "queue.overview.window"),
            value=t(self.guild, "queue.overview.window_value", start=start, end=end),
            inline=False,
        )
        embed.add_field(
            name=t(self.guild, "queue.overview.participants"),
            value=t(
                self.guild,
                "queue.overview.participant_count",
                count=participants,
            ),
            inline=True,
        )
        embed.add_field(
            name=t(self.guild, "queue.destruction.progress"),
            value=t(
                self.guild,
                "queue.destruction.progress_value",
                destroyed=destroyed,
                open=max(participants - destroyed, 0),
            ),
            inline=True,
        )
        embed.add_field(
            name=t(self.guild, "queue.overview.phases"),
            value="\n".join(phase_lines)[:1024] or "-",
            inline=False,
        )
        if role is not None:
            embed.set_footer(
                text=f"{t(self.guild, 'queue.overview.role')}: {role.name}"
            )
        view = QueueOverviewView(
            self,
            eruption.id,
            tuple((phase.id, phase.index) for phase in phases),
        )
        try:
            message = await self._fetch_message(channel, configuration.message_id)
            if message is None:
                message = await channel.send(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await message.edit(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            destruction_message = await self._fetch_message(
                channel,
                configuration.destruction_message_id,
            )
            if destruction_message is None:
                destruction_message = await channel.send(
                    allowed_mentions=discord.AllowedMentions.none()
                )
            if (
                configuration.message_id != message.id
                or configuration.destruction_message_id != destruction_message.id
            ):
                if not await self.queues.set_main_messages(
                    guild=self.guild,
                    channel_id=configuration.channel_id,
                    overview_message_id=message.id,
                    destruction_message_id=destruction_message.id,
                ):
                    return False
            await destruction_message.edit(
                embed=await self._destruction_embed(eruption),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            self._register_view(view, message.id)
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to publish the QS queue overview in channel %s.",
                self.guild.name,
                configuration.channel_id,
            )
            return False
        return True

    @staticmethod
    async def _fetch_message(
        channel: discord.TextChannel | discord.Thread,
        message_id: int | None,
    ) -> discord.Message | None:
        if message_id is None:
            return None
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None

    async def _destruction_embed(self, eruption: Eruption) -> discord.Embed:
        participant_ids = await self.queues.get_eruption_participant_ids(eruption.id)
        destructions = await self.queues.get_destructions(eruption.id)
        destroyed_ids = {entry.member_id for entry in destructions}
        lines = [
            f"{index}. <@{entry.member_id}>"
            for index, entry in enumerate(destructions, 1)
        ]
        embed = discord.Embed(
            title=t(self.guild, "queue.destruction.overview_title"),
            description="\n".join(lines)[:4000]
            or t(self.guild, "queue.overview.empty"),
            color=discord.Color.dark_red(),
        )
        embed.add_field(
            name=t(self.guild, "queue.destruction.progress"),
            value=t(
                self.guild,
                "queue.destruction.progress_value",
                destroyed=len(destroyed_ids),
                open=max(len(participant_ids) - len(destroyed_ids), 0),
            ),
        )
        return embed

    async def _ensure_phase_thread(
        self,
        configuration: QueueConfiguration,
        eruption: Eruption,
        phase: QueuePhase,
    ) -> bool:
        channel = self.guild.get_channel(configuration.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False
        thread: discord.Thread | None = None
        if phase.thread_id is not None:
            existing = self.guild.get_channel_or_thread(phase.thread_id)
            if isinstance(existing, discord.Thread):
                thread = existing
        try:
            if thread is None:
                thread = await channel.create_thread(
                    name=f"QS {eruption.id} - Phase {phase.index}",
                    type=discord.ChannelType.private_thread,
                    invitable=False,
                    reason="QS eruption phase coordination",
                )
            members = await self.queues.get_phase_members(
                eruption_id=eruption.id,
                phase_id=phase.id,
            )
            for participant in members:
                member = self.guild.get_member(participant.member_id)
                if member is not None and member not in thread.members:
                    await thread.add_user(member)
            embed = await self._phase_embed(eruption, phase, members)
            view = PhaseThreadView(
                self,
                eruption.id,
                phase.id,
                enabled=discord.utils.utcnow().timestamp() < phase.ends_at,
            )
            message = await self._fetch_message(thread, phase.message_id)
            if message is None:
                message = await thread.send(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await message.edit(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            if phase.thread_id != thread.id or phase.message_id != message.id:
                if not await self.queues.set_phase_messages(
                    phase_id=phase.id,
                    thread_id=thread.id,
                    message_id=message.id,
                ):
                    return False
            self._register_view(view, message.id)
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to create or refresh QS phase %s thread.",
                self.guild.name,
                phase.id,
            )
            return False
        return True

    async def _phase_embed(
        self,
        eruption: Eruption,
        phase: QueuePhase,
        members: tuple[PhaseParticipant, ...],
    ) -> discord.Embed:
        lines = []
        for index, participant in enumerate(members, 1):
            member = self.guild.get_member(participant.member_id)
            display = (
                member.mention if member is not None else f"<@{participant.member_id}>"
            )
            line = f"{index}. {display}"
            lines.append(f"**{line}**" if index <= 8 else line)
        embed = discord.Embed(
            title=t(self.guild, "queue.phase.title", index=phase.index),
            description="\n".join(lines)[:4000]
            or t(self.guild, "queue.overview.empty"),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=t(self.guild, "queue.phase.window"),
            value=t(
                self.guild,
                "queue.overview.window_value",
                start=self._discord_timestamp(phase.starts_at),
                end=self._discord_timestamp(phase.ends_at),
            ),
            inline=False,
        )
        participants, destroyed = await self.queues.get_eruption_counts(eruption.id)
        embed.set_footer(
            text=t(
                self.guild,
                "queue.destruction.progress_value",
                destroyed=destroyed,
                open=max(participants - destroyed, 0),
            )
        )
        return embed

    def _register_view(self, view: discord.ui.View, message_id: int) -> None:
        key = (view.__class__.__name__, message_id)
        if key in self._registered_views:
            return
        self.client.add_view(view, message_id=message_id)
        self._registered_views.add(key)

    @staticmethod
    def _discord_timestamp(value: float) -> str:
        timestamp = datetime.fromtimestamp(value, timezone.utc)
        return discord.utils.format_dt(timestamp, style="F")

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        if channel.guild.id != self.guild.id:
            return False
        configuration = await self.queues.get(
            guild=self.guild,
            channel_id=channel.id,
        )
        if configuration is None or configuration.mode != "qs_phases":
            return False
        await self.remove_queue(channel.id)
        return True
