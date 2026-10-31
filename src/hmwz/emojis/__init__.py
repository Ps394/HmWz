"""Application emoji uploads and shared Unicode fallbacks."""

from . import emojis
from .uploader import EmojiUploader, UploadResult

__all__ = ["EmojiUploader", "UploadResult", "emojis"]
