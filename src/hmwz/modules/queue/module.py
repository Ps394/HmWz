from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import discord
from zoneinfo import ZoneInfo

from hmwz import sqlite_db
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .models import (
    Eruption,
    QueueCleanupItem,
    QueueCleanupJob,
    PhaseParticipant,
    QueueConfiguration,
    QueuePhase,
    QueueReminder,
)
from .repositories import QueueRepository
from .rules import phase_schedule
from .views import (
    BaseDestructionConfirmationView,
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
        self._cleanup_task: asyncio.Task[None] | None = None

    async def sync(self, startup: bool = False) -> bool:
        return await self.queues.ensure_schema()

    async def ensure(self) -> bool:
        if not await self.queues.ensure_schema():
            return False
        if self._reminder_task is None or self._reminder_task.done():
            self._reminder_task = asyncio.create_task(self._reminder_loop())
        now = discord.utils.utcnow().timestamp()
        success = True
        for job in await self.queues.get_open_cleanup_jobs(guild=self.guild):
            try:
                result = await self._resume_cleanup_job(job)
                if result not in {"saved", "completed"}:
                    success = False
            except Exception:
                _logger.exception(
                    "Guild %s could not resume cleanup job %s in channel %s.",
                    self.guild.id,
                    job.id,
                    job.channel_id,
                )
                success = False
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
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

    async def _resume_cleanup_job(self, job: QueueCleanupJob) -> str:
        if job.operation == "remove":
            return await self.remove_queue(job.channel_id)
        if job.operation == "reset":
            configuration = await self.queues.get(
                guild=self.guild, channel_id=job.channel_id
            )
            return (
                await self.resume_reset(configuration, job)
                if configuration is not None
                else "partial"
            )
        _logger.error(
            "Guild %s channel %s cleanup job %s has unsupported operation %s.",
            self.guild.id,
            job.channel_id,
            job.id,
            job.operation,
        )
        return "failed"

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                for job in await self.queues.get_open_cleanup_jobs(guild=self.guild):
                    try:
                        await self._resume_cleanup_job(job)
                    except Exception:
                        _logger.exception(
                            "Guild %s could not retry cleanup job %s in channel %s.",
                            self.guild.id,
                            job.id,
                            job.channel_id,
                        )
            except Exception:
                _logger.exception(
                    "Guild %s cleanup polling failed.", self.guild.id
                )

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
        if not await self.queues.ensure_schema():
            return "error"
        if (
            await self.queues.get_cleanup_job(guild=self.guild, channel_id=channel_id)
            is not None
        ):
            return "cleanup_pending"
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
        timezone_name: str,
    ) -> str:
        if not configuration.phase_hours:
            return "failed"
        now = discord.utils.utcnow().timestamp()
        job_id = await self.queues.prepare_reset_cleanup(
            guild=self.guild,
            configuration=configuration,
            eruption_id=eruption.id,
            starts_at=starts_at,
            ends_at=ends_at,
            phases=phases,
            timezone_name=timezone_name,
            now=now,
        )
        if job_id is None:
            return "failed"
        job = await self.queues.get_cleanup_job(
            guild=self.guild,
            channel_id=configuration.channel_id,
            open_only=False,
        )
        if job is None or job.id != job_id or job.operation != "reset":
            return "failed"
        if job.status == "completed":
            return "saved"
        try:
            payload = json.loads(job.payload)
            saved_eruption_id = int(payload["eruption_id"])
            saved_starts_at = float(payload["starts_at"])
            saved_ends_at = float(payload["ends_at"])
            saved_phases = tuple(
                (float(start), float(end)) for start, end in payload["phases"]
            )
            saved_timezone = str(payload["timezone"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            _logger.exception(
                "Guild %s channel %s reset cleanup job %s has invalid persisted payload.",
                self.guild.id,
                configuration.channel_id,
                job_id,
            )
            return "failed"
        if saved_eruption_id != eruption.id:
            already_created = await self.queues.get_eruption_by_cleanup_job(
                guild=self.guild,
                channel_id=configuration.channel_id,
                cleanup_job_id=job_id,
            )
            if already_created is None or already_created.id != eruption.id:
                _logger.error(
                    "Guild %s channel %s reset cleanup job %s belongs to eruption %s, not %s.",
                    self.guild.id,
                    configuration.channel_id,
                    job_id,
                    saved_eruption_id,
                    eruption.id,
                )
                return "partial"

        if not await self._process_cleanup_job(job):
            return "partial"
        reset = await self.queues.reset_eruption(
            guild=self.guild,
            configuration=configuration,
            cleanup_job_id=job_id,
            old_eruption_id=saved_eruption_id,
            starts_at=saved_starts_at,
            ends_at=saved_ends_at,
            phases=saved_phases,
            timezone_name=saved_timezone,
            now=discord.utils.utcnow().timestamp(),
        )
        if not reset:
            return "failed"
        updated = await self.queues.get(
            guild=self.guild, channel_id=configuration.channel_id
        )
        if updated is None:
            await self._set_cleanup_status(job_id, configuration.channel_id, "partial")
            return "partial"
        if saved_ends_at <= discord.utils.utcnow().timestamp():
            return (
                "saved"
                if await self._set_cleanup_status(
                    job_id, configuration.channel_id, "completed"
                )
                else "partial"
            )
        upcoming = await self.queues.get_latest_eruption(
            guild=self.guild,
            channel_id=configuration.channel_id,
        )
        if upcoming is None:
            await self._set_cleanup_status(job_id, configuration.channel_id, "partial")
            return "partial"
        if not await self.compose_overviews(updated, upcoming):
            await self._set_cleanup_status(job_id, configuration.channel_id, "partial")
            return "partial"
        for phase in await self.queues.get_phases(upcoming.id):
            if not await self._ensure_phase_thread(updated, upcoming, phase):
                await self._set_cleanup_status(
                    job_id, configuration.channel_id, "partial"
                )
                return "partial"
        return (
            "saved"
            if await self._set_cleanup_status(
                job_id, configuration.channel_id, "completed"
            )
            else "partial"
        )

    async def resume_reset(
        self, configuration: QueueConfiguration, job: QueueCleanupJob
    ) -> str:
        try:
            payload = json.loads(job.payload)
            eruption_id = int(payload["eruption_id"])
            eruption = await self.queues.get_eruption(
                guild=self.guild, eruption_id=eruption_id
            )
            if eruption is None:
                eruption = await self.queues.get_eruption_by_cleanup_job(
                    guild=self.guild,
                    channel_id=configuration.channel_id,
                    cleanup_job_id=job.id,
                )
            if eruption is None:
                _logger.error(
                    "Guild %s channel %s open reset job %s references missing eruption %s.",
                    self.guild.id,
                    job.channel_id,
                    job.id,
                    eruption_id,
                )
                return "partial"
            phases = tuple(
                (float(start), float(end)) for start, end in payload["phases"]
            )
            return await self.reset_queue(
                configuration=configuration,
                eruption=eruption,
                starts_at=float(payload["starts_at"]),
                ends_at=float(payload["ends_at"]),
                phases=phases,
                timezone_name=str(payload["timezone"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            _logger.exception(
                "Guild %s channel %s reset cleanup job %s has invalid persisted payload.",
                self.guild.id,
                job.channel_id,
                job.id,
            )
            return "failed"

    async def _process_cleanup_job(self, job: QueueCleanupJob) -> bool:
        if job.status == "completed":
            return True
        try:
            json.loads(job.payload)
        except json.JSONDecodeError:
            _logger.exception(
                "Guild %s channel %s cleanup job %s has invalid persisted JSON.",
                self.guild.id,
                job.channel_id,
                job.id,
            )
            return False

        items = await self.queues.get_cleanup_items(job.id)
        for item in items:
            if item.status != "pending" or item.kind != "role_scan":
                continue
            await self._scan_cleanup_role(job, item)

        items = await self.queues.get_cleanup_items(job.id)
        for item in items:
            if item.status != "pending" or item.kind == "role_scan":
                continue
            await self._process_cleanup_item(job, item)

        remaining = await self.queues.get_cleanup_items(job.id)
        pending = any(item.status == "pending" for item in remaining)
        if not await self._set_cleanup_status(
            job.id, job.channel_id, "partial" if pending else "pending"
        ):
            return False
        return not pending

    async def _set_cleanup_status(
        self, job_id: int, channel_id: int, status: str
    ) -> bool:
        updated = await self.queues.update_cleanup_job_status(job_id, status)
        if not updated:
            _logger.error(
                "Guild %s channel %s could not save cleanup job %s status %s.",
                self.guild.id,
                channel_id,
                job_id,
                status,
            )
        return updated

    async def _set_cleanup_item(
        self,
        job: QueueCleanupJob,
        item: QueueCleanupItem,
        *,
        completed: bool,
        error: str | None = None,
    ) -> bool:
        updated = await self.queues.update_cleanup_item(
            job_id=job.id,
            kind=item.kind,
            parent_id=item.parent_id,
            resource_id=item.resource_id,
            completed=completed,
            error=error,
        )
        if not updated:
            _logger.error(
                "Guild %s channel %s could not save cleanup job %s resource %s/%s/%s.",
                self.guild.id,
                job.channel_id,
                job.id,
                item.kind,
                item.parent_id,
                item.resource_id,
            )
        return updated

    async def _scan_cleanup_role(
        self, job: QueueCleanupJob, item: QueueCleanupItem
    ) -> None:
        role = self.guild.get_role(item.resource_id)
        if role is None:
            await self._set_cleanup_item(job, item, completed=True)
            return
        try:
            members = [member async for member in self.guild.fetch_members(limit=None)]
        except discord.DiscordException as error:
            _logger.warning(
                "Guild %s channel %s could not enumerate members for cleanup job %s, role %s.",
                self.guild.id,
                job.channel_id,
                job.id,
                role.id,
                exc_info=True,
            )
            await self._set_cleanup_item(
                job, item, completed=False, error=type(error).__name__
            )
            return
        role_items = tuple(
            ("role_member", role.id, member.id)
            for member in members
            if role in member.roles
        )
        if not await self.queues.add_cleanup_items(job.id, role_items):
            _logger.error(
                "Guild %s channel %s could not persist cleanup members for job %s, role %s.",
                self.guild.id,
                job.channel_id,
                job.id,
                role.id,
            )
            return
        await self._set_cleanup_item(job, item, completed=True)

    async def _process_cleanup_item(
        self, job: QueueCleanupJob, item: QueueCleanupItem
    ) -> None:
        try:
            complete = await self._delete_cleanup_resource(item)
        except discord.HTTPException as error:
            _logger.warning(
                "Guild %s Discord cleanup failed: queue channel %s, job %s, "
                "resource %s/%s/%s.",
                self.guild.id,
                job.channel_id,
                job.id,
                item.kind,
                item.parent_id,
                item.resource_id,
                exc_info=True,
            )
            await self._set_cleanup_item(
                job, item, completed=False, error=type(error).__name__
            )
            return
        except Exception as error:
            _logger.exception(
                "Guild %s unexpected cleanup error: queue channel %s, job %s, "
                "resource %s/%s/%s.",
                self.guild.id,
                job.channel_id,
                job.id,
                item.kind,
                item.parent_id,
                item.resource_id,
            )
            await self._set_cleanup_item(
                job, item, completed=False, error=type(error).__name__
            )
            return
        await self._set_cleanup_item(
            job,
            item,
            completed=complete,
            error=None if complete else "resource_unavailable",
        )

    async def _delete_cleanup_resource(self, item: QueueCleanupItem) -> bool:
        if item.kind == "role_member":
            role = self.guild.get_role(item.parent_id or 0)
            member = self.guild.get_member(item.resource_id)
            if role is None:
                return True
            if member is None:
                try:
                    member = await self.guild.fetch_member(item.resource_id)
                except discord.NotFound:
                    return True
            if role not in member.roles:
                return True
            await member.remove_roles(role, reason="QS queue cleanup")
            return True
        if item.kind in {"queue_message", "phase_message"}:
            parent_id = item.parent_id
            if parent_id is None:
                return True
            channel = self.guild.get_channel_or_thread(parent_id)
            if channel is None:
                try:
                    channel = await self.guild.fetch_channel(parent_id)
                except discord.NotFound:
                    return True
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                try:
                    await channel.get_partial_message(item.resource_id).delete()
                except discord.NotFound:
                    return True
                return True
            _logger.error(
                "Guild %s QS cleanup message %s in %s has unsupported parent %s.",
                self.guild.id,
                item.resource_id,
                item.kind,
                parent_id,
            )
            return False
        if item.kind == "thread":
            thread = self.guild.get_channel_or_thread(item.resource_id)
            if thread is None:
                try:
                    thread = await self.guild.fetch_channel(item.resource_id)
                except discord.NotFound:
                    return True
            if isinstance(thread, discord.Thread):
                await thread.delete(reason="QS queue cleanup")
                return True
            _logger.error(
                "Guild %s QS cleanup thread %s resolved to an unsupported channel.",
                self.guild.id,
                item.resource_id,
            )
            return False
        _logger.error("Unknown QS cleanup resource kind %s.", item.kind)
        return False

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

    async def remove_queue(self, channel_id: int) -> str:
        job_id = await self.queues.prepare_remove_cleanup(
            guild=self.guild,
            channel_id=channel_id,
            now=discord.utils.utcnow().timestamp(),
        )
        if job_id is None:
            open_job = await self.queues.get_cleanup_job(
                guild=self.guild, channel_id=channel_id
            )
            if open_job is not None:
                return "reset_pending" if open_job.operation == "reset" else "partial"
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            return "failed" if configuration is not None else "completed"
        job = await self.queues.get_cleanup_job(
            guild=self.guild,
            channel_id=channel_id,
            operation="remove",
            open_only=False,
        )
        if job is None or job.id != job_id:
            return "partial"
        if not await self._process_cleanup_job(job):
            return "partial"
        if not await self._set_cleanup_status(job_id, channel_id, "completed"):
            return "partial"
        return "completed"

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
        await interaction.response.send_message(
            content=configuration.modal_prompt,
            view=BaseDestructionConfirmationView(self, eruption_id, phase_id),
            ephemeral=True,
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
                local_range=self._phase_local_range(
                    phase.starts_at, phase.ends_at, eruption.timezone
                ),
                start=self._discord_timestamp(phase.starts_at),
                end=self._discord_timestamp(phase.ends_at),
                timezone=eruption.timezone,
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
            value=t(
                self.guild,
                "queue.overview.window_value",
                start=start,
                end=end,
                local_start=self._local_datetime(eruption.starts_at, eruption.timezone),
                timezone=eruption.timezone,
            ),
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
            tuple(
                (
                    phase.id,
                    phase.index,
                    self._phase_local_range(
                        phase.starts_at, phase.ends_at, eruption.timezone
                    ),
                )
                for phase in phases
            ),
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
            title=t(
                self.guild,
                "queue.phase.title",
                index=phase.index,
                local_range=self._phase_local_range(
                    phase.starts_at, phase.ends_at, eruption.timezone
                ),
            ),
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
                timezone=eruption.timezone,
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

    @staticmethod
    def _phase_local_range(
        starts_at: float,
        ends_at: float,
        timezone_name: str,
    ) -> str:
        zone = ZoneInfo(timezone_name)
        start = datetime.fromtimestamp(starts_at, timezone.utc).astimezone(zone)
        end = datetime.fromtimestamp(ends_at, timezone.utc).astimezone(zone)
        return f"{start:%H:%M}-{end:%H:%M}"

    @staticmethod
    def _local_datetime(timestamp: float, timezone_name: str) -> str:
        local = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(
            ZoneInfo(timezone_name)
        )
        return local.strftime("%Y-%m-%d %H:%M")

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
