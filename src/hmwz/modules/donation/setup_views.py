from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

import discord

from hmwz.i18n import t

from .repository import (
    DEFAULT_DONATION_CHOICES,
    DonationChannel,
    DonationKind,
    DonationType,
)
from .rush_pricing import RUSH_DURATIONS_HOURS
from .validation import parse_amount, parse_choices, parse_rush_start

if TYPE_CHECKING:
    from .module import DonationModule

DonationSetupAction = Literal["content", "values", "recent", "ranking", "start", "save"]


@dataclass(slots=True)
class DonationSetupDraft:
    """Mutable settings collected by the donation setup menu."""

    module: DonationModule
    channel_id: int
    owner_id: int
    kind: DonationKind
    title: str
    description: str
    unit: str
    choices: tuple[str, ...]
    time_reductions: tuple[str, ...]
    goal_hours: int | None
    recent_limit: int
    show_ranking: bool
    rush_start_at: datetime | None


def donation_setup_panel(
    draft: DonationSetupDraft, interaction: discord.Interaction
) -> str:
    """Summarize the editable donation configuration."""
    kind_key = (
        "donation.setup.simple" if draft.kind == "simple" else "donation.setup.rush"
    )
    choices = (
        t(interaction, "donation.setup.fixed_rush_price")
        if draft.kind == "time_reduction"
        else t(
            interaction,
            "donation.setup.configured"
            if draft.choices
            else "donation.setup.free_entry",
        )
    )
    return t(
        interaction,
        "donation.setup.panel",
        kind=t(interaction, kind_key),
        title=draft.title or t(interaction, "donation.setup.default_title"),
        description=_status(interaction, bool(draft.description)),
        unit=_status(interaction, bool(draft.unit)),
        choices=choices,
        hours=", ".join(draft.time_reductions)
        or t(interaction, "donation.setup.not_configured"),
        goal=(
            f"{draft.goal_hours}h"
            if draft.goal_hours is not None
            else t(interaction, "donation.setup.not_configured")
        ),
        recent_limit=draft.recent_limit,
        ranking=t(
            interaction,
            "donation.setup.enabled"
            if draft.show_ranking
            else "donation.setup.disabled",
        ),
        rush_start=(
            draft.rush_start_at.astimezone(ZoneInfo("Europe/Berlin")).strftime(
                "%d.%m.%Y %H:%M"
            )
            if draft.rush_start_at is not None
            else t(interaction, "donation.setup.not_configured")
        ),
    )


def _status(interaction: discord.Interaction, is_configured: bool) -> str:
    key = (
        "donation.setup.configured"
        if is_configured
        else "donation.setup.not_configured"
    )
    return t(interaction, key)


class DonationSetupKindSelect(discord.ui.Select):
    """Select which donation workflow to configure."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        owner_id: int,
        channel_configuration: DonationChannel | None,
        donation_type: DonationType | None,
    ) -> None:
        super().__init__(
            placeholder=t(module.guild, "donation.setup.kind_prompt"),
            options=[
                discord.SelectOption(
                    label=t(module.guild, "donation.setup.simple"),
                    value="simple",
                    description=t(module.guild, "donation.setup.simple_description"),
                    default=donation_type is not None
                    and donation_type.kind == "simple",
                ),
                discord.SelectOption(
                    label=t(module.guild, "donation.setup.time_reduction"),
                    value="time_reduction",
                    description=t(
                        module.guild, "donation.setup.time_reduction_description"
                    ),
                    default=donation_type is not None
                    and donation_type.kind == "time_reduction",
                ),
            ],
            min_values=1,
            max_values=1,
        )
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.channel_configuration = channel_configuration
        self.donation_type = donation_type

    async def callback(self, interaction: discord.Interaction) -> None:
        kind = self._selected_kind()
        if kind is None:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_type"), ephemeral=True
            )
            return
        draft = self.create_draft(kind, interaction)
        await interaction.response.edit_message(
            content=donation_setup_panel(draft, interaction),
            view=DonationSetupView(draft),
        )

    def _selected_kind(self) -> DonationKind | None:
        selected_kind = self.values[0]
        if selected_kind == "simple":
            return "simple"
        if selected_kind == "time_reduction":
            return "time_reduction"
        return None

    def create_draft(
        self, kind: DonationKind, interaction: discord.Interaction
    ) -> DonationSetupDraft:
        current_type = self.donation_type
        if current_type is not None and current_type.kind != kind:
            current_type = None
        configuration = self.channel_configuration
        rush_start_at = (
            configuration.rush_start_at
            if configuration is not None and kind == "time_reduction"
            else None
        )
        if kind == "time_reduction" and rush_start_at is None:
            rush_start_at = datetime.now(ZoneInfo("Europe/Berlin"))
        return DonationSetupDraft(
            module=self.module,
            channel_id=self.channel_id,
            owner_id=self.owner_id,
            kind=kind,
            title=(
                configuration.title
                if configuration is not None
                else t(interaction, "donation.setup.default_title")
            ),
            description=configuration.description if configuration is not None else "",
            unit=(
                current_type.unit
                if current_type is not None
                else (
                    t(interaction, "donation.setup.crystals_unit")
                    if kind == "time_reduction"
                    else t(interaction, "donation.setup.credits_unit")
                )
            ),
            choices=(
                current_type.choices
                if current_type is not None and kind == "simple"
                else DEFAULT_DONATION_CHOICES
                if kind == "simple"
                else ()
            ),
            time_reductions=(
                tuple(f"{hours}h" for hours in RUSH_DURATIONS_HOURS)
                if kind == "time_reduction"
                else ()
            ),
            goal_hours=(216 if kind == "time_reduction" else None),
            recent_limit=(
                configuration.recent_limit if configuration is not None else 20
            ),
            show_ranking=(
                configuration.show_ranking if configuration is not None else True
            ),
            rush_start_at=rush_start_at,
        )


class DonationSetupOwnerView(discord.ui.View):
    """Restrict an ephemeral setup step to its initiating administrator."""

    def __init__(self, owner_id: int, *, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "donation.setup.owner_only"), ephemeral=True
        )
        return False


class DonationSetupKindView(DonationSetupOwnerView):
    """Ephemeral first step that selects the donation kind."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        owner_id: int,
        channel_configuration: DonationChannel | None = None,
        donation_type: DonationType | None = None,
    ) -> None:
        super().__init__(owner_id, timeout=180)
        self.add_item(
            DonationSetupKindSelect(
                module,
                channel_id,
                owner_id,
                channel_configuration,
                donation_type,
            )
        )


class DonationSetupButton(discord.ui.Button):
    """Open one section of the setup menu or save the configuration."""

    LABELS: dict[DonationSetupAction, str] = {
        "content": "donation.setup.edit_content",
        "values": "donation.setup.edit_values",
        "recent": "donation.setup.edit_recent",
        "ranking": "donation.setup.toggle_ranking",
        "start": "donation.setup.edit_start",
        "save": "donation.setup.save",
    }

    def __init__(
        self, setup_view: DonationSetupView, action: DonationSetupAction, row: int
    ) -> None:
        super().__init__(
            label=t(setup_view.draft.module.guild, self.LABELS[action]),
            style=(
                discord.ButtonStyle.success
                if action == "save"
                else discord.ButtonStyle.primary
            ),
            custom_id=f"donation:setup:{action}",
            row=row,
        )
        self.setup_view = setup_view
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.setup_view.handle_action(interaction, self.action)


class DonationSetupView(DonationSetupOwnerView):
    """Menu for editing each section of a donation setup."""

    def __init__(self, draft: DonationSetupDraft) -> None:
        super().__init__(draft.owner_id)
        self.draft = draft
        self.add_item(DonationSetupButton(self, "content", row=0))
        if draft.kind == "simple":
            self.add_item(DonationSetupButton(self, "values", row=0))
        if draft.kind == "time_reduction":
            self.add_item(DonationSetupButton(self, "start", row=0))
        self.add_item(DonationSetupButton(self, "recent", row=1))
        self.add_item(DonationSetupButton(self, "ranking", row=1))
        self.add_item(DonationSetupButton(self, "save", row=2))

    async def handle_action(
        self, interaction: discord.Interaction, action: DonationSetupAction
    ) -> None:
        match action:
            case "content":
                await interaction.response.send_modal(DonationContentModal(self.draft))
            case "values":
                await interaction.response.send_modal(DonationValuesModal(self.draft))
            case "recent":
                await interaction.response.send_modal(
                    DonationRecentLimitModal(self.draft)
                )
            case "ranking":
                self.draft.show_ranking = not self.draft.show_ranking
                await self.refresh(interaction)
            case "start":
                await interaction.response.send_modal(
                    DonationRushStartModal(self.draft)
                )
            case "save":
                await self.save(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=donation_setup_panel(self.draft, interaction), view=self
        )

    async def save(self, interaction: discord.Interaction) -> None:
        if self.draft.kind == "simple" and not self.draft.unit:
            await interaction.response.send_message(
                t(interaction, "donation.error.unit_required"), ephemeral=True
            )
            return
        if not 1 <= self.draft.recent_limit <= 20:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_recent_limit"), ephemeral=True
            )
            return
        if self.draft.kind == "time_reduction" and self.draft.rush_start_at is None:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_setup_values"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        if not await _save_setup(self.draft, interaction):
            return
        self.stop()
        await interaction.edit_original_response(
            content=t(interaction, "donation.setup.complete"), view=None
        )


async def _save_setup(
    draft: DonationSetupDraft, interaction: discord.Interaction
) -> bool:
    donation_type = DonationType(
        name=t(
            draft.module.guild,
            (
                "donation.setup.simple"
                if draft.kind == "simple"
                else "donation.setup.rush"
            ),
        ),
        kind=draft.kind,
        unit=draft.unit or t(draft.module.guild, "donation.setup.crystals_unit"),
        input_mode="choice" if draft.kind == "simple" and draft.choices else "free",
        choices=draft.choices if draft.kind == "simple" else (),
        time_reductions=(
            tuple(f"{hours}h" for hours in RUSH_DURATIONS_HOURS)
            if draft.kind == "time_reduction"
            else ()
        ),
    )
    history_units = await draft.module.donations.get_history_units(
        guild=draft.module.guild, channel_id=draft.channel_id
    )
    if history_units is None:
        await _send_setup_followup_error(interaction, "donation.error.setup_save")
        return False
    if history_units and set(history_units) != {donation_type.unit}:
        await _send_setup_followup_error(interaction, "donation.error.unit_locked")
        return False
    saved = await draft.module.configure_donation(
        draft.channel_id,
        title=draft.title or t(interaction, "donation.setup.default_title"),
        description=draft.description,
        donation_type=donation_type,
        goal_hours=draft.goal_hours if draft.kind == "time_reduction" else None,
        recent_limit=draft.recent_limit,
        show_ranking=draft.show_ranking,
        rush_start_at=(draft.rush_start_at if draft.kind == "time_reduction" else None),
    )
    if not saved:
        await _send_setup_followup_error(interaction, "donation.error.setup_save")
        return False
    return True


async def _send_setup_followup_error(
    interaction: discord.Interaction, translation_key: str
) -> None:
    await interaction.followup.send(t(interaction, translation_key), ephemeral=True)


class DonationContentModal(discord.ui.Modal):
    """Edit the optional overview title and description."""

    def __init__(self, draft: DonationSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "donation.setup.content_title")[:45]
        )
        self.draft = draft
        self.setup_view = DonationSetupView(draft)
        self.title_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.overview_title")[:45],
            default=draft.title,
            required=False,
            max_length=256,
        )
        self.description_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.overview_text")[:45],
            default=draft.description,
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=4000,
        )
        self.add_item(self.title_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.draft.title = self.title_input.value.strip()
        self.draft.description = self.description_input.value.strip()
        await self.setup_view.refresh(interaction)


class DonationValuesModal(discord.ui.Modal):
    """Edit the donation unit and optional fixed amount values."""

    def __init__(self, draft: DonationSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "donation.setup.values_title")[:45]
        )
        self.draft = draft
        self.setup_view = DonationSetupView(draft)
        self.unit_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.unit")[:45],
            placeholder=t(draft.module.guild, "donation.setup.unit_example")[:100],
            default=draft.unit,
            max_length=45,
        )
        self.choices_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.choices")[:45],
            placeholder=t(draft.module.guild, "donation.setup.choices_example")[:100],
            default="; ".join(draft.choices),
            required=False,
            max_length=1000,
        )
        self.add_item(self.unit_input)
        self.add_item(self.choices_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        unit = self.unit_input.value.strip()
        if not unit:
            await interaction.response.send_message(
                t(interaction, "donation.error.unit_required"), ephemeral=True
            )
            return
        try:
            choices = _parse_donation_choices(self.choices_input.value)
        except ValueError:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_setup_values"),
                ephemeral=True,
            )
            return
        self.draft.unit = unit
        self.draft.choices = choices
        await self.setup_view.refresh(interaction)


def _parse_donation_choices(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    raw_choices = parse_choices(raw)
    choices = tuple(format(parse_amount(choice), "f") for choice in raw_choices)
    if len(set(choices)) != len(choices):
        raise ValueError("Donation amount choices must be unique.")
    return choices


class DonationRecentLimitModal(discord.ui.Modal):
    """Set how many current-cycle donations appear in the overview."""

    def __init__(self, draft: DonationSetupDraft) -> None:
        super().__init__(
            title=t(draft.module.guild, "donation.setup.recent_title")[:45]
        )
        self.draft = draft
        self.setup_view = DonationSetupView(draft)
        self.limit_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.recent_limit")[:45],
            default=str(draft.recent_limit),
            max_length=2,
        )
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            limit = int(self.limit_input.value)
        except ValueError:
            limit = 0
        if not 1 <= limit <= 20:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_recent_limit"),
                ephemeral=True,
            )
            return
        self.draft.recent_limit = limit
        await self.setup_view.refresh(interaction)


class DonationRushStartModal(discord.ui.Modal):
    """Set the start date and local time of the nine-day Rush period."""

    def __init__(self, draft: DonationSetupDraft) -> None:
        super().__init__(title=t(draft.module.guild, "donation.setup.start_title")[:45])
        self.draft = draft
        self.setup_view = DonationSetupView(draft)
        local_start = (
            draft.rush_start_at.astimezone(ZoneInfo("Europe/Berlin"))
            if draft.rush_start_at is not None
            else datetime.now(ZoneInfo("Europe/Berlin"))
        )
        self.date_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.start_date")[:45],
            placeholder="YYYY-MM-DD",
            default=local_start.strftime("%Y-%m-%d"),
            max_length=10,
        )
        self.time_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(draft.module.guild, "donation.setup.start_time")[:45],
            placeholder="HH:MM",
            default=local_start.strftime("%H:%M"),
            max_length=5,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.draft.rush_start_at = parse_rush_start(
                self.date_input.value, self.time_input.value
            )
        except ValueError:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_rush_start"),
                ephemeral=True,
            )
            return
        await self.setup_view.refresh(interaction)
