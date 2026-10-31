from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_response as _send_temporary_response

from ....models import (
    DEFAULT_DONATION_CHOICES,
    DonationChannel,
    DonationKind,
    DonationType,
)
from ....type.credit.setup import DonationValuesModal, configured_type as credit_type
from ....type.rush.setup import (
    DonationRushStartModal,
    DonationRushTargetModal,
    configured_type as rush_type,
)
from ....type.rush.pricing import RUSH_DURATIONS_HOURS
from ....type.rush.pricing import validate_rush_target
from ....type.rush.validation import COMMON_DONATION_TIMEZONES, donation_timezone
from .configuration_message import donation_setup_panel
from .draft import DonationSetupDraft

if TYPE_CHECKING:
    from ....module import DonationModule

DonationSetupAction = Literal[
    "content",
    "values",
    "ranking",
    "start",
    "target",
    "visibility",
    "donations",
    "export",
    "save",
]


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
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_type")
            )
            return
        draft = self.create_draft(kind, interaction)
        await interaction.response.edit_message(
            content=None,
            embed=donation_setup_panel(draft, interaction),
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
            rush_start_at = datetime.now(UTC).replace(second=0, microsecond=0)
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
                configuration.show_ranking if configuration is not None else False
            ),
            rush_start_at=rush_start_at,
            timezone_name=(
                configuration.timezone_name if configuration is not None else "UTC"
            ),
            show_donations=(
                configuration.show_donations if configuration is not None else True
            ),
            donations_enabled=(
                configuration.donations_enabled if configuration is not None else True
            ),
            export_channel_id=(
                configuration.export_channel_id if configuration is not None else None
            ),
            target_at=(
                configuration.target_at
                if configuration is not None and kind == "time_reduction"
                else None
            ),
        )


class DonationSetupOwnerView(discord.ui.View):
    """Restrict an ephemeral setup step to its initiating administrator."""

    def __init__(self, owner_id: int, *, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await _send_temporary_response(
            interaction, t(interaction, "donation.setup.owner_only")
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
        "ranking": "donation.setup.toggle_ranking",
        "start": "donation.setup.edit_start",
        "target": "donation.setup.edit_target",
        "visibility": "donation.setup.toggle_visibility",
        "donations": "donation.setup.toggle_donations",
        "export": "donation.setup.export_channel",
        "save": "donation.setup.save",
    }

    def __init__(
        self, setup_view: DonationSetupView, action: DonationSetupAction, row: int
    ) -> None:
        super().__init__(
            label=t(
                setup_view.draft.module.guild,
                (
                    "donation.setup.stop_donations"
                    if action == "donations" and setup_view.draft.donations_enabled
                    else "donation.setup.start_donations"
                    if action == "donations"
                    else "donation.setup.hide_donations"
                    if action == "visibility" and setup_view.draft.show_donations
                    else "donation.setup.show_donations"
                    if action == "visibility"
                    else "donation.setup.hide_ranking"
                    if action == "ranking" and setup_view.draft.show_ranking
                    else "donation.setup.show_ranking"
                    if action == "ranking"
                    else self.LABELS[action]
                ),
            ),
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


class DonationExportChannelSelect(discord.ui.ChannelSelect):
    """Select a text channel where completed donation cycles are exported."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder=t(
                setup_view.draft.module.guild,
                "donation.setup.export_channel_select",
            ),
            min_values=1,
            max_values=1,
        )
        self.setup_view = setup_view

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        guild = self.setup_view.draft.module.guild
        channel = guild.get_channel(selected.id)
        if not isinstance(channel, discord.TextChannel):
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.export_channel_invalid")
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.export_channel_save")
            )
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.attach_files:
            await _send_temporary_response(
                interaction,
                t(interaction, "donation.error.export_channel_permissions"),
            )
            return
        self.setup_view.draft.export_channel_id = channel.id
        await interaction.response.edit_message(
            content=None,
            embed=donation_setup_panel(self.setup_view.draft, interaction),
            view=self.setup_view,
        )


class DonationExportChannelView(DonationSetupOwnerView):
    """Choose or disable the channel used for cycle JSON exports."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        super().__init__(setup_view.draft.owner_id, timeout=180)
        self.setup_view = setup_view
        self.add_item(DonationExportChannelSelect(setup_view))
        labels = {
            "donation:setup:export-disable": "donation.setup.export_disable",
            "donation:setup:export-back": "donation.setup.export_back",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in labels:
                item.label = t(setup_view.draft.module.guild, labels[item.custom_id])

    @discord.ui.button(
        label="Disable export",
        style=discord.ButtonStyle.danger,
        custom_id="donation:setup:export-disable",
        row=1,
    )
    async def disable_export(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.setup_view.draft.export_channel_id = None
        await interaction.response.edit_message(
            content=None,
            embed=donation_setup_panel(self.setup_view.draft, interaction),
            view=self.setup_view,
        )

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id="donation:setup:export-back",
        row=1,
    )
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=donation_setup_panel(self.setup_view.draft, interaction),
            view=self.setup_view,
        )


class DonationSetupView(DonationSetupOwnerView):
    """Menu for editing each section of a donation setup."""

    def __init__(self, draft: DonationSetupDraft) -> None:
        super().__init__(draft.owner_id)
        self.draft = draft
        self._build_controls()

    def _build_controls(self) -> None:
        self.clear_items()
        draft = self.draft
        row = 0
        if draft.kind == "time_reduction":
            self.add_item(DonationTimezoneSelect(self))
            row = 1
        self.add_item(DonationSetupButton(self, "content", row=row))
        if draft.kind == "simple":
            self.add_item(DonationSetupButton(self, "values", row=0))
        if draft.kind == "time_reduction":
            self.add_item(DonationSetupButton(self, "start", row=row))
            self.add_item(DonationSetupButton(self, "target", row=row))
        self.add_item(DonationSetupButton(self, "ranking", row=row + 1))
        self.add_item(DonationSetupButton(self, "visibility", row=row + 1))
        self.add_item(DonationSetupButton(self, "donations", row=row + 1))
        self.add_item(DonationSetupButton(self, "export", row=row + 2))
        self.add_item(DonationSetupButton(self, "save", row=row + 2))

    async def handle_action(
        self, interaction: discord.Interaction, action: DonationSetupAction
    ) -> None:
        match action:
            case "content":
                await interaction.response.send_modal(DonationContentModal(self.draft))
            case "values":
                await interaction.response.send_modal(DonationValuesModal(self))
            case "ranking":
                self.draft.show_ranking = not self.draft.show_ranking
                await self.refresh(interaction)
            case "visibility":
                self.draft.show_donations = not self.draft.show_donations
                await self.refresh(interaction)
            case "donations":
                self.draft.donations_enabled = not self.draft.donations_enabled
                await self.refresh(interaction)
            case "start":
                await interaction.response.send_modal(DonationRushStartModal(self))
            case "target":
                await interaction.response.send_modal(DonationRushTargetModal(self))
            case "export":
                await interaction.response.edit_message(
                    content=t(interaction, "donation.setup.export_channel_prompt"),
                    embed=None,
                    view=DonationExportChannelView(self),
                )
            case "save":
                await self.save(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._build_controls()
        await interaction.response.edit_message(
            content=None,
            embed=donation_setup_panel(self.draft, interaction),
            view=self,
        )

    async def save(self, interaction: discord.Interaction) -> None:
        if self.draft.kind == "simple" and not self.draft.unit:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.unit_required")
            )
            return
        if not 1 <= self.draft.recent_limit <= 20:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_recent_limit")
            )
            return
        if self.draft.kind == "time_reduction" and self.draft.rush_start_at is None:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_setup_values")
            )
            return
        await interaction.response.defer(ephemeral=True)
        if not await _save_setup(self.draft, interaction):
            return
        self.stop()
        await interaction.delete_original_response()
        confirmation = await interaction.followup.send(
            t(interaction, "donation.setup.complete"), ephemeral=True, wait=True
        )
        await confirmation.delete(delay=5)


async def _save_setup(
    draft: DonationSetupDraft, interaction: discord.Interaction
) -> bool:
    if draft.kind == "time_reduction" and draft.target_at is not None:
        try:
            if draft.rush_start_at is None:
                raise ValueError("A target requires a Rush start.")
            draft.target_at = validate_rush_target(
                draft.rush_start_at, draft.target_at, draft.accelerated_hours
            )
        except ValueError:
            await _send_setup_followup_error(
                interaction, "donation.error.invalid_target"
            )
            return False
    donation_type = credit_type(draft) if draft.kind == "simple" else rush_type(draft)
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
        timezone_name=draft.timezone_name,
        show_donations=draft.show_donations,
        donations_enabled=draft.donations_enabled,
        export_channel_id=draft.export_channel_id,
        target_at=draft.target_at if draft.kind == "time_reduction" else None,
    )
    if not saved:
        await _send_setup_followup_error(interaction, "donation.error.setup_save")
        return False
    return True


class DonationTimezoneSelect(discord.ui.Select):
    """Choose the setup's input timezone without shifting saved absolute instants."""

    def __init__(self, setup_view: DonationSetupView) -> None:
        self.setup_view = setup_view
        draft = setup_view.draft
        options = [
            discord.SelectOption(
                label=t(draft.module.guild, key),
                value=name,
                description=name,
                default=name == draft.timezone_name,
            )
            for name, key in COMMON_DONATION_TIMEZONES
        ]
        if draft.timezone_name not in {option.value for option in options}:
            options.append(
                discord.SelectOption(
                    label=draft.timezone_name,
                    value=draft.timezone_name,
                    default=True,
                )
            )
        super().__init__(
            placeholder=t(draft.module.guild, "donation.setup.timezone"),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        timezone_name = self.values[0]
        try:
            donation_timezone(timezone_name)
        except ValueError:
            await _send_temporary_response(
                interaction, t(interaction, "donation.error.invalid_timezone")
            )
            return
        self.setup_view.draft.timezone_name = timezone_name
        await self.setup_view.refresh(interaction)


async def _send_setup_followup_error(
    interaction: discord.Interaction, translation_key: str
) -> None:
    message = await interaction.followup.send(
        t(interaction, translation_key), ephemeral=True, wait=True
    )
    await message.delete(delay=5)


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
