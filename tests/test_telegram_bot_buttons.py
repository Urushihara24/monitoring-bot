from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.telegram_bot import (
    BTN_ADD_URL,
    BTN_AUTO_OFF,
    BTN_AUTO_ON,
    BTN_BACK,
    BTN_DIAGNOSTICS,
    BTN_DOWN,
    BTN_HISTORY,
    BTN_INTERVAL,
    BTN_MAX,
    BTN_MIN,
    BTN_MODE,
    BTN_POSITION,
    BTN_PRICE,
    BTN_PROFILE,
    BTN_REMOVE_URL,
    BTN_SETTINGS,
    BTN_STATUS,
    BTN_STEP,
    BTN_UP,
    TelegramBot,
)


def make_bot() -> TelegramBot:
    bot = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    return bot


def make_update(text: str):
    message = SimpleNamespace(
        text=text,
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=100),
        message=message,
    )


def keyboard_texts(markup) -> list[str]:
    texts = []
    for row in markup.keyboard:
        for btn in row:
            texts.append(getattr(btn, 'text', str(btn)))
    return texts


def test_settings_keyboard_is_not_overloaded():
    bot = make_bot()
    texts = keyboard_texts(bot.get_settings_keyboard())
    assert '📤 Экспорт' not in texts
    assert '📥 Импорт' not in texts
    assert BTN_HISTORY in texts
    assert BTN_ADD_URL in texts
    assert BTN_REMOVE_URL in texts


@pytest.mark.asyncio
async def test_main_buttons_route_to_handlers():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}

    bot.send_status = AsyncMock()
    bot.handle_price_change = AsyncMock()
    bot.toggle_auto = AsyncMock()
    bot.send_settings = AsyncMock()
    bot.send_diagnostics = AsyncMock()

    status = make_update(BTN_STATUS)
    await bot.handle_message(status, None)
    bot.send_status.assert_awaited_once()

    up = make_update(BTN_UP)
    await bot.handle_message(up, None)
    bot.handle_price_change.assert_any_await(100, 0.01, up)

    down = make_update(BTN_DOWN)
    await bot.handle_message(down, None)
    bot.handle_price_change.assert_any_await(100, -0.01, down)

    auto = make_update(BTN_AUTO_ON)
    await bot.handle_message(auto, None)
    bot.toggle_auto.assert_awaited_once_with(auto)

    settings = make_update(BTN_SETTINGS)
    await bot.handle_message(settings, None)
    bot.send_settings.assert_awaited_once_with(100, settings)

    diagnostics = make_update(BTN_DIAGNOSTICS)
    await bot.handle_message(diagnostics, None)
    bot.send_diagnostics.assert_awaited_once_with(100, diagnostics)


@pytest.mark.asyncio
async def test_profile_button_opens_profile_keyboard():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    update = make_update(BTN_PROFILE)

    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert args[0] == 'Выбери профиль:'
    assert kwargs['reply_markup'] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('button', 'expected_action'),
    [
        (BTN_PRICE, 'DESIRED_PRICE'),
        (BTN_STEP, 'UNDERCUT_VALUE'),
        (BTN_MIN, 'MIN_PRICE'),
        (BTN_MAX, 'MAX_PRICE'),
        (BTN_INTERVAL, 'CHECK_INTERVAL'),
        (BTN_ADD_URL, 'ADD_URL'),
    ],
)
async def test_settings_buttons_set_pending_actions(button, expected_action):
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot._runtime = lambda _profile: SimpleNamespace(
        FAST_CHECK_INTERVAL_MIN=20,
        FAST_CHECK_INTERVAL_MAX=60,
    )
    update = make_update(button)

    await bot.handle_message(update, None)

    assert bot.pending_actions[100] == expected_action
    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_mode_and_position_buttons_call_toggles():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.toggle_mode = AsyncMock()
    bot.toggle_position_filter = AsyncMock()

    mode = make_update(BTN_MODE)
    await bot.handle_message(mode, None)
    bot.toggle_mode.assert_awaited_once_with(100, 1, mode)

    position = make_update(BTN_POSITION)
    await bot.handle_message(position, None)
    bot.toggle_position_filter.assert_awaited_once_with(100, 1, position)


@pytest.mark.asyncio
async def test_remove_and_history_buttons_call_handlers():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.start_remove_url = AsyncMock()
    bot.show_settings_history = AsyncMock()

    remove_url = make_update(BTN_REMOVE_URL)
    await bot.handle_message(remove_url, None)
    bot.start_remove_url.assert_awaited_once_with(100, remove_url)

    history = make_update(BTN_HISTORY)
    await bot.handle_message(history, None)
    bot.show_settings_history.assert_awaited_once_with(100, history)


@pytest.mark.asyncio
async def test_back_clears_pending_action():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.pending_actions[100] = 'DESIRED_PRICE'
    update = make_update(BTN_BACK)

    await bot.handle_message(update, None)

    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_message_shows_main_keyboard():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    update = make_update('какой-то текст')

    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert args[0] == 'Используй кнопки 👇'
    assert kwargs['reply_markup'] is not None


@pytest.mark.asyncio
async def test_removed_export_button_is_treated_as_unknown_text():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    update = make_update('📤 Экспорт')

    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == 'Используй кнопки 👇'
