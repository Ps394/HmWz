from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from hmwz import sqlite_db
from hmwz.i18n import t
from hmwz.modules.module import Module
from hmwz.modules.protocols import MessageModuleProtocol, RoleModuleProtocol

from hmwz.utils.loaders import fetch_message, fetch_member, fetch_role

from hmwz.ui.messages import send_temporary_followup

_logger = logging.getLogger(__name__)

class RegistrationModule(Module, MessageModuleProtocol, RoleModuleProtocol):
    """Module for handling user registration."""

    
