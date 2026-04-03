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
import src.telegram_bot as telegram_module


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


def make_runtime(competitor_urls=None):
    return SimpleNamespace(
        MIN_PRICE=0.2,
        MAX_PRICE=1.0,
        UNDERCUT_VALUE=0.0051,
        MODE='STEP_UP',
        CHECK_INTERVAL=30,
        FAST_CHECK_INTERVAL_MIN=20,
        FAST_CHECK_INTERVAL_MAX=60,
        COOLDOWN_SECONDS=30,
        IGNORE_DELTA=0.001,
        MAX_DOWN_STEP=0.03,
        FAST_REBOUND_DELTA=0.01,
        NOTIFY_SKIP_COOLDOWN_SECONDS=300,
        COMPETITOR_CHANGE_DELTA=0.0001,
        COMPETITOR_CHANGE_COOLDOWN_SECONDS=60,
        PARSER_ISSUE_COOLDOWN_SECONDS=300,
        WEAK_POSITION_THRESHOLD=20,
        COMPETITOR_URLS=competitor_urls or ['https://example.com/item'],
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


@pytest.mark.asyncio
async def test_status_prefers_last_target_price():
    bot = make_bot()
    bot._state = lambda _profile: {
        'last_target_price': 0.2649,
        'last_price': 0.26,
        'last_competitor_min': 0.27,
        'last_update': None,
        'last_competitor_rank': None,
        'last_competitor_parse_at': None,
        'last_competitor_url': 'https://example.com/item-1',
        'last_competitor_method': 'api4_goods',
        'auto_mode': True,
        'update_count': 1,
        'skip_count': 2,
    }
    bot._runtime = lambda _profile: SimpleNamespace(
        MODE='STEP_UP',
        CHECK_INTERVAL=60,
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💰 Моя цена: 0.2649₽' in args[0]


@pytest.mark.asyncio
async def test_pending_price_action_formats_to_4dp(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = 'UNDERCUT_VALUE'
    bot._runtime = lambda _profile: SimpleNamespace(
        FAST_CHECK_INTERVAL_MIN=20,
        FAST_CHECK_INTERVAL_MAX=60,
    )
    bot.send_settings = AsyncMock()

    captured = {}

    def fake_set_runtime_setting(
        key,
        value,
        user_id=None,
        source='system',
        profile_id='ggsel',
    ):
        captured['key'] = key
        captured['value'] = value
        captured['user_id'] = user_id
        captured['source'] = source
        captured['profile_id'] = profile_id

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )
    update = make_update('0.00514')

    await bot.handle_pending_action(100, 1, '0.00514', update)

    assert captured['key'] == 'UNDERCUT_VALUE'
    assert captured['value'] == '0.0051'
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '✅ UNDERCUT_VALUE = 0.0051'


@pytest.mark.asyncio
async def test_diagnostics_includes_digiseller_token_perms_line():
    class DigiClient:
        def check_api_access(self):
            return True

        def get_product(self, _product_id):
            return SimpleNamespace(price=0.3333)

        def get_token_perms_status(self):
            return True, 'products.read, products.write'

    bot = TelegramBot(
        api_clients={'digiseller': DigiClient()},
        profile_products={'digiseller': 11},
        profile_default_urls={'digiseller': ['https://example.com/digi']},
        profile_labels={'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'digiseller'
    bot._state = lambda _profile: {
        'auto_mode': True,
        'last_cycle': None,
        'last_competitor_error': None,
        'last_competitor_block_reason': None,
    }
    bot._runtime = lambda _profile: make_runtime(['https://example.com/digi'])
    update = make_update(BTN_DIAGNOSTICS)

    await bot.send_diagnostics(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Профиль: DIGISELLER' in args[0]
    assert 'Token perms: OK (products.read, products.write)' in args[0]


@pytest.mark.asyncio
async def test_diagnostics_for_ggsel_has_no_token_perms_line():
    class GGClient:
        def check_api_access(self):
            return True

        def get_product(self, _product_id):
            return SimpleNamespace(price=0.2649)

    bot = TelegramBot(
        api_clients={'ggsel': GGClient()},
        profile_products={'ggsel': 22},
        profile_default_urls={'ggsel': ['https://example.com/gg']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    bot._state = lambda _profile: {
        'auto_mode': True,
        'last_cycle': None,
        'last_competitor_error': None,
        'last_competitor_block_reason': None,
    }
    bot._runtime = lambda _profile: make_runtime(['https://example.com/gg'])
    update = make_update(BTN_DIAGNOSTICS)

    await bot.send_diagnostics(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Профиль: GGSEL' in args[0]
    assert 'Token perms:' not in args[0]


@pytest.mark.asyncio
async def test_cmd_smoke_reports_active_profile_result(monkeypatch):
    bot = TelegramBot(
        api_clients={'digiseller': object()},
        profile_products={'digiseller': 9001},
        profile_default_urls={'digiseller': []},
        profile_labels={'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'digiseller'
    update = make_update('/smoke')

    monkeypatch.setattr(
        telegram_module,
        'run_profile_smoke',
        lambda *_args, **_kwargs: SimpleNamespace(
            api_access=True,
            product_read_ok=True,
            write_probe_ok=True,
            current_price=0.33,
            probe_price=0.33,
            verify_price=0.33,
            error=None,
        ),
    )

    await bot.cmd_smoke(update, None)

    assert update.message.reply_text.await_count == 2
    first_args, _first_kwargs = update.message.reply_text.await_args_list[0]
    second_args, _second_kwargs = update.message.reply_text.await_args_list[1]
    assert 'Запуск smoke API для профиля DIGISELLER' in first_args[0]
    assert '🧪 Smoke API' in second_args[0]
    assert 'Профиль: DIGISELLER' in second_args[0]
    assert 'API: OK' in second_args[0]


@pytest.mark.asyncio
async def test_cmd_smoke_fails_when_profile_not_configured():
    bot = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 0},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    update = make_update('/smoke')

    await bot.cmd_smoke(update, None)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Smoke недоступен' in args[0]
