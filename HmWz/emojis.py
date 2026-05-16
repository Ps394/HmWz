"""
Das Modul "emojis" enthält die Definition der Emojis, die im Bot verwendet werden. Es verwendet eine Enum-Klasse, um die verschiedenen Emojis zu definieren, die für verschiedene Aktionen und Statusanzeigen im Bot verwendet werden können. Die Emojis sind als Unicode-Zeichen definiert und können in den Nachrichten des Bots verwendet werden, um visuelle Hinweise zu geben.
"""
from enum import Enum


class Emojis(Enum):
     """
     Vollstaendige, uebliche Default-Emoji-Sammlung fuer Bot-Features.
     Die bestehenden Schluessel bleiben kompatibel und werden um gaengige
     Standardwerte fuer Status, Aktionen, Navigation und Kategorien ergaenzt.
     """

     # Core status
     SUCCESS = "✅"
     WARNING = "⚠️"
     ERROR = "❌"
     INFO = "ℹ️"
     QUESTION = "❓"
     UNKNOWN = "❔"

     # Common action results
     CREATED = "🆕"
     UPDATED = "✏️"
     DELETED = "🗑️"
     SAVED = "💾"
     RESET = "♻️"

     # Registration (existing compatibility)
     REGISTER = "➕"
     REREGISTER = "🔄"
     UNREGISTER = "➖"
     PERMA_REGISTRATION = "🔒"
     NORMAL_REGISTRATION = "🔓"

     # Generic actions
     ADD = "➕"
     REMOVE = "➖"
     EDIT = "✏️"
     CONFIGURE = "⚙️"
     SEARCH = "🔎"
     FILTER = "🧰"
     EXPORT = "📤"
     IMPORT = "📥"
     REFRESH = "🔄"
     RETRY = "🔁"

     # Approvals / moderation
     APPROVE = "👍"
     REJECT = "👎"
     BAN = "🔨"
     KICK = "🥾"
     MUTE = "🔇"
     UNMUTE = "🔊"

     # Access / permissions
     LOCKED = "🔒"
     UNLOCKED = "🔓"
     ADMIN = "🛡️"
     MODERATOR = "🧑‍⚖️"
     USER = "👤"
     BOT = "🤖"

     # Navigation / UI hints
     NEXT = "➡️"
     PREVIOUS = "⬅️"
     UP = "⬆️"
     DOWN = "⬇️"
     HOME = "🏠"
     BACK = "↩️"
     FORWARD = "↪️"
     MENU = "📋"

     # Time / schedule
     CLOCK = "🕒"
     CALENDAR = "📅"
     DEADLINE = "⏰"
     DURATION = "⏱️"

     # Data / files
     FILE = "📄"
     FOLDER = "📁"
     CSV = "📑"
     DATABASE = "🗄️"
     STATS = "📊"
     CHART = "📈"

     # Communication
     MESSAGE = "💬"
     ANNOUNCEMENT = "📣"
     EMAIL = "📧"
     LINK = "🔗"

     # Process state
     PENDING = "🟡"
     RUNNING = "🔵"
     COMPLETED = "🟢"
     FAILED = "🔴"
     SKIPPED = "⏭️"
     PAUSED = "⏸️"
     STOPPED = "⏹️"

     # Misc common labels
     STAR = "⭐"
     FIRE = "🔥"
     CHECKBOX_ON = "☑️"
     CHECKBOX_OFF = "⬜"
     TAG = "🏷️"
     PIN = "📌"
     TROPHY = "🏆"

