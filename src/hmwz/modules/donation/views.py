from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t

from .repository import DonationType

if TYPE_CHECKING:
    from .module import DonationModule


class DonationRecordButton(discord.ui.Button):
    """Button that opens the donation type selector."""

    def __init__(self, module: DonationModule, channel_id: int) -> None:
        super().__init__(
            label=t(module.guild, "donation.ui.record_button"),
            style=discord.ButtonStyle.success,
            custom_id="donation:record",
        )
        self.module = module
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.module.show_donation_type_selection(interaction, self.channel_id)


class DonationOverviewView(discord.ui.View):
    """Persistent entry button attached to a channel's donation overview."""

    def __init__(self, module: DonationModule, channel_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(DonationRecordButton(module, channel_id))


class DonationTypeSelect(discord.ui.Select):
    """Select one configured donation type and display its entry modal."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_types: tuple[DonationType, ...],
    ) -> None:
        super().__init__(
            placeholder=t(module.guild, "donation.ui.select_placeholder"),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=donation_type.name,
                    value=donation_type.name,
                    description=(
                        f"{t(module.guild, 'donation.overview.second_field')}: "
                        f"{donation_type.extra_field[:100]}"
                        if donation_type.extra_field
                        else None
                    ),
                )
                for donation_type in donation_types
            ],
        )
        self.module = module
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        donation_type = await self.module.donations.get_type(
            guild=self.module.guild, name=self.values[0]
        )
        if donation_type is None:
            await interaction.response.send_message(
                t(interaction, "donation.error.invalid_type"), ephemeral=True
            )
            return
        await interaction.response.send_modal(
            DonationModal(self.module, self.channel_id, donation_type)
        )


class DonationTypeSelectView(discord.ui.View):
    """Ephemeral donation type selector shown before the donation modal."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_types: tuple[DonationType, ...],
    ) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.add_item(DonationTypeSelect(module, channel_id, donation_types[:25]))


class DonationModal(discord.ui.Modal):
    """Collect one donation's value and optional additional value."""

    def __init__(
        self,
        module: DonationModule,
        channel_id: int,
        donation_type: DonationType,
    ) -> None:
        super().__init__(
            title=t(module.guild, "donation.modal.title", name=donation_type.name)[:45]
        )
        self.module = module
        self.channel_id = channel_id
        self.donation_type = donation_type
        self.amount_input: discord.ui.TextInput = discord.ui.TextInput(
            label=t(
                module.guild,
                "donation.modal.amount",
                name=donation_type.name,
            )[:45],
            placeholder=t(module.guild, "donation.modal.amount_placeholder")[:100],
            max_length=100,
        )
        self.add_item(self.amount_input)
        self.extra_input: discord.ui.TextInput | None = None
        if donation_type.extra_field:
            self.extra_input = discord.ui.TextInput(
                label=donation_type.extra_field[:45],
                placeholder=t(module.guild, "donation.modal.extra_placeholder")[:100],
                max_length=100,
            )
            self.add_item(self.extra_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if interaction.guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                t(interaction, "donation.error.guild_only"), ephemeral=True
            )
            return

        amount = self.amount_input.value.strip()
        extra_value = (
            self.extra_input.value.strip() if self.extra_input is not None else None
        )
        if not amount or (self.extra_input is not None and not extra_value):
            await interaction.response.send_message(
                t(interaction, "donation.error.required_value"), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        saved = await self.module.donations.add_donation(
            guild=interaction.guild,
            channel_id=self.channel_id,
            member=member,
            donation_type=self.donation_type,
            amount=amount,
            extra_value=extra_value,
        )
        if not saved:
            await interaction.followup.send(
                t(interaction, "donation.error.save"), ephemeral=True
            )
            return

        updated = await self.module.compose_overview(self.channel_id)
        await interaction.followup.send(
            t(
                interaction,
                (
                    "donation.success.saved"
                    if updated
                    else "donation.success.saved_overview_failed"
                ),
            ),
            ephemeral=True,
        )
