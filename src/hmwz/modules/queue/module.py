from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

import discord

from hmwz import events, sqlite_db
from hmwz.i18n import t
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import edit_message, send_message
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.registry import register

from .overview import QueueOverview
from .modes import create_queue_modes
from .modes.protocol import QueueModeSetup
from .repository import (
    QueueConfiguration,
    QueueMode,
    QueueRepository,
    QueueRun,
    QueueSeason,
)
from .rules import can_start_early, season_start_timestamp, valid_run_range
from .views import (
    EarlyVoteView,
    QueueOverviewView,
    RunConfirmationView,
    SeasonTaskCompletionModal,
    SeasonOverviewView,
    SeasonGoalView,
    SeasonTaskSelectView,
    StageAction,
    StageSelectView,
)

_logger = logging.getLogger(__name__)
QueueAction = Literal["join", "leave", "vote", "toggle"]


@register
class QueueModule(BasicModule):
    """Manage guild queues, staged start votes, and season goal runs."""

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        super().__init__(guild, client)
        if not isinstance(self.database, sqlite_db.Database):
            raise RuntimeError("Queue module requires a database.")
        self.queues = QueueRepository(self.database)
        self.queue_modes = create_queue_modes()
        self._queue_locks: dict[int, asyncio.Lock] = {}
        self._overview_messages: dict[int, discord.Message] = {}
        self._registered_views: set[tuple[int, int]] = set()
        self._confirmation_enabled_runs: set[int] = set()
        self._maintenance_task: asyncio.Task[None] | None = None

    async def sync(self, startup: bool = False) -> bool:
        return await self.queues.ensure_schema()

    async def ensure(self) -> bool:
        if not await self.queues.ensure_schema():
            return False
        success = True
        for configuration in await self.queues.get_all(guild=self.guild):
            if (
                configuration.mode == "seasons"
                and not await self._ensure_season_threads(configuration.channel_id)
            ):
                success = False
            if not await self.compose_overview(configuration.channel_id):
                success = False
            if not await self._start_available_runs(configuration.channel_id):
                success = False
        for run in await self.queues.get_active_runs(guild=self.guild):
            await self._register_run_view(run)
            if time.time() >= run.confirmation_available_at:
                if await self._refresh_run_message(run.id):
                    self._confirmation_enabled_runs.add(run.id)
        for (
            vote_id,
            channel_id,
            _stage_index,
            message_id,
        ) in await self.queues.get_open_votes(guild=self.guild):
            self._register_view(EarlyVoteView(self, vote_id), message_id)
            await self._refresh_vote_message(vote_id, channel_id, message_id)
        self._ensure_maintenance_task()
        return success

    # Queue setup and lifecycle
    async def configure(
        self,
        *,
        channel_id: int,
        title: str,
        description: str,
        min_players: int,
        max_players: int,
        mode: QueueMode,
        confirmation_delay_minutes: int,
        ping_participants: bool,
        stages: tuple[str, ...],
        seasons: tuple[str, ...],
        season_goal_limit: int,
        season_goal_description: str,
        season_start_date: str | None = None,
        stage_prefix: str = "",
        season_duration_hours: int = 24,
        season_tasks: tuple[tuple[str, int], ...] = (),
        confirmed_mode_change: bool = False,
    ) -> bool:
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            timezone = await self.client.get_guild_timezone(self.guild.id)
            return await self._configure_locked(
                channel_id=channel_id,
                title=title,
                description=description,
                min_players=min_players,
                max_players=max_players,
                mode=mode,
                confirmation_delay_minutes=confirmation_delay_minutes,
                ping_participants=ping_participants,
                stages=stages,
                seasons=seasons,
                season_goal_limit=season_goal_limit,
                season_goal_description=season_goal_description,
                season_start_date=season_start_date,
                timezone=timezone,
                stage_prefix=stage_prefix,
                season_duration_hours=season_duration_hours,
                season_tasks=season_tasks,
                confirmed_mode_change=confirmed_mode_change,
            )

    async def _configure_locked(
        self,
        *,
        channel_id: int,
        title: str,
        description: str,
        min_players: int,
        max_players: int,
        mode: QueueMode,
        confirmation_delay_minutes: int,
        ping_participants: bool,
        stages: tuple[str, ...],
        seasons: tuple[str, ...],
        season_goal_limit: int,
        season_goal_description: str,
        timezone: str,
        season_start_date: str | None = None,
        stage_prefix: str = "",
        season_duration_hours: int = 24,
        season_tasks: tuple[tuple[str, int], ...] = (),
        confirmed_mode_change: bool = False,
    ) -> bool:
        if not season_tasks and season_goal_description.strip():
            season_tasks = ((season_goal_description, season_goal_limit),)
        if mode == "seasons" and season_tasks:
            season_goal_description, season_goal_limit = season_tasks[0]
        if not self._is_valid_configuration(
            min_players=min_players,
            max_players=max_players,
            mode=mode,
            confirmation_delay_minutes=confirmation_delay_minutes,
            stages=stages,
            seasons=seasons,
            season_goal_limit=season_goal_limit,
            season_goal_description=season_goal_description,
            season_start_date=season_start_date,
            timezone=timezone,
            stage_prefix=stage_prefix,
            season_duration_hours=season_duration_hours,
            season_tasks=season_tasks,
        ):
            return False
        if not await self.queues.ensure_schema():
            return False
        existing = await self.queues.get(guild=self.guild, channel_id=channel_id)
        changing_mode = existing is not None and existing.mode != mode
        if changing_mode and not confirmed_mode_change:
            return False
        previous_seasons = (
            await self.queues.get_seasons(guild=self.guild, channel_id=channel_id)
            if existing is not None and existing.mode == "seasons"
            else ()
        )
        if changing_mode:
            runs = await self.queues.get_runs(guild=self.guild, channel_id=channel_id)
            if not await self._delete_run_threads(runs):
                return False
            if existing is not None and existing.mode == "seasons":
                if not await self._delete_season_threads(channel_id):
                    return False
            if not await self.queues.clear_mode_data(
                guild=self.guild, channel_id=channel_id
            ):
                return False
            self._confirmation_enabled_runs.difference_update(run.id for run in runs)
        elif (
            existing is not None
            and mode == "seasons"
            and await self._season_schedule_changed(
                existing,
                channel_id,
                seasons,
                season_start_date or "",
                timezone,
            )
        ):
            if not await self._reset_season_queue_locked(channel_id):
                return False
        if not await self.queues.configure(
            guild=self.guild,
            channel_id=channel_id,
            title=title,
            description=description,
            min_players=min_players,
            max_players=max_players,
            mode=mode,
            confirmation_delay_minutes=confirmation_delay_minutes,
            ping_participants=ping_participants,
            season_start_date=season_start_date or "",
            timezone=timezone,
            stage_prefix=stage_prefix,
            season_duration_hours=season_duration_hours,
        ):
            return False
        if not await self._save_mode_configuration(
            channel_id=channel_id,
            mode=mode,
            stages=stages,
            seasons=seasons,
            season_goal_limit=season_goal_limit,
            season_goal_description=season_goal_description,
            season_start_date=season_start_date,
            timezone=timezone,
            season_duration_hours=season_duration_hours,
            season_tasks=season_tasks,
        ):
            return False
        if not await self._delete_removed_season_threads(
            previous_seasons=previous_seasons,
            mode=mode,
            seasons=seasons,
        ):
            return False
        if mode == "seasons" and not await self._ensure_season_threads(channel_id):
            return False
        if not await self.compose_overview(channel_id):
            return False
        self._ensure_maintenance_task()
        return True

    def _ensure_maintenance_task(self) -> None:
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def _season_schedule_changed(
        self,
        existing: QueueConfiguration,
        channel_id: int,
        seasons: tuple[str, ...],
        start_date: str,
        timezone: str,
    ) -> bool:
        existing_seasons = await self.queues.get_seasons(
            guild=self.guild, channel_id=channel_id
        )
        expected_starts = {
            season: season_start_timestamp(start_date, season, timezone)
            for season in seasons
        }
        existing_starts = {season.name: season.starts_at for season in existing_seasons}
        return (
            existing.season_start_date != start_date
            or {season.name for season in existing_seasons} != set(seasons)
            or any(start is None for start in expected_starts.values())
            or existing_starts != expected_starts
        )

    async def _save_mode_configuration(
        self,
        *,
        channel_id: int,
        mode: QueueMode,
        stages: tuple[str, ...],
        seasons: tuple[str, ...],
        season_goal_limit: int,
        season_goal_description: str,
        season_start_date: str | None,
        timezone: str,
        season_duration_hours: int,
        season_tasks: tuple[tuple[str, int], ...],
    ) -> bool:
        if not await self.queues.replace_stages(
            guild=self.guild,
            channel_id=channel_id,
            stages=stages if mode == "stages" else (),
        ):
            return False
        if not await self.queues.replace_seasons(
            guild=self.guild,
            channel_id=channel_id,
            seasons=seasons if mode == "seasons" else (),
            goal_limit=season_goal_limit,
            goal_description=season_goal_description,
            start_date=season_start_date if mode == "seasons" else None,
            timezone=timezone,
            duration_hours=season_duration_hours,
        ):
            return False
        return await self.queues.replace_season_tasks(
            guild=self.guild,
            channel_id=channel_id,
            tasks=season_tasks if mode == "seasons" else (),
        )

    async def _delete_removed_season_threads(
        self,
        *,
        previous_seasons: tuple[QueueSeason, ...],
        mode: QueueMode,
        seasons: tuple[str, ...],
    ) -> bool:
        retained_season_indexes = (
            {int(hour[:2]) for hour in seasons} if mode == "seasons" else set()
        )
        for season in previous_seasons:
            if (
                season.index not in retained_season_indexes
                and season.thread_id is not None
                and not await self._delete_thread(
                    season.thread_id, f"season {season.name}"
                )
            ):
                return False
        return True

    def _is_valid_configuration(
        self,
        *,
        min_players: int,
        max_players: int,
        mode: QueueMode,
        confirmation_delay_minutes: int,
        stages: tuple[str, ...],
        seasons: tuple[str, ...],
        season_goal_limit: int,
        season_goal_description: str,
        season_start_date: str | None,
        timezone: str,
        stage_prefix: str,
        season_duration_hours: int = 24,
        season_tasks: tuple[tuple[str, int], ...] = (),
    ) -> bool:
        if not valid_run_range(min_players, max_players):
            return False
        if not 0 <= confirmation_delay_minutes <= 10080:
            return False
        return self.queue_modes[mode].validate_setup(
            QueueModeSetup(
                stage_count=len(stages),
                stage_prefix=stage_prefix,
                stage_labels=stages,
                seasons=seasons,
                season_goal_limit=season_goal_limit,
                season_goal_description=season_goal_description,
                season_start_date=season_start_date,
                timezone=timezone,
                season_duration_hours=season_duration_hours,
                season_tasks=season_tasks
                or (
                    ((season_goal_description, season_goal_limit),)
                    if season_goal_description.strip()
                    else ()
                ),
            )
        )

    async def remove_queue(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            return False
        if any(
            run.channel_id == channel_id
            for run in await self.queues.get_active_runs(guild=self.guild)
        ):
            return False
        runs = await self.queues.get_runs(guild=self.guild, channel_id=channel_id)
        season_thread_ids = {
            season.thread_id
            for season in await self.queues.get_seasons(
                guild=self.guild, channel_id=channel_id
            )
            if season.thread_id is not None
        }
        if not await self._delete_run_threads(
            tuple(run for run in runs if run.thread_id not in season_thread_ids)
        ):
            return False
        if not await self._delete_season_threads(channel_id):
            return False
        if not await self.queues.remove(guild=self.guild, channel_id=channel_id):
            return False
        self._confirmation_enabled_runs.difference_update(run.id for run in runs)
        message = self._overview_messages.pop(channel_id, None)
        if message is None and configuration.message_id is not None:
            channel = self.guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(configuration.message_id)
                except discord.NotFound:
                    message = None
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to fetch removed queue overview in channel %s.",
                        self.guild.name,
                        channel_id,
                    )
        if message is not None:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to delete removed queue overview in channel %s.",
                    self.guild.name,
                    channel_id,
                )
        return True

    async def _delete_run_threads(self, runs: tuple[QueueRun, ...]) -> bool:
        for run in runs:
            thread = self.guild.get_channel_or_thread(run.thread_id)
            if not isinstance(thread, discord.Thread):
                try:
                    fetched = await self.client.fetch_channel(run.thread_id)
                except discord.NotFound:
                    continue
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to fetch queue run thread %s for removal.",
                        self.guild.name,
                        run.thread_id,
                    )
                    return False
                if not isinstance(fetched, discord.Thread):
                    _logger.error(
                        "%s Queue run channel %s is not a thread.",
                        self.guild.name,
                        run.thread_id,
                    )
                    return False
                thread = fetched
            try:
                await thread.delete()
            except discord.NotFound:
                continue
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to delete queue run thread %s.",
                    self.guild.name,
                    run.thread_id,
                )
                return False
        return True

    async def compose_overview(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            return False
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            _logger.error(
                "%s Queue channel %s is unavailable or not a text channel.",
                self.guild.name,
                channel_id,
            )
            return False
        mode = self.queue_modes[configuration.mode]
        pools = await mode.get_pools(
            self.queues,
            self.guild,
            channel_id,
            max_players=configuration.max_players,
        )
        view = QueueOverviewView(
            self,
            channel_id,
            mode=configuration.mode,
            pools=pools,
        )
        embed = await QueueOverview.create_embed(
            self.guild, configuration, self.queues, pools
        )
        message = self._overview_messages.get(channel_id)
        if message is None and configuration.message_id not in (None, 0):
            try:
                message = await channel.fetch_message(configuration.message_id)
            except discord.NotFound:
                message = None
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch queue overview in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                return False
        try:
            if message is None:
                message = await send_message(channel, embed=embed, view=view)
                if message is None:
                    return False
                if not await self.queues.set_message(
                    guild=self.guild,
                    channel_id=channel_id,
                    message_id=message.id,
                ):
                    _logger.error(
                        "%s Failed to save queue overview message %s.",
                        self.guild.name,
                        message.id,
                    )
                    return False
            else:
                updated_message = await edit_message(message, embed=embed, view=view)
                if updated_message is None:
                    return False
                message = updated_message
            self._overview_messages[channel_id] = message
            self._register_view(view, message.id)
            return True

        except discord.HTTPException:
            _logger.exception(
                "%s Failed to publish queue overview in channel %s.",
                self.guild.name,
                channel_id,
            )
            return False

    # Season threads and participation
    async def _ensure_season_threads(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None or configuration.mode != "seasons":
            return True
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False

        success = True
        for season in await self.queues.get_seasons(
            guild=self.guild, channel_id=channel_id
        ):
            thread = await self._get_or_create_season_thread(channel, season)
            if thread is None:
                success = False
                continue
            if not await self._sync_season_thread(channel_id, season, thread):
                success = False
        return success

    async def _get_or_create_season_thread(
        self, channel: discord.TextChannel, season: QueueSeason
    ) -> discord.Thread | None:
        if season.thread_id is not None:
            cached = self.guild.get_channel_or_thread(season.thread_id)
            if isinstance(cached, discord.Thread):
                return cached
            try:
                fetched = await self.client.fetch_channel(season.thread_id)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch thread for season %s in channel %s.",
                    self.guild.name,
                    season.name,
                    channel.id,
                )
                return None
            else:
                if isinstance(fetched, discord.Thread):
                    return fetched
                _logger.error(
                    "%s Stored season channel %s is not a thread.",
                    self.guild.name,
                    season.thread_id,
                )
                return None

        try:
            return await channel.create_thread(
                name=season.name[:100],
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=10080,
            )
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to create permanent thread for season %s.",
                self.guild.name,
                season.name,
            )
            return None

    async def _sync_season_thread(
        self,
        channel_id: int,
        season: QueueSeason,
        thread: discord.Thread,
    ) -> bool:
        try:
            if thread.archived or thread.locked:
                await thread.edit(archived=False, locked=False)
            await self._add_season_members_to_thread(channel_id, season.index, thread)
            message = await self._sync_season_overview_message(
                channel_id, season, thread
            )
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to update thread for season %s.",
                self.guild.name,
                season.name,
            )
            return False

        if not await self.queues.set_season_thread(
            guild=self.guild,
            channel_id=channel_id,
            season_index=season.index,
            thread_id=thread.id,
            message_id=message.id,
        ):
            _logger.error(
                "%s Failed to save thread for season %s.",
                self.guild.name,
                season.name,
            )
            return False
        self._register_view(self._season_overview_view(channel_id, season), message.id)
        return True

    async def _add_season_members_to_thread(
        self, channel_id: int, season_index: int, thread: discord.Thread
    ) -> None:
        member_ids = await self.queues.get_season_members(
            guild=self.guild,
            channel_id=channel_id,
            season_index=season_index,
        )
        for member_id in member_ids:
            member = self.guild.get_member(member_id)
            if member is None:
                try:
                    member = await self.guild.fetch_member(member_id)
                except discord.NotFound:
                    continue
            await thread.add_user(member)

    async def _sync_season_overview_message(
        self,
        channel_id: int,
        season: QueueSeason,
        thread: discord.Thread,
    ) -> discord.Message:
        view = self._season_overview_view(channel_id, season)
        embed = await self._season_embed(channel_id, season)
        message = None
        if thread.id == season.thread_id and season.message_id is not None:
            try:
                message = await thread.fetch_message(season.message_id)
            except discord.NotFound:
                pass
        if message is None:
            return await thread.send(embed=embed, view=view)
        await message.edit(embed=embed, view=view)
        return message

    def _season_overview_view(
        self, channel_id: int, season: QueueSeason
    ) -> SeasonOverviewView:
        return SeasonOverviewView(
            self,
            channel_id,
            season.index,
            enabled=season.status == "active",
            completed=season.status == "completed",
        )

    async def _season_embed(
        self, channel_id: int, season: QueueSeason
    ) -> discord.Embed:
        participants = await self.queues.get_season_members(
            guild=self.guild,
            channel_id=channel_id,
            season_index=season.index,
        )
        goal_text = await self._season_goal_text(channel_id, season.index)
        tasks = await self.queues.get_season_tasks(
            guild=self.guild, channel_id=channel_id
        )
        embed = create_embed(
            title=season.name,
            description=t(
                self.guild,
                "queue.season.active_window",
                start=f"<t:{int(season.starts_at)}:F>",
                end=f"<t:{int(season.starts_at + season.duration_hours * 3600)}:F>",
                duration=season.duration_hours,
            ),
            color=(
                discord.Color.green()
                if season.status == "completed"
                else discord.Color.blurple()
            ),
        )
        embed.add_field(
            name=t(self.guild, "queue.season.participants"),
            value=self._season_participant_mentions(participants)
            or t(self.guild, "queue.overview.empty"),
            inline=True,
        )
        for offset in range(0, len(tasks), 8):
            embed.add_field(
                name=t(self.guild, "queue.season.task_progress"),
                value="\n".join(
                    f"• {task.label[:100]}: {task.completed} / {task.completion_limit}"
                    for task in tasks[offset : offset + 8]
                ),
                inline=False,
            )
        if not tasks:
            embed.add_field(
                name=t(self.guild, "queue.season.task_progress"),
                value=t(self.guild, "queue.season.no_tasks"),
                inline=False,
            )
        embed.add_field(
            name=t(self.guild, "queue.season.completions"),
            value=goal_text or t(self.guild, "queue.season.no_goals"),
            inline=False,
        )
        return embed

    async def _season_goal_text(self, channel_id: int, season_index: int) -> str:
        goals = await self.queues.get_task_completions(
            guild=self.guild,
            channel_id=channel_id,
            season_index=season_index,
        )
        tasks = {
            task.index: task.label
            for task in await self.queues.get_season_tasks(
                guild=self.guild, channel_id=channel_id
            )
        }
        goal_lines = [
            f"**{tasks.get(goal.task_index, t(self.guild, 'queue.season.legacy_task'))}**"
            f" — <@{goal.member_id}>" + (f": {goal.text}" if goal.text else "")
            for goal in goals
        ]
        goal_text = "\n".join(goal_lines)
        if len(goal_text) <= 1024:
            return goal_text
        return goal_text[:1018].rsplit("\n", maxsplit=1)[0] + "\n..."

    @staticmethod
    def _season_participant_mentions(participants: tuple[int, ...]) -> str:
        mentions: list[str] = []
        for member_id in participants:
            candidate = "\n".join((*mentions, f"<@{member_id}>"))
            if len(candidate) > 1024:
                break
            mentions.append(f"<@{member_id}>")
        return "\n".join(mentions)

    async def _delete_season_threads(self, channel_id: int) -> bool:
        for season in await self.queues.get_seasons(
            guild=self.guild, channel_id=channel_id
        ):
            if season.thread_id is None:
                continue
            cached = self.guild.get_channel_or_thread(season.thread_id)
            if isinstance(cached, discord.Thread):
                thread = cached
            else:
                try:
                    fetched = await self.client.fetch_channel(season.thread_id)
                except discord.NotFound:
                    continue
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to fetch thread for season %s during removal.",
                        self.guild.name,
                        season.name,
                    )
                    return False
                if not isinstance(fetched, discord.Thread):
                    _logger.error(
                        "%s Stored season channel %s is not a thread.",
                        self.guild.name,
                        season.thread_id,
                    )
                    return False
                thread = fetched
            try:
                await thread.delete()
            except discord.NotFound:
                continue
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to delete thread for season %s.",
                    self.guild.name,
                    season.name,
                )
                return False
        return True

    async def _delete_thread(self, thread_id: int, context: str) -> bool:
        cached = self.guild.get_channel_or_thread(thread_id)
        if isinstance(cached, discord.Thread):
            thread = cached
        else:
            try:
                fetched = await self.client.fetch_channel(thread_id)
            except discord.NotFound:
                return True
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch %s thread %s.",
                    self.guild.name,
                    context,
                    thread_id,
                )
                return False
            if not isinstance(fetched, discord.Thread):
                _logger.error(
                    "%s Stored channel %s for %s is not a thread.",
                    self.guild.name,
                    thread_id,
                    context,
                )
                return False
            thread = fetched
        try:
            await thread.delete()
        except discord.NotFound:
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to delete %s thread %s.",
                self.guild.name,
                context,
                thread_id,
            )
            return False
        return True

    async def reset_season_queue(self, channel_id: int) -> bool:
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            return await self._reset_season_queue_locked(channel_id)

    async def _reset_season_queue_locked(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None or configuration.mode != "seasons":
            return False
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False
        if not await self._ensure_season_threads(channel_id):
            return False

        runs = tuple(
            run
            for run in await self.queues.get_runs(
                guild=self.guild, channel_id=channel_id
            )
            if run.season_index is not None
        )
        season_threads = {
            season.thread_id
            for season in await self.queues.get_seasons(
                guild=self.guild, channel_id=channel_id
            )
            if season.thread_id is not None
        }
        bot_member = self.guild.me
        if bot_member is None:
            return False
        for season in await self.queues.get_seasons(
            guild=self.guild, channel_id=channel_id
        ):
            thread = await self._fetch_thread(season.thread_id or 0)
            if thread is None:
                return False
            if not thread.permissions_for(bot_member).manage_messages:
                _logger.error(
                    "%s Cannot reset season thread %s without Manage Messages.",
                    self.guild.name,
                    thread.id,
                )
                return False

        obsolete_runs = tuple(
            run for run in runs if run.thread_id not in season_threads
        )
        if not await self._delete_run_threads(obsolete_runs):
            return False

        for season in await self.queues.get_seasons(
            guild=self.guild, channel_id=channel_id
        ):
            thread = await self._fetch_thread(season.thread_id or 0)
            if thread is None:
                return False
            for member_id in await self.queues.get_season_members(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season.index,
            ):
                try:
                    await thread.remove_user(discord.Object(id=member_id))
                except discord.NotFound:
                    continue
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to revoke access to season %s from member %s.",
                        self.guild.name,
                        season.name,
                        member_id,
                    )
                    return False
            if not await self._clear_messages(thread, include_user_messages=True):
                return False

        if not await self._clear_messages(channel, include_user_messages=False):
            return False
        if not await self.queues.reset_season_queue(
            guild=self.guild, channel_id=channel_id
        ):
            return False
        self._confirmation_enabled_runs.difference_update(run.id for run in runs)
        self._overview_messages.pop(channel_id, None)
        return await self._ensure_season_threads(
            channel_id
        ) and await self.compose_overview(channel_id)

    async def _clear_messages(
        self,
        channel: discord.TextChannel | discord.Thread,
        *,
        include_user_messages: bool,
    ) -> bool:
        bot_user = self.client.user
        if bot_user is None:
            return False
        try:
            async for message in channel.history(limit=None):
                if not include_user_messages and message.author.id != bot_user.id:
                    continue
                if message.is_system():
                    continue
                try:
                    await message.delete()
                except discord.NotFound:
                    continue
                except discord.Forbidden as error:
                    if error.code == 50021:
                        continue
                    _logger.exception(
                        "%s Failed to clear message %s from channel %s.",
                        self.guild.name,
                        message.id,
                        channel.id,
                    )
                    return False
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to clear message %s from channel %s.",
                        self.guild.name,
                        message.id,
                        channel.id,
                    )
                    return False
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to read messages from channel %s for reset.",
                self.guild.name,
                channel.id,
            )
            return False
        return True

    async def toggle_season_membership(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        season_index: int,
    ) -> None:
        if await self._validate_queue_interaction(interaction, channel_id) is None:
            return
        season = await self.queues.get_season(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        if season is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.not_configured"), ephemeral=True
            )
            return
        thread = await self._fetch_thread(season.thread_id or 0)
        if thread is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.season_thread_unavailable"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            await self._toggle_season_membership_locked(
                interaction, channel_id, season_index, thread
            )

    async def _toggle_season_membership_locked(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        season_index: int,
        thread: discord.Thread,
    ) -> None:
        season = await self.queues.get_season(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        if season is None:
            await interaction.followup.send(
                t(interaction, "queue.error.not_configured"), ephemeral=True
            )
            return
        if thread.archived or thread.locked:
            try:
                await thread.edit(archived=False, locked=False)
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to activate season thread %s.",
                    self.guild.name,
                    thread.id,
                )
                await interaction.followup.send(
                    t(interaction, "queue.error.season_thread_unavailable"),
                    ephemeral=True,
                )
                return
        members = await self.queues.get_season_members(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        user_id = interaction.user.id
        if user_id in members:
            try:
                await thread.remove_user(discord.Object(id=user_id))
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to remove member %s from season thread %s.",
                    self.guild.name,
                    user_id,
                    thread.id,
                )
                await interaction.followup.send(
                    t(interaction, "queue.error.season_membership_failed"),
                    ephemeral=True,
                )
                return
            if not await self.queue_modes["seasons"].leave(
                self.queues,
                self.guild,
                channel_id,
                user_id,
                season_index,
            ):
                await thread.add_user(interaction.user)
                await interaction.followup.send(
                    t(interaction, "queue.error.season_membership_failed"),
                    ephemeral=True,
                )
                return
            key = "queue.season.left"
        else:
            if season.status == "completed":
                await interaction.followup.send(
                    t(interaction, "queue.error.season_completed"), ephemeral=True
                )
                return
            try:
                await thread.add_user(interaction.user)
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to add member %s to season thread %s.",
                    self.guild.name,
                    user_id,
                    thread.id,
                )
                await interaction.followup.send(
                    t(interaction, "queue.error.season_membership_failed"),
                    ephemeral=True,
                )
                return
            if not await self.queue_modes["seasons"].join(
                self.queues,
                self.guild,
                channel_id,
                user_id,
                season_index,
                time.time(),
            ):
                await thread.remove_user(interaction.user)
                await interaction.followup.send(
                    t(interaction, "queue.error.season_membership_failed"),
                    ephemeral=True,
                )
                return
            key = "queue.season.joined"
        if not await self._refresh_season_thread(channel_id, season_index):
            _logger.error(
                "%s Season membership changed but thread %s was not refreshed.",
                self.guild.name,
                thread.id,
            )
        await self.compose_overview(channel_id)
        await interaction.followup.send(
            t(interaction, key, name=season.name), ephemeral=True
        )

    async def open_season_task_selection(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        season_index: int,
    ) -> None:
        season = await self.queues.get_season(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        if (
            interaction.guild_id != self.guild.id
            or season is None
            or interaction.channel_id != season.thread_id
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return
        members = await self.queues.get_season_members(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        now = time.time()
        if interaction.user.id not in members:
            await interaction.response.send_message(
                t(interaction, "queue.error.not_season_member"), ephemeral=True
            )
            return
        if (
            season.status != "active"
            or now < season.starts_at
            or now >= season.starts_at + season.duration_hours * 3600
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.season_not_started"), ephemeral=True
            )
            return
        completion = await self.queues.get_member_task_completion(
            guild=self.guild,
            channel_id=channel_id,
            member_id=interaction.user.id,
        )
        if completion is not None:
            completed_task = next(
                (
                    task.label
                    for task in await self.queues.get_season_tasks(
                        guild=self.guild, channel_id=channel_id
                    )
                    if task.index == completion.task_index
                ),
                t(interaction, "queue.season.legacy_task"),
            )
            await interaction.response.send_message(
                t(
                    interaction,
                    "queue.error.task_already_completed",
                    task=completed_task,
                ),
                ephemeral=True,
            )
            return
        tasks = await self.queues.get_season_tasks(
            guild=self.guild, channel_id=channel_id
        )
        available_tasks = tuple(
            task for task in tasks if task.completed < task.completion_limit
        )
        if not available_tasks:
            await interaction.response.send_message(
                t(interaction, "queue.error.no_tasks_available"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            t(interaction, "queue.season.select_task"),
            view=SeasonTaskSelectView(self, channel_id, season_index, available_tasks),
            ephemeral=True,
        )

    async def open_season_task_dialog(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        season_index: int,
        task_index: int,
    ) -> None:
        season = await self.queues.get_season(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        if (
            interaction.guild_id != self.guild.id
            or season is None
            or interaction.channel_id != season.thread_id
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return
        members = await self.queues.get_season_members(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        now = time.time()
        if interaction.user.id not in members:
            await interaction.response.send_message(
                t(interaction, "queue.error.not_season_member"), ephemeral=True
            )
            return
        if (
            season.status != "active"
            or now < season.starts_at
            or now >= season.starts_at + season.duration_hours * 3600
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.season_not_started"), ephemeral=True
            )
            return
        if await self.queues.get_member_task_completion(
            guild=self.guild,
            channel_id=channel_id,
            member_id=interaction.user.id,
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.task_already_completed"),
                ephemeral=True,
            )
            return
        tasks = await self.queues.get_season_tasks(
            guild=self.guild, channel_id=channel_id
        )
        if not any(
            task.index == task_index and task.completed < task.completion_limit
            for task in tasks
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.no_tasks_available"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            SeasonTaskCompletionModal(self, channel_id, season_index, task_index)
        )

    async def record_season_task_completion(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        season_index: int,
        task_index: int,
        text: str,
    ) -> None:
        season = await self.queues.get_season(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        members = await self.queues.get_season_members(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        if (
            interaction.guild_id != self.guild.id
            or season is None
            or interaction.channel_id != season.thread_id
            or interaction.user.id not in members
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.not_season_member"), ephemeral=True
            )
            return
        now = time.time()
        if (
            season.status != "active"
            or now < season.starts_at
            or now >= season.starts_at + season.duration_hours * 3600
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.season_not_started"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            result = await self.queues.record_task_completion(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season_index,
                task_index=task_index,
                member_id=interaction.user.id,
                text=text,
                created_at=time.time(),
            )
        if result is None:
            await interaction.followup.send(
                t(interaction, "queue.error.task_completion_failed"),
                ephemeral=True,
            )
            return
        task_count, queue_completed = result
        for configured_season in await self.queues.get_seasons(
            guild=self.guild, channel_id=channel_id
        ):
            if not await self._refresh_season_thread(
                channel_id, configured_season.index
            ):
                _logger.error(
                    "%s Task completion was saved but season thread %s was not "
                    "refreshed.",
                    self.guild.name,
                    configured_season.index,
                )
        await self.compose_overview(channel_id)
        await interaction.followup.send(
            t(
                interaction,
                "queue.season.task_saved",
                count=task_count,
                status=(
                    t(interaction, "queue.season.queue_completed")
                    if queue_completed
                    else ""
                ),
            ),
            ephemeral=True,
        )

    async def _refresh_season_thread(self, channel_id: int, season_index: int) -> bool:
        season = await self.queues.get_season(
            guild=self.guild, channel_id=channel_id, season_index=season_index
        )
        if season is None:
            return False
        thread = await self._fetch_thread(season.thread_id or 0)
        if thread is None:
            return False
        return await self._sync_season_thread(channel_id, season, thread)

    # Queue registration and run creation
    async def handle_queue_action(
        self, interaction: discord.Interaction, channel_id: int, action: QueueAction
    ) -> None:
        configuration = await self._validate_queue_interaction(interaction, channel_id)
        if configuration is None:
            return
        if action == "toggle":
            waiting = await self.queues.get_waiting_members(
                guild=self.guild, channel_id=channel_id
            )
            if any(member_id == interaction.user.id for member_id, _ in waiting):
                await self._leave_queue(interaction, channel_id)
                return
        if action == "leave":
            await self._leave_queue(interaction, channel_id)
            return
        if configuration.mode == "stages":
            stages = await self.queues.get_stages(
                guild=self.guild, channel_id=channel_id
            )
            stage_action: StageAction = "vote" if action == "vote" else "join"
            await interaction.response.send_message(
                t(interaction, "queue.stage.select_action"),
                view=StageSelectView(self, channel_id, stages, stage_action),
                ephemeral=True,
            )
            return
        if action == "vote":
            await interaction.response.send_message(
                t(interaction, "queue.error.early_start_not_available"),
                ephemeral=True,
            )
            return
        await self._join_queue(interaction, channel_id, stage_index=0)

    async def handle_stage_action(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        action: StageAction,
        stage_index: int,
    ) -> None:
        if await self._validate_queue_interaction(interaction, channel_id) is None:
            return
        if action == "join":
            await self._join_queue(interaction, channel_id, stage_index)
        else:
            await self._start_early_vote(interaction, channel_id, stage_index)

    async def toggle_stage_membership(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        stage_index: int,
    ) -> None:
        configuration = await self._validate_queue_interaction(interaction, channel_id)
        if configuration is None:
            return
        if configuration.mode != "stages":
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return
        stage_exists = any(
            stage.index == stage_index
            for stage in await self.queues.get_stages(
                guild=self.guild, channel_id=channel_id
            )
        )
        if not stage_exists:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            waiting_members = await self.queues.get_waiting_members(
                guild=self.guild, channel_id=channel_id
            )
            current_pool = next(
                (
                    pool_index
                    for member_id, pool_index in waiting_members
                    if member_id == interaction.user.id
                ),
                None,
            )
            mode = self.queue_modes["stages"]
            if current_pool == stage_index:
                changed = await mode.leave(
                    self.queues,
                    self.guild,
                    channel_id,
                    interaction.user.id,
                    stage_index,
                )
                response_key = "queue.action.left"
            else:
                if current_pool is not None and not await mode.leave(
                    self.queues,
                    self.guild,
                    channel_id,
                    interaction.user.id,
                    current_pool,
                ):
                    changed = False
                else:
                    changed = await mode.join(
                        self.queues,
                        self.guild,
                        channel_id,
                        interaction.user.id,
                        stage_index,
                        time.time(),
                    )
                    if not changed and current_pool is not None:
                        restored = await mode.join(
                            self.queues,
                            self.guild,
                            channel_id,
                            interaction.user.id,
                            current_pool,
                            time.time(),
                        )
                        if not restored:
                            _logger.error(
                                "%s Failed to restore member %s to stage %s "
                                "after a failed stage switch.",
                                self.guild.name,
                                interaction.user.id,
                                current_pool,
                            )
                response_key = "queue.action.joined"
            if not changed:
                await interaction.followup.send(
                    t(
                        interaction,
                        "queue.error.not_waiting"
                        if current_pool == stage_index
                        else "queue.error.join_failed",
                    ),
                    ephemeral=True,
                )
                return
            await self._cancel_votes_if_changed(channel_id)
            if not await self._start_available_runs_locked(channel_id):
                _logger.error(
                    "%s Failed to start a full stage queue run in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                await interaction.followup.send(
                    t(interaction, "queue.error.run_start_failed"), ephemeral=True
                )
                return
        await self.compose_overview(channel_id)
        await interaction.followup.send(t(interaction, response_key), ephemeral=True)

    async def _validate_queue_interaction(
        self, interaction: discord.Interaction, channel_id: int
    ) -> QueueConfiguration | None:
        if (
            interaction.guild is None
            or interaction.guild.id != self.guild.id
            or not isinstance(interaction.user, discord.Member)
            or interaction.channel_id != channel_id
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return None
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.not_configured"), ephemeral=True
            )
            return None
        return configuration

    async def _join_queue(
        self, interaction: discord.Interaction, channel_id: int, stage_index: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            if configuration is None:
                await interaction.followup.send(
                    t(interaction, "queue.error.not_configured"), ephemeral=True
                )
                return
            waiting = await self.queues.get_waiting_members(
                guild=self.guild, channel_id=channel_id
            )
            if any(member_id == interaction.user.id for member_id, _ in waiting):
                await interaction.followup.send(
                    t(interaction, "queue.error.already_waiting"), ephemeral=True
                )
                return
            if (
                configuration.mode == "seasons"
                and not any(
                    run.channel_id == channel_id and run.season_index is not None
                    for run in await self.queues.get_active_runs(guild=self.guild)
                )
                and await self.queues.get_next_season(
                    guild=self.guild, channel_id=channel_id
                )
                is None
            ):
                await interaction.followup.send(
                    t(interaction, "queue.error.no_seasons_left"), ephemeral=True
                )
                return
            mode = self.queue_modes[configuration.mode]
            if not await mode.join(
                self.queues,
                self.guild,
                channel_id,
                interaction.user.id,
                stage_index,
                time.time(),
            ):
                await interaction.followup.send(
                    t(interaction, "queue.error.join_failed"), ephemeral=True
                )
                return
            await interaction.followup.send(
                t(interaction, "queue.action.joined"), ephemeral=True
            )
            await self._cancel_votes_if_changed(channel_id)
            if not await self._start_available_runs(channel_id):
                _logger.error(
                    "%s Failed to start a full queue run in channel %s.",
                    self.guild.name,
                    channel_id,
                )
                await interaction.followup.send(
                    t(interaction, "queue.error.run_start_failed"), ephemeral=True
                )
        await self.compose_overview(channel_id)

    async def _leave_queue(
        self, interaction: discord.Interaction, channel_id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            waiting = await self.queues.get_waiting_members(
                guild=self.guild, channel_id=channel_id
            )
            member_pool = next(
                (
                    pool_index
                    for member_id, pool_index in waiting
                    if member_id == interaction.user.id
                ),
                None,
            )
            if (
                configuration is None
                or member_pool is None
                or not await self.queue_modes[configuration.mode].leave(
                    self.queues,
                    self.guild,
                    channel_id,
                    interaction.user.id,
                    member_pool,
                )
            ):
                await interaction.followup.send(
                    t(interaction, "queue.error.not_waiting"), ephemeral=True
                )
                return
        await interaction.followup.send(
            t(interaction, "queue.action.left"), ephemeral=True
        )
        await self._cancel_votes_if_changed(channel_id)
        await self._start_available_runs(channel_id)
        await self.compose_overview(channel_id)

    async def _start_available_runs(self, channel_id: int) -> bool:
        lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            return await self._start_available_runs_locked(channel_id)

    async def _start_available_runs_locked(self, channel_id: int) -> bool:
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            return False
        if configuration.mode == "seasons":
            return True
        mode = self.queue_modes[configuration.mode]
        pools = await mode.get_pools(
            self.queues,
            self.guild,
            channel_id,
            max_players=configuration.max_players,
        )
        for pool in pools:
            while True:
                members = await self.queues.get_members(
                    guild=self.guild,
                    channel_id=channel_id,
                    stage_index=pool.index,
                )
                if len(members) < configuration.max_players:
                    break
                if configuration.mode == "seasons" and any(
                    run.channel_id == channel_id and run.season_index is not None
                    for run in await self.queues.get_active_runs(guild=self.guild)
                ):
                    break
                if not await self._start_run(
                    configuration, members[: configuration.max_players], pool.index
                ):
                    return False
        return True

    async def _resolve_run_details(
        self, configuration: QueueConfiguration, stage_index: int
    ) -> tuple[str, QueueSeason | None] | None:
        season = None
        if configuration.mode == "seasons":
            season = await self.queues.get_next_season(
                guild=self.guild, channel_id=configuration.channel_id
            )
            if season is None:
                _logger.info(
                    "%s No pending seasons remain for queue %s.",
                    self.guild.name,
                    configuration.channel_id,
                )
                return None
            if time.time() < season.starts_at:
                return None

        stage_name = configuration.title
        if configuration.mode == "stages":
            stages = await self.queues.get_stages(
                guild=self.guild, channel_id=configuration.channel_id
            )
            stage_name = next(
                (stage.name for stage in stages if stage.index == stage_index), ""
            )
            if not stage_name:
                _logger.error(
                    "%s Missing stage %s for queue %s.",
                    self.guild.name,
                    stage_index,
                    configuration.channel_id,
                )
                return None

        run_name = season.name if season is not None else stage_name
        if not run_name:
            run_name = t(self.guild, "queue.run.default_thread_name")
        return run_name, season

    def _create_run_embed(
        self,
        configuration: QueueConfiguration,
        run_name: str,
        season: QueueSeason | None,
        members: list[discord.Member],
    ) -> discord.Embed:
        embed = create_embed(
            title=season.name if season is not None else run_name,
            description=(
                season.goal_description
                if season is not None
                else t(
                    self.guild,
                    "queue.run.started",
                    minutes=configuration.confirmation_delay_minutes,
                )
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=t(self.guild, "queue.run.participants"),
            value=self._participant_mentions(members),
            inline=False,
        )
        if season is not None:
            embed.add_field(
                name=t(self.guild, "queue.season.progress"),
                value=f"0 / {season.goal_limit}",
            )
        return embed

    async def _add_run_members(
        self, thread: discord.Thread, member_ids: tuple[int, ...]
    ) -> list[discord.Member]:
        members: list[discord.Member] = []
        for member_id in member_ids:
            member = self.guild.get_member(member_id)
            if member is None:
                member = await self.guild.fetch_member(member_id)
            await thread.add_user(member)
            members.append(member)
        return members

    async def _start_run(
        self,
        configuration: QueueConfiguration,
        members: tuple[int, ...],
        stage_index: int,
        *,
        early: bool = False,
    ) -> bool:
        if not configuration.min_players <= len(members) <= configuration.max_players:
            return False
        if not early and len(members) < configuration.max_players:
            return False
        channel = self.guild.get_channel(configuration.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False
        run_details = await self._resolve_run_details(configuration, stage_index)
        if run_details is None:
            return False
        run_name, season = run_details
        thread: discord.Thread | None = None
        try:
            thread = await channel.create_thread(
                name=f"{run_name[:90]} - Run",
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=1440,
            )
            run_members = await self._add_run_members(thread, members)

            now = time.time()
            confirmation_available_at = (
                now + configuration.confirmation_delay_minutes * 60
            )
            message = await thread.send(
                embed=self._create_run_embed(
                    configuration, run_name, season, run_members
                )
            )
            run_id = await self.queues.create_run(
                guild=self.guild,
                channel_id=configuration.channel_id,
                stage_index=stage_index if configuration.mode == "stages" else None,
                season_index=season.index if season else None,
                thread_id=thread.id,
                message_id=message.id,
                members=members,
                started_at=now,
                confirmation_available_at=confirmation_available_at,
            )
            if run_id is None:
                await thread.edit(archived=True)
                return False
            run = await self.queues.get_run(run_id)
            if run is None:
                return False
            await self._announce_run_participants(
                channel,
                thread,
                run_members,
                ping=configuration.ping_participants,
                run_id=run_id,
            )
            run_view = self._run_view(run, enabled=now >= confirmation_available_at)
            view_updated = False
            try:
                await message.edit(view=run_view)
                view_updated = True
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to attach controls to run %s.",
                    self.guild.name,
                    run_id,
                )
            self._register_view(run_view, message.id)
            if view_updated and now >= confirmation_available_at:
                self._confirmation_enabled_runs.add(run.id)
            return True
        except (discord.HTTPException, discord.NotFound):
            _logger.exception(
                "%s Failed to start queue run in channel %s.",
                self.guild.name,
                configuration.channel_id,
            )
            if thread is not None:
                try:
                    await thread.edit(archived=True)
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to archive incomplete queue thread %s.",
                        self.guild.name,
                        thread.id,
                    )
            return False

    async def _announce_run_participants(
        self,
        channel: discord.TextChannel,
        thread: discord.Thread,
        members: list[discord.Member],
        *,
        ping: bool,
        run_id: int,
    ) -> None:
        template = t(
            self.guild,
            "queue.run.participant_announcement",
            members="",
            thread=thread.mention,
        )
        mention_capacity = 1900 - len(template)
        chunks: list[list[discord.Member]] = []
        current_chunk: list[discord.Member] = []
        current_length = 0
        for member in members:
            mention_length = len(member.mention) + bool(current_chunk)
            if current_chunk and current_length + mention_length > mention_capacity:
                chunks.append(current_chunk)
                current_chunk = []
                current_length = 0
                mention_length = len(member.mention)
            current_chunk.append(member)
            current_length += mention_length
        if current_chunk:
            chunks.append(current_chunk)
        for chunk in chunks:
            mentions = " ".join(member.mention for member in chunk)
            try:
                await channel.send(
                    t(
                        self.guild,
                        "queue.run.participant_announcement",
                        members=mentions,
                        thread=thread.mention,
                    ),
                    allowed_mentions=(
                        discord.AllowedMentions(
                            users=[discord.Object(id=member.id) for member in chunk]
                        )
                        if ping
                        else discord.AllowedMentions.none()
                    ),
                )
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to announce participants for queue run %s.",
                    self.guild.name,
                    run_id,
                )
                return

    def _run_view(self, run: QueueRun, *, enabled: bool) -> discord.ui.View:
        if run.season_index is not None:
            return SeasonGoalView(
                self, run.id, enabled=enabled, completed=run.status == "completed"
            )
        return RunConfirmationView(
            self, run.id, enabled=enabled, completed=run.status == "completed"
        )

    @staticmethod
    def _participant_mentions(members: list[discord.Member]) -> str:
        mentions: list[str] = []
        for member in members:
            candidate = "\n".join((*mentions, member.mention))
            if len(candidate) > 1024:
                break
            mentions.append(member.mention)
        return "\n".join(mentions)

    # Early-start voting
    async def _start_early_vote(
        self, interaction: discord.Interaction, channel_id: int, stage_index: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        configuration = await self.queues.get(guild=self.guild, channel_id=channel_id)
        if configuration is None:
            await interaction.followup.send(
                t(interaction, "queue.error.not_configured"), ephemeral=True
            )
            return
        members = await self.queues.get_members(
            guild=self.guild, channel_id=channel_id, stage_index=stage_index
        )
        if not can_start_early(
            len(members),
            min_players=configuration.min_players,
            max_players=configuration.max_players,
        ):
            await interaction.followup.send(
                t(interaction, "queue.error.vote_outside_range"), ephemeral=True
            )
            return
        if interaction.user.id not in members:
            await interaction.followup.send(
                t(interaction, "queue.error.not_vote_member"), ephemeral=True
            )
            return
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                t(interaction, "queue.error.not_configured"), ephemeral=True
            )
            return
        stage = next(
            (
                stage
                for stage in await self.queues.get_stages(
                    guild=self.guild, channel_id=channel_id
                )
                if stage.index == stage_index
            ),
            None,
        )
        if stage is None:
            await interaction.followup.send(
                t(interaction, "queue.error.not_configured"), ephemeral=True
            )
            return
        if any(
            vote[2] == stage_index
            for vote in await self.queues.get_open_votes(
                guild=self.guild, channel_id=channel_id
            )
        ):
            await interaction.followup.send(
                t(interaction, "queue.error.vote_already_open"), ephemeral=True
            )
            return
        message = await channel.send(
            t(
                self.guild,
                "queue.vote.started",
                stage=stage.name,
                count=len(members),
                minimum=configuration.min_players,
                maximum=configuration.max_players,
            ),
        )
        vote_id = await self.queues.create_early_vote(
            guild=self.guild,
            channel_id=channel_id,
            stage_index=stage_index,
            message_id=message.id,
            members=members,
        )
        if vote_id is None:
            await message.delete()
            await interaction.followup.send(
                t(interaction, "queue.error.vote_failed"), ephemeral=True
            )
            return
        await message.edit(view=EarlyVoteView(self, vote_id))
        self._register_view(EarlyVoteView(self, vote_id), message.id)
        mention_chunk: list[int] = []
        mention_text = ""
        for member_id in members:
            member_mention = f"<@{member_id}>"
            if len(mention_text) + len(member_mention) + 1 > 1800:
                await channel.send(
                    mention_text,
                    allowed_mentions=discord.AllowedMentions(
                        users=[
                            discord.Object(id=mentioned_id)
                            for mentioned_id in mention_chunk
                        ]
                    ),
                )
                mention_chunk = []
                mention_text = ""
            mention_chunk.append(member_id)
            mention_text += f"{member_mention} "
        if mention_text:
            await channel.send(
                mention_text,
                allowed_mentions=discord.AllowedMentions(
                    users=[
                        discord.Object(id=mentioned_id)
                        for mentioned_id in mention_chunk
                    ]
                ),
            )
        await interaction.followup.send(
            t(interaction, "queue.vote.created"), ephemeral=True
        )

    async def cast_early_vote(
        self, interaction: discord.Interaction, vote_id: int, approve: bool
    ) -> None:
        votes = await self.queues.get_open_votes(guild=self.guild)
        vote = next((item for item in votes if item[0] == vote_id), None)
        if vote is None or interaction.guild_id != self.guild.id:
            await interaction.response.send_message(
                t(interaction, "queue.error.vote_closed"), ephemeral=True
            )
            return
        _, channel_id, stage_index, message_id = vote
        if interaction.channel_id != channel_id:
            await interaction.response.send_message(
                t(interaction, "queue.error.invalid_context"), ephemeral=True
            )
            return
        voters = await self.queues.get_vote_members(vote_id)
        if not any(member_id == interaction.user.id for member_id, _ in voters):
            await interaction.response.send_message(
                t(interaction, "queue.error.not_vote_member"), ephemeral=True
            )
            return
        if not await self.queues.cast_vote(
            vote_id=vote_id,
            member_id=interaction.user.id,
            vote_value=int(approve),
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.already_voted"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        voters = await self.queues.get_vote_members(vote_id)
        if not approve:
            await self.queues.close_vote(vote_id=vote_id, status="rejected")
            await self._finish_vote_message(
                channel_id,
                message_id,
                t(interaction, "queue.vote.rejected_result"),
            )
            await interaction.followup.send(
                t(interaction, "queue.vote.rejected_result"), ephemeral=True
            )
            return
        if all(value == 1 for _, value in voters):
            current = await self.queues.get_members(
                guild=self.guild, channel_id=channel_id, stage_index=stage_index
            )
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            if (
                configuration is None
                or {member_id for member_id, _ in voters} != set(current)
                or not can_start_early(
                    len(current),
                    min_players=configuration.min_players,
                    max_players=configuration.max_players,
                )
            ):
                await self.queues.close_vote(vote_id=vote_id, status="cancelled")
                await self._finish_vote_message(
                    channel_id,
                    message_id,
                    t(interaction, "queue.vote.cancelled"),
                )
                await interaction.followup.send(
                    t(interaction, "queue.vote.cancelled"), ephemeral=True
                )
                return
            lock = self._queue_locks.setdefault(channel_id, asyncio.Lock())
            async with lock:
                await self.queues.close_vote(vote_id=vote_id, status="accepted")
                started = await self._start_run(
                    configuration, current, stage_index, early=True
                )
            result = (
                t(interaction, "queue.vote.run_started")
                if started
                else t(interaction, "queue.error.run_start_failed")
            )
            await self._finish_vote_message(channel_id, message_id, result)
            await interaction.followup.send(result, ephemeral=True)
            await self.compose_overview(channel_id)
            return
        await self._refresh_vote_message(vote_id, channel_id, message_id)
        await interaction.followup.send(
            t(
                interaction,
                "queue.vote.progress",
                votes=sum(value == 1 for _, value in voters),
                total=len(voters),
            ),
            ephemeral=True,
        )

    async def _cancel_votes_if_changed(self, channel_id: int) -> None:
        for (
            vote_id,
            vote_channel,
            stage_index,
            message_id,
        ) in await self.queues.get_open_votes(guild=self.guild, channel_id=channel_id):
            voters = await self.queues.get_vote_members(vote_id)
            current = await self.queues.get_members(
                guild=self.guild, channel_id=channel_id, stage_index=stage_index
            )
            if set(current) != {member_id for member_id, _ in voters}:
                await self.queues.close_vote(vote_id=vote_id, status="cancelled")
                await self._finish_vote_message(
                    vote_channel,
                    message_id,
                    t(self.guild, "queue.vote.cancelled"),
                )

    async def _refresh_vote_message(
        self, vote_id: int, channel_id: int, message_id: int
    ) -> None:
        voters = await self.queues.get_vote_members(vote_id)
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(
                content=t(
                    self.guild,
                    "queue.vote.progress",
                    votes=sum(value == 1 for _, value in voters),
                    total=len(voters),
                ),
                view=EarlyVoteView(self, vote_id),
            )
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to update early-start vote %s.",
                self.guild.name,
                vote_id,
            )

    async def _finish_vote_message(
        self, channel_id: int, message_id: int, content: str
    ) -> None:
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(content=content, view=None)
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to finalize early-start vote message %s.",
                self.guild.name,
                message_id,
            )

    # Run confirmation, season goals, and scheduled maintenance
    async def confirm_run(self, interaction: discord.Interaction, run_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        run = await self.queues.get_run(run_id)
        if (
            run is None
            or run.guild_id != self.guild.id
            or run.status != "active"
            or run.season_index is not None
            or interaction.guild_id != self.guild.id
        ):
            await interaction.followup.send(
                t(interaction, "queue.error.run_unavailable"), ephemeral=True
            )
            return
        if time.time() < run.confirmation_available_at:
            await interaction.followup.send(
                t(interaction, "queue.error.confirmation_too_early"),
                ephemeral=True,
            )
            return
        participants = await self.queues.get_run_participants(run_id)
        participant = next(
            (item for item in participants if item.member_id == interaction.user.id),
            None,
        )
        if participant is None:
            await interaction.followup.send(
                t(interaction, "queue.error.not_run_member"), ephemeral=True
            )
            return
        if participant.confirmed_at is not None:
            await interaction.followup.send(
                t(interaction, "queue.error.already_confirmed"), ephemeral=True
            )
            return
        if not await self.queues.confirm(
            run_id=run_id, member_id=interaction.user.id, confirmed_at=time.time()
        ):
            await interaction.followup.send(
                t(interaction, "queue.error.confirm_failed"), ephemeral=True
            )
            return
        participants = await self.queues.get_run_participants(run_id)
        all_confirmed = bool(participants) and all(
            item.confirmed_at is not None for item in participants
        )
        if all_confirmed:
            if not await self.queues.complete_run(run_id):
                await interaction.followup.send(
                    t(interaction, "queue.error.confirm_failed"), ephemeral=True
                )
                return
            self._confirmation_enabled_runs.discard(run_id)
            key = "queue.confirmation.completed"
        else:
            key = "queue.confirmation.saved"
        await interaction.followup.send(t(interaction, key), ephemeral=True)
        await self._refresh_run_message(run_id)
        if all_confirmed:
            await self.compose_overview(run.channel_id)

    async def record_season_goal(
        self, interaction: discord.Interaction, run_id: int, text: str
    ) -> None:
        run = await self.queues.get_run(run_id)
        if (
            run is None
            or run.guild_id != self.guild.id
            or run.season_index is None
            or run.status != "active"
            or interaction.guild_id != self.guild.id
        ):
            await interaction.response.send_message(
                t(interaction, "queue.error.run_unavailable"), ephemeral=True
            )
            return
        if not text:
            await interaction.response.send_message(
                t(interaction, "queue.error.empty_goal"), ephemeral=True
            )
            return
        if time.time() < run.confirmation_available_at:
            await interaction.response.send_message(
                t(interaction, "queue.error.confirmation_too_early"),
                ephemeral=True,
            )
            return
        season = await self.queues.get_season(
            guild=self.guild,
            channel_id=run.channel_id,
            season_index=run.season_index,
        )
        if season is None:
            await interaction.response.send_message(
                t(interaction, "queue.error.run_unavailable"), ephemeral=True
            )
            return
        if season.status != "active" or time.time() < season.starts_at:
            await interaction.response.send_message(
                t(interaction, "queue.error.season_not_started"), ephemeral=True
            )
            return
        participants = await self.queues.get_run_participants(run_id)
        if not any(item.member_id == interaction.user.id for item in participants):
            await interaction.response.send_message(
                t(interaction, "queue.error.not_run_member"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        lock = self._queue_locks.setdefault(run.channel_id, asyncio.Lock())
        async with lock:
            result = await self.queues.record_goal(
                guild=self.guild,
                channel_id=run.channel_id,
                season_index=run.season_index,
                member_id=interaction.user.id,
                text=text,
                created_at=time.time(),
            )
            if result is None:
                await interaction.followup.send(
                    t(interaction, "queue.error.goal_save_failed"), ephemeral=True
                )
                return
            goal_count, completed = result
            if not await self.queues.confirm(
                run_id=run_id,
                member_id=interaction.user.id,
                confirmed_at=time.time(),
            ):
                _logger.error(
                    "%s Goal was saved but participant confirmation could not be "
                    "updated for run %s.",
                    self.guild.name,
                    run_id,
                )
            if completed:
                await self.queues.complete_run(run_id)
                self._confirmation_enabled_runs.discard(run_id)
        await self._refresh_run_message(run_id)
        await self.compose_overview(run.channel_id)
        await interaction.followup.send(
            t(
                interaction,
                "queue.season.goal_saved",
                count=goal_count,
            ),
            ephemeral=True,
        )
        if completed:
            await self._notify_season_completed(run)
            await self._start_available_runs(run.channel_id)
            await self.compose_overview(run.channel_id)

    async def _notify_season_completed(self, run: QueueRun) -> None:
        season = await self.queues.get_season(
            guild=self.guild,
            channel_id=run.channel_id,
            season_index=run.season_index or 0,
        )
        thread = await self._fetch_thread(run.thread_id)
        if season is None or thread is None:
            return
        configuration = await self.queues.get(
            guild=self.guild, channel_id=run.channel_id
        )
        if configuration is None:
            return
        participants = await self.queues.get_run_participants(run.id)
        mentions = " ".join(f"<@{item.member_id}>" for item in participants)
        try:
            await thread.send(
                t(
                    self.guild,
                    "queue.season.completed",
                    name=season.name,
                    members=mentions,
                    count=season.goal_limit,
                ),
                allowed_mentions=(
                    discord.AllowedMentions(
                        users=[
                            discord.Object(id=item.member_id) for item in participants
                        ]
                    )
                    if configuration.ping_participants
                    else discord.AllowedMentions.none()
                ),
            )
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to notify participants of completed season %s.",
                self.guild.name,
                season.name,
            )

    async def _maintenance_loop(self) -> None:
        while True:
            try:
                await self._process_due_confirmations()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("%s Queue maintenance failed.", self.guild.name)
            await asyncio.sleep(30)

    async def _process_due_confirmations(self) -> None:
        now = time.time()
        await self._process_due_season_starts(now)
        await self._process_expired_seasons(now)
        for run in await self.queues.get_active_runs(guild=self.guild):
            if now < run.confirmation_available_at:
                continue
            configuration = await self.queues.get(
                guild=self.guild, channel_id=run.channel_id
            )
            if configuration is None:
                continue
            participants = await self.queues.get_run_participants(run.id)
            if not participants:
                _logger.error(
                    "%s Active queue run %s has no participants.",
                    self.guild.name,
                    run.id,
                )
                continue
            if run.season_index is None and all(
                item.confirmed_at is not None for item in participants
            ):
                if await self.queues.complete_run(run.id):
                    await self.compose_overview(run.channel_id)
                continue
            season = (
                await self.queues.get_season(
                    guild=self.guild,
                    channel_id=run.channel_id,
                    season_index=run.season_index,
                )
                if run.season_index is not None
                else None
            )
            if season is not None and season.status == "completed":
                continue
            if run.id not in self._confirmation_enabled_runs:
                if await self._refresh_run_message(run.id):
                    self._confirmation_enabled_runs.add(run.id)

    async def _process_expired_seasons(self, now: float) -> None:
        for channel_id, season_index in await self.queues.get_expired_seasons(
            guild=self.guild, now=now
        ):
            if not await self.queues.expire_season(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season_index,
                now=now,
            ):
                continue
            if not await self._refresh_season_thread(channel_id, season_index):
                _logger.error(
                    "%s Failed to refresh expired season %s in channel %s.",
                    self.guild.name,
                    season_index,
                    channel_id,
                )
            if not await self.compose_overview(channel_id):
                _logger.error(
                    "%s Failed to refresh overview for expired season queue %s.",
                    self.guild.name,
                    channel_id,
                )

    async def _process_due_season_starts(self, now: float) -> None:
        for channel_id, season_index in await self.queues.get_due_seasons(
            guild=self.guild, now=now
        ):
            if not await self.queues.activate_season(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season_index,
                now=now,
            ):
                continue
            if not await self._refresh_season_thread(channel_id, season_index):
                _logger.error(
                    "%s Failed to refresh season %s when it started.",
                    self.guild.name,
                    season_index,
                )

        for (
            channel_id,
            season_index,
        ) in await self.queues.get_unnotified_started_seasons(
            guild=self.guild, now=now
        ):
            configuration = await self.queues.get(
                guild=self.guild, channel_id=channel_id
            )
            season = await self.queues.get_season(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season_index,
            )
            if configuration is None or season is None:
                continue
            if not await self._refresh_season_thread(channel_id, season_index):
                continue
            thread = await self._fetch_thread(season.thread_id or 0)
            if thread is None:
                continue
            members = await self.queues.get_season_members(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season_index,
            )
            mentions = " ".join(f"<@{member_id}>" for member_id in members)
            try:
                await thread.send(
                    t(
                        self.guild,
                        "queue.season.started",
                        name=season.name,
                        thread=thread.mention,
                        members=mentions or t(self.guild, "queue.overview.empty"),
                        start=f"<t:{int(season.starts_at)}:F>",
                    ),
                    allowed_mentions=(
                        discord.AllowedMentions(
                            users=[
                                discord.Object(id=member_id) for member_id in members
                            ]
                        )
                        if configuration.ping_participants
                        else discord.AllowedMentions.none()
                    ),
                )
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to announce the start of season %s.",
                    self.guild.name,
                    season.name,
                )
                continue
            if not await self.queues.mark_season_start_notified(
                guild=self.guild,
                channel_id=channel_id,
                season_index=season_index,
            ):
                _logger.error(
                    "%s Season %s started but its notification was not recorded.",
                    self.guild.name,
                    season.name,
                )

    async def _refresh_run_message(self, run_id: int) -> bool:
        run = await self.queues.get_run(run_id)
        if run is None:
            return False
        participants = await self.queues.get_run_participants(run_id)
        completed = run.status == "completed"
        thread = await self._fetch_thread(run.thread_id)
        if thread is None:
            return False
        if run.season_index is not None:
            season = await self.queues.get_season(
                guild=self.guild,
                channel_id=run.channel_id,
                season_index=run.season_index,
            )
            if season is None:
                return False
            goal_text = await self._season_goal_text(run.channel_id, run.season_index)
            embed = create_embed(
                title=season.name,
                description=season.goal_description,
                color=(
                    discord.Color.green()
                    if season.status == "completed"
                    else discord.Color.blurple()
                ),
            )
            embed.add_field(
                name=t(self.guild, "queue.season.progress"),
                value=f"{season.goals_completed} / {season.goal_limit}",
            )
            embed.add_field(
                name=t(self.guild, "queue.season.goals"),
                value=goal_text or t(self.guild, "queue.season.no_goals"),
                inline=False,
            )
            view = SeasonGoalView(
                self,
                run.id,
                enabled=time.time() >= run.confirmation_available_at,
                completed=completed,
            )
            try:
                message = await thread.fetch_message(run.message_id)
                await message.edit(embed=embed, view=view)
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to update season thread %s.",
                    self.guild.name,
                    run.thread_id,
                )
                return False
            return True
        confirmed_count = sum(item.confirmed_at is not None for item in participants)
        try:
            message = await thread.fetch_message(run.message_id)
            await message.edit(
                content=t(
                    self.guild,
                    "queue.run.confirmation_status",
                    confirmed=confirmed_count,
                    total=len(participants),
                ),
                view=RunConfirmationView(
                    self,
                    run.id,
                    enabled=time.time() >= run.confirmation_available_at,
                    completed=completed,
                ),
            )
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to update confirmation message for run %s.",
                self.guild.name,
                run.id,
            )
            return False
        return True

    # Persistent views and Discord events
    async def _register_run_view(self, run: QueueRun) -> None:
        if run.season_index is not None:
            view: discord.ui.View = SeasonGoalView(
                self,
                run.id,
                enabled=time.time() >= run.confirmation_available_at,
                completed=run.status == "completed",
            )
        else:
            view = RunConfirmationView(
                self,
                run.id,
                enabled=time.time() >= run.confirmation_available_at,
                completed=run.status == "completed",
            )
        self._register_view(view, run.message_id)

    def _register_view(self, view: discord.ui.View, message_id: int) -> None:
        key = (0, message_id)
        if key in self._registered_views:
            return
        self.client.add_view(view, message_id=message_id)
        self._registered_views.add(key)

    async def _fetch_thread(self, thread_id: int) -> discord.Thread | None:
        channel = self.guild.get_channel_or_thread(thread_id)
        if isinstance(channel, discord.Thread):
            return channel
        try:
            fetched = await self.client.fetch_channel(thread_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to fetch queue run thread %s.",
                self.guild.name,
                thread_id,
            )
            return None
        return fetched if isinstance(fetched, discord.Thread) else None

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        if guild.id != self.guild.id:
            return False
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            self._maintenance_task = None
        return True

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        if channel.guild.id != self.guild.id:
            return False
        if await self.queues.get(guild=self.guild, channel_id=channel.id) is None:
            return True
        return await self.remove_queue(channel.id)

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        if payload.guild_id != self.guild.id or payload.channel_id is None:
            return False
        for queue_configuration in await self.queues.get_all(guild=self.guild):
            if queue_configuration.mode != "seasons":
                continue
            for season in await self.queues.get_seasons(
                guild=self.guild, channel_id=queue_configuration.channel_id
            ):
                if (
                    season.thread_id == payload.channel_id
                    and season.message_id == payload.message_id
                ):
                    return await self._refresh_season_thread(
                        queue_configuration.channel_id, season.index
                    )
        configuration = await self.queues.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        if configuration is None or configuration.message_id != payload.message_id:
            return True
        self._overview_messages.pop(payload.channel_id, None)
        if not await self.queues.set_message(
            guild=self.guild, channel_id=payload.channel_id, message_id=0
        ):
            return False
        return await self.compose_overview(payload.channel_id)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        if payload.guild_id != self.guild.id:
            return False
        for queue_configuration in await self.queues.get_all(guild=self.guild):
            if queue_configuration.mode != "seasons":
                continue
            for season in await self.queues.get_seasons(
                guild=self.guild, channel_id=queue_configuration.channel_id
            ):
                if (
                    season.thread_id == payload.channel_id
                    and season.message_id in payload.message_ids
                ):
                    return await self._refresh_season_thread(
                        queue_configuration.channel_id, season.index
                    )
        configuration = await self.queues.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        if configuration is None or configuration.message_id not in payload.message_ids:
            return True
        self._overview_messages.pop(payload.channel_id, None)
        if not await self.queues.set_message(
            guild=self.guild, channel_id=payload.channel_id, message_id=0
        ):
            return False
        return await self.compose_overview(payload.channel_id)
