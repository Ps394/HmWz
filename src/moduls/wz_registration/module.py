from __future__ import annotations
import asyncio
import logging
import time
from types import SimpleNamespace

import discord
import hmEvents
import hmEmojis
import hmUtils

from configuration import config
from i18n import t
from hmModels.botembed import BotEmbed

from ..basic_module import BasicModule
from ..registry import register
from . import models
from . import recordsets

_logger = logging.getLogger(__name__)


@register
class WzRegistrationModule(BasicModule):
    """Guild-spezifisches WZ-Registrierungsmodul."""

    def __init__(self, guild: discord.Guild, client):
        """Initialisiert Recordsets und Laufzeitzustand fuer die Guild."""
        super().__init__(guild, client)
        self.configuration = recordsets.Configuration(self.database)
        self.roles = recordsets.WzRoles(self.database)
        self.registration = recordsets.WzRegistration(self.database)
        self.registrations = recordsets.WzRegistrations(self.database)
        self.list = recordsets.WzList(self.database)
        self._schema_ready = False
        self._compose_lock = asyncio.Lock()
        self._last_compose_at = 0.0
        self._compose_min_interval_seconds = 1.5

    @property
    def _client_color(self) -> discord.Color:
        """Ermittelt die aktuelle Bot-Farbe in der Guild fuer Embeds."""
        member = self.guild.get_member(self.client.user.id) if self.client and self.client.user else None
        if member and member.roles:
            return max(member.roles, key=lambda r: r.position).color
        return discord.Color.blurple()

    @property
    def _client_avatar(self) -> discord.Asset | None:
        """Liefert ein passendes Avatar fuer Embed-Footer."""
        if self.guild.icon:
            return self.guild.icon
        if self.client and self.client.user and self.client.user.avatar:
            return self.client.user.avatar
        return None

    def _runtime_t(self, key: str, **kwargs) -> str:
        """Uebersetzt Laufzeittexte fuer guild-getriebene Kontexte ohne Interaction."""
        locale = str(getattr(self.guild, "preferred_locale", "") or "de")
        pseudo_interaction = SimpleNamespace(locale=locale, guild_locale=locale)
        return t(pseudo_interaction, key, **kwargs)

    async def _load_configuration_model(self) -> models.Configuration:
        """Liest DB-Daten und mappt sie in das interne Domain-Model."""
        record = await self.registration.get(guild=self.guild)
        role_records = await self.roles.get(guild=self.guild)
        registration_roles = tuple(
            models.RegistrationRole(role_id=role.role, score=role.score, permanent=role.permanent)
            for role in (role_records or [])
            if role.role is not None
        )

        if record is None:
            return models.Configuration(
                guild_id=self.guild.id,
                channel_id=None,
                message_id=None,
                title=None,
                description=None,
                registration_roles=registration_roles,
            )

        return models.Configuration(
            guild_id=self.guild.id,
            channel_id=record.channel,
            message_id=record.message,
            title=record.title,
            description=record.description,
            registration_roles=registration_roles,
        )

    async def _load_registration_model(self, configuration: models.Configuration) -> models.Registration:
        """Liest Registrierungen aus der DB und mappt sie in Domain-Objekte."""
        role_map = {role.role_id: role for role in configuration.registration_roles}
        registration_records = await self.registrations.get(guild=self.guild)
        out: list[models.RegistrationMember] = []

        for record in registration_records or []:
            if record.member is None or record.role is None:
                continue
            role_model = role_map.get(record.role)
            if role_model is None:
                role_model = models.RegistrationRole(role_id=record.role, score=0, permanent=False)
            out.append(
                models.RegistrationMember(
                    member_id=record.member,
                    role=role_model,
                    timestamp=record.timestamp,
                )
            )

        return models.Registration(guild=self.guild, registrations=out)

    async def _handle_registration(self, interaction: discord.Interaction, role: discord.Role) -> None:
        """Verarbeitet An- und Abmeldung eines Users fuer eine Rolle.

        Das Verhalten ist toggelnd:
        - gleiche Rolle erneut: Abmeldung
        - andere Rolle: Wechsel
        - keine bestehende Registrierung: Anmeldung
        """
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        await interaction.response.defer(ephemeral=True)

        records = await self.registrations.get(guild=guild, member=member.id)
        current = records[0] if records else None

        if current and current.role == role.id:
            removed = await self.registrations.remove(guild=guild, member=member.id)
            if not removed:
                await interaction.followup.send(
                    t(interaction, "wz.overview.registration.error_registration"),
                    ephemeral=True,
                )
                return
            await member.remove_roles(role, reason="WZ deregistration")
            await interaction.followup.send(
                t(interaction, "wz.overview.registration.remove_registration", role_name=role.name),
                ephemeral=True,
            )
            await self.compose_registration_overview(force=True)
            return

        is_update = current is not None and current.role != role.id
        if current and current.role != role.id:
            if current.role is not None:
                old_role = await hmUtils.fetch_role(guild, current.role)
                if old_role is not None:
                    await member.remove_roles(old_role, reason="WZ registration update")

        added = await self.registrations.add(guild=guild, member=member.id, role=role.id)
        if not added:
            await interaction.followup.send(
                t(interaction, "wz.overview.registration.error_registration"),
                ephemeral=True,
            )
            return
        await member.add_roles(role, reason="WZ registration")
        key = "wz.overview.registration.update_registration" if is_update else "wz.overview.registration.new_registration"
        await interaction.followup.send(
            t(interaction, key, role_name=role.name),
            ephemeral=True,
        )
        await self.compose_registration_overview(force=True)

    def _build_view(self, roles: tuple[models.RegistrationRole, ...]) -> discord.ui.View:
        """Erstellt die Button-View fuer alle konfigurierten Rollen."""
        view = discord.ui.View(timeout=None)
        row = 0
        for role_data in roles:
            role = self.guild.get_role(role_data.role_id)
            if role is None:
                continue

            async def callback(interaction: discord.Interaction, selected_role: discord.Role = role):
                await self._handle_registration(interaction, selected_role)

            button = discord.ui.Button(
                label=role.name,
                style=discord.ButtonStyle.primary,
                row=min(row, 4),
            )
            button.callback = callback
            view.add_item(button)
            row += 1
        return view

    async def _load_list_messages(self, channel: discord.TextChannel) -> list[discord.Message]:
        """Laedt bestehende Listen-Nachrichten aus der DB und bereinigt stale Eintraege."""
        records = await self.list.get(guild=self.guild)
        if not records:
            return []

        messages: list[discord.Message] = []
        stale_ids: list[int] = []
        for record in records:
            message = await hmUtils.fetch_message(channel, record.message)
            if message is None:
                stale_ids.append(record.message)
                continue
            messages.append(message)

        for stale_id in stale_ids:
            await self.list.remove(guild=self.guild, message=stale_id)

        return messages

    async def _create_list_embeds(
        self,
        registrations: models.Registration,
    ) -> list[discord.Embed]:
        """Erzeugt Embeds fuer die Anmeldeliste aus den Registrierungsdaten."""
        if not registrations.registrations:
            return []
        entries: list[tuple[str, bool, str]] = []

        for reg in registrations.registrations:
            role_obj = await hmUtils.fetch_role(self.guild, reg.role.role_id)
            member_obj = await hmUtils.fetch_member(self.guild, reg.member_id)

            if role_obj is None or member_obj is None:
                continue

            entries.append((role_obj.name, reg.role.permanent, member_obj.display_name))

        if not entries:
            return []

        entries.sort(key=lambda e: (not e[1], e[0].lower(), e[2].lower()))

        total = len(entries)
        permanent = len([entry for entry in entries if entry[1]])
        non_permanent = total - permanent

        rows: list[str] = []
        last_group = ""
        for index, (role_name, is_permanent, display_name) in enumerate(entries, start=1):
            marker = hmEmojis.PERMA_REGISTRATION if is_permanent else hmEmojis.NORMAL_REGISTRATION
            group = f"{role_name} {marker}"
            if group != last_group:
                rows.append(f"**{group}**")
                last_group = group
            rows.append(f"{index}. {display_name}")

        embeds: list[discord.Embed] = []
        chunk: list[str] = []
        chunk_chars = 0
        chunk_limit = 3800
        page = 1

        def make_embed(page_no: int, content: str) -> discord.Embed:
            return BotEmbed(
                title=self._runtime_t(
                    "wz.overview.list.title",
                    page=page_no,
                    total=total,
                    perma_emoji=hmEmojis.PERMA_REGISTRATION,
                    permanent_count=permanent,
                    normal_emoji=hmEmojis.NORMAL_REGISTRATION,
                    non_permanent_count=non_permanent,
                ),
                description=content,
                color=self._client_color,
                client_avatar=self._client_avatar,
            )

        for row in rows:
            line = row + "\n"
            if chunk and (chunk_chars + len(line)) > chunk_limit:
                embeds.append(make_embed(page, "".join(chunk)))
                page += 1
                chunk = []
                chunk_chars = 0
            chunk.append(line)
            chunk_chars += len(line)

        if chunk:
            embeds.append(make_embed(page, "".join(chunk)))

        return embeds

    async def _sync_list_messages(
        self,
        channel: discord.TextChannel,
        embeds: list[discord.Embed],
    ) -> bool:
        """Synchronisiert Listen-Embeds mit bestehenden Nachrichten in Discord und DB."""
        existing_messages = await self._load_list_messages(channel)

        for index in range(max(len(existing_messages), len(embeds))):
            if index < len(embeds) and index < len(existing_messages):
                message = existing_messages[index]
                embed = embeds[index]
                await message.edit(embed=embed)
                await self.list.add(
                    guild=self.guild,
                    channel=channel.id,
                    message=message.id,
                    title=embed.title or "",
                    text=embed.description or "",
                )
                continue

            if index < len(embeds):
                embed = embeds[index]
                message = await channel.send(embed=embed)
                await self.list.add(
                    guild=self.guild,
                    channel=channel.id,
                    message=message.id,
                    title=embed.title or "",
                    text=embed.description or "",
                )
                continue

            message = existing_messages[index]
            try:
                await message.delete()
            finally:
                await self.list.remove(guild=self.guild, message=message.id)

        return True

    async def _compose_registration_overview_inner(self) -> bool:
        """Baut Registrierungsnachricht und Anmeldeliste auf und synchronisiert beides."""
        configuration = await self._load_configuration_model()

        if not configuration.has_channel:
            _logger.debug(f"{self.guild.name} ({self.guild.id}) - No registration channel configured.")
            return False
        if not configuration.has_registration_roles:
            _logger.debug(f"{self.guild.name} ({self.guild.id}) - No registration roles configured.")
            return False

        channel_id = configuration.channel_id
        if channel_id is None:
            return False

        channel = await hmUtils.fetch_channel(self.guild, channel_id)
        if channel is None:
            _logger.warning(
                f"{self.guild.name} ({self.guild.id}) - Registration channel not found: {channel_id}"
            )
            return False

        default_title = self._runtime_t("wz.overview.default_title")
        default_description = self._runtime_t("wz.overview.default_description")
        if isinstance(config, dict):
            registration_cfg = config.get("wz_registration")
            if isinstance(registration_cfg, dict):
                default_title = str(registration_cfg.get("default_title", default_title))
                default_description = str(registration_cfg.get("default_description", default_description))

        title = configuration.title or default_title
        description = configuration.description or default_description
        embed = BotEmbed(
            title=title,
            description=description,
            color=self._client_color,
            client_avatar=self._client_avatar,
        )
        view = self._build_view(configuration.registration_roles)

        message: discord.Message | None = None
        if configuration.has_message and configuration.message_id is not None:
            message = await hmUtils.fetch_message(channel, configuration.message_id)

        registration_model = await self._load_registration_model(configuration)

        if message is None:
            message = await channel.send(embed=embed, view=view)
            await self.registration.upsert(
                guild=self.guild,
                channel_id=channel.id,
                message_id=message.id,
                title=title,
                description=description,
            )
            list_embeds = await self._create_list_embeds(registration_model)
            await self._sync_list_messages(channel, list_embeds)
            _logger.info(f"{self.guild.name} ({self.guild.id}) - Created registration overview message {message.id} in {channel.name}({channel.id}).")
            return True

        await message.edit(embed=embed, view=view)
        await self.registration.upsert(
            guild=self.guild,
            channel_id=channel.id,
            message_id=message.id,
            title=title,
            description=description,
        )
        list_embeds = await self._create_list_embeds(registration_model)
        await self._sync_list_messages(channel, list_embeds)
        _logger.info(f"{self.guild.name} ({self.guild.id}) - Updated registration overview message {message.id} in {channel.name}({channel.id}).")
        return True

    async def compose_registration_overview(self, force: bool = False) -> bool:
        """Komponiert die Uebersicht mit Debounce und Lock.

        Parameter:
        - force: Ueberspringt Debounce, z. B. nach direkter User-Interaktion.
        """
        now = time.monotonic()
        if not force and (now - self._last_compose_at) < self._compose_min_interval_seconds:
            _logger.debug(
                f"{self.guild.name} ({self.guild.id}) - Debounced registration overview compose request."
            )
            return True

        async with self._compose_lock:
            now = time.monotonic()
            if not force and (now - self._last_compose_at) < self._compose_min_interval_seconds:
                _logger.debug(
                    f"{self.guild.name} ({self.guild.id}) - Debounced registration overview compose request (locked)."
                )
                return True

            result = await self._compose_registration_overview_inner()
            if result:
                self._last_compose_at = time.monotonic()
            return result

    async def _ensure_schema(self) -> bool:
        """Stellt sicher, dass alle benoetigten Tabellen existieren."""
        if self._schema_ready:
            return True
        try:
            # Keep schema creation local to this module for scalability.
            await self.database.execute(self.configuration.table)
            await self.database.execute(self.roles.table)
            await self.database.execute(self.registration.table)
            await self.database.execute(self.registrations.table)
            await self.database.execute(self.list.table)
            self._schema_ready = True
            _logger.info(f"{self.guild.name} ({self.guild.id}) - WZ module schema ready.")
            return True
        except Exception as e:
            _logger.exception(f"{self.guild.name} ({self.guild.id}) - Failed to ensure WZ schema: {e}")
            return False

    async def sync(self, startup: bool = False) -> bool:
        """Synchronisiert den technischen Modulzustand (Schema)."""
        if not await self._ensure_schema():
            return False
        if startup:
            _logger.debug(f"{self.guild.name} ({self.guild.id}) - WZ module startup sync done.")
        return True

    async def ensure(self) -> bool:
        """Stellt sicher, dass die Registrierungsuebersicht sichtbar und aktuell ist."""
        try:
            return await self.compose_registration_overview()
        except Exception as e:
            _logger.exception(f"{self.guild.name} ({self.guild.id}) - Failed to compose registration overview: {e}")
            return False

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Initialisiert Modulzustand bei Guild-Join."""
        if guild.id != self.guild.id:
            return False
        return await self.sync(startup=True)

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Entfernt guild-bezogene WZ-Daten beim Verlassen der Guild."""
        if guild.id != self.guild.id:
            return False
        # Best effort cleanup for this guild.
        await self.configuration.remove(guild=guild)
        await self.registration.remove(guild=guild)
        await self.roles.remove(guild=guild)
        await self.list.remove(guild=guild)
        await self.registrations.remove(guild=guild)
        return True

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return channel.guild.id == self.guild.id

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return before.guild.id == self.guild.id

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return channel.guild.id == self.guild.id

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return before.guild.id == self.guild.id

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Bereinigt geloeschte Rollen aus Rollen- und Registrierungsrecordset."""
        if role.guild.id != self.guild.id:
            return False
        await self.roles.remove(guild=self.guild, role=role.id)
        await self.registrations.remove(guild=self.guild, role=role.id)
        return True

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> bool:
        """Synchronisiert Registrierungen bei manuellen Rollen-Aenderungen."""
        if before.guild.id != self.guild.id:
            return False

        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}
        added_role_ids = after_role_ids - before_role_ids
        removed_role_ids = before_role_ids - after_role_ids

        if not added_role_ids and not removed_role_ids:
            return True

        configured_roles = await self.roles.get(guild=self.guild)
        if not configured_roles:
            return True

        registration_role_ids = {role.role for role in configured_roles}
        added_registration_roles = added_role_ids & registration_role_ids
        removed_registration_roles = removed_role_ids & registration_role_ids

        if not added_registration_roles and not removed_registration_roles:
            return True

        registrations = await self.registrations.get(guild=self.guild, member=after.id)
        current_registration = registrations[0] if registrations else None

        changed = False

        if current_registration and current_registration.role is not None:
            current_role_id = current_registration.role

            if current_role_id in removed_registration_roles:
                changed = await self.registrations.remove(guild=self.guild, member=after.id)
            elif (
                added_registration_roles
                and current_role_id not in after_role_ids
            ):
                target_role = min(added_registration_roles)
                changed = await self.registrations.add(
                    guild=self.guild,
                    member=after.id,
                    role=target_role,
                )
        elif added_registration_roles:
            target_role = min(added_registration_roles)
            changed = await self.registrations.add(
                guild=self.guild,
                member=after.id,
                role=target_role,
            )

        if changed:
            await self.compose_registration_overview(force=True)

        return True

    async def on_raw_member_remove(self, payload: hmEvents.RawMemberRemoveEvent) -> bool:
        """Entfernt Registrierungen fuer verlassende Mitglieder."""
        if payload.guild_id != self.guild.id:
            return False
        await self.registrations.remove(guild=self.guild, member=payload.user.id)
        return True

    async def on_raw_message_delete(self, payload: hmEvents.RawMessageDeleteEvent) -> bool:
        """Bereinigt Referenzen auf geloeschte Registrierungsnachrichten und stellt sie bei Bedarf wieder her."""
        if payload.guild_id != self.guild.id:
            return False
        if payload.message_id is not None:
            registration = await self.registration.get(guild=self.guild)
            if registration and registration.message == payload.message_id:
                await self.registration.upsert(guild=self.guild, message_id=None)
                await self.compose_registration_overview(force=True)
            await self.list.remove(guild=self.guild, message=payload.message_id)
        return True

    async def on_raw_bulk_message_delete(self, payload: hmEvents.RawBulkMessageDeleteEvent) -> bool:
        """Behandelt Massenloeschungen (z. B. via /purge) wie mehrere einzelne Nachrichtenloeschungen."""
        if payload.guild_id != self.guild.id:
            return False

        registration = await self.registration.get(guild=self.guild)
        needs_recompose = bool(registration and registration.message in payload.message_ids)
        if needs_recompose:
            await self.registration.upsert(guild=self.guild, message_id=None)

        for message_id in payload.message_ids:
            await self.list.remove(guild=self.guild, message=message_id)

        if needs_recompose:
            await self.compose_registration_overview(force=True)
        return True
