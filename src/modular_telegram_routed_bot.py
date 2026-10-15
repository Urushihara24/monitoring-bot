"""Telegram runtime facade with extracted command/update routing."""

from __future__ import annotations

from .modular_telegram_settings_bot import ModularTelegramSettingsBot
from .telegram_router import TelegramRouter


class ModularTelegramRoutedBot(ModularTelegramSettingsBot):
    """Active Telegram runtime whose PTB handlers are owned by TelegramRouter."""

    def _setup_handlers(self):
        self._router = TelegramRouter(self)
        self._router.register(self.app)
