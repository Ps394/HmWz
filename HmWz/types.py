from typing import Union, Optional, Tuple
from discord import Guild, Member, Role, TextChannel, Message

type Id = int
"""
Type-Alias für die id von Discord-Objekten 

:type id: int
"""
type Ids = Tuple[Id, ...]

type DiscordGuild = Guild
"""Type-Alias für eine Discord Guild-Objekt"""
type DiscordMember = Member
"""Type-Alias für ein Discord Member-Objekt"""
type DiscordTextChannel = TextChannel
"""Type-Alias für ein Discord TextChannel-Objekt"""
type DiscordMessage = Message
"""Type-Alias für ein Discord Message-Objekt"""