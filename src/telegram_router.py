"""Telegram command/update router for the modular runtime."""

from __future__ import annotations

from typing import Any

from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)


class TelegramRouter:
    """Own python-telegram-bot handler registration and thin delegation."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot

    def register(self, application: Any) -> None:
        application.add_handler(CommandHandler('start', self.cmd_start))
        application.add_handler(CommandHandler('status', self.cmd_status))
        application.add_handler(CommandHandler('diag', self.cmd_diag))
        application.add_handler(CommandHandler('smoke', self.cmd_smoke))
        application.add_handler(CallbackQueryHandler(self.callback_query))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message)
        )
        application.add_error_handler(self.error)

    async def cmd_start(self, update, context) -> None:
        await self.bot.cmd_start(update, context)

    async def cmd_status(self, update, context) -> None:
        await self.bot.cmd_status(update, context)

    async def cmd_diag(self, update, context) -> None:
        await self.bot.cmd_diag(update, context)

    async def cmd_smoke(self, update, context) -> None:
        await self.bot.cmd_smoke(update, context)

    async def callback_query(self, update, context) -> None:
        await self.bot.handle_callback_query(update, context)

    async def message(self, update, context) -> None:
        await self.bot.handle_message(update, context)

    async def error(self, update, context) -> None:
        await self.bot.handle_app_error(update, context)
