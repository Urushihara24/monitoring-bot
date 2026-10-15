from __future__ import annotations

from types import SimpleNamespace

import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from src.telegram_router import TelegramRouter


class FakeApplication:
    def __init__(self) -> None:
        self.handlers = []
        self.error_handlers = []

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    def add_error_handler(self, callback) -> None:
        self.error_handlers.append(callback)


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    async def cmd_start(self, update, context):
        self.calls.append(('start', update, context))

    async def cmd_status(self, update, context):
        self.calls.append(('status', update, context))

    async def cmd_diag(self, update, context):
        self.calls.append(('diag', update, context))

    async def cmd_smoke(self, update, context):
        self.calls.append(('smoke', update, context))

    async def handle_callback_query(self, update, context):
        self.calls.append(('callback', update, context))

    async def handle_message(self, update, context):
        self.calls.append(('message', update, context))

    async def handle_app_error(self, update, context):
        self.calls.append(('error', update, context))


def test_router_registers_existing_update_surface():
    bot = FakeBot()
    router = TelegramRouter(bot)
    app = FakeApplication()

    router.register(app)

    assert len(app.handlers) == 6
    assert [type(handler) for handler in app.handlers] == [
        CommandHandler,
        CommandHandler,
        CommandHandler,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
    ]
    assert [set(handler.commands) for handler in app.handlers[:4]] == [
        {'start'},
        {'status'},
        {'diag'},
        {'smoke'},
    ]
    assert [handler.callback.__self__ for handler in app.handlers] == [
        router,
        router,
        router,
        router,
        router,
        router,
    ]
    assert len(app.error_handlers) == 1
    assert app.error_handlers[0].__self__ is router


@pytest.mark.asyncio
async def test_router_delegates_commands_updates_and_errors_without_translation():
    bot = FakeBot()
    router = TelegramRouter(bot)
    update = SimpleNamespace(value='update')
    context = SimpleNamespace(value='context')

    await router.cmd_start(update, context)
    await router.cmd_status(update, context)
    await router.cmd_diag(update, context)
    await router.cmd_smoke(update, context)
    await router.callback_query(update, context)
    await router.message(update, context)
    await router.error(update, context)

    assert bot.calls == [
        ('start', update, context),
        ('status', update, context),
        ('diag', update, context),
        ('smoke', update, context),
        ('callback', update, context),
        ('message', update, context),
        ('error', update, context),
    ]
