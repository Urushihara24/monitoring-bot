from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.telegram_bot import (
    BTN_ADD_URL,
    BTN_AUTO_OFF,
    BTN_AUTO_ON,
    BTN_BACK,
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


def test_main_keyboard_is_not_overloaded():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    texts = keyboard_texts(bot.get_main_keyboard('ggsel'))
    assert '🩺 Диагностика' not in texts
    assert BTN_UP not in texts
    assert BTN_DOWN not in texts
    settings_texts = keyboard_texts(bot.get_settings_keyboard())
    assert BTN_UP in settings_texts
    assert BTN_DOWN in settings_texts


@pytest.mark.asyncio
async def test_main_buttons_route_to_handlers():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}

    bot.send_status = AsyncMock()
    bot.handle_price_change = AsyncMock()
    bot.toggle_auto = AsyncMock()
    bot.send_settings = AsyncMock()

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

    assert bot.pending_actions[100] == (expected_action, 'ggsel')
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
async def test_toggle_auto_updates_only_active_profile(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 2},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'digiseller'
    bot._state = lambda _profile: {'auto_mode': True}
    update = make_update(BTN_AUTO_ON)

    calls = []

    def fake_update_state(*, profile_id='ggsel', **kwargs):
        calls.append((profile_id, kwargs))

    monkeypatch.setattr(
        telegram_module.storage,
        'update_state',
        fake_update_state,
    )

    await bot.toggle_auto(update)

    assert calls == [('digiseller', {'auto_mode': False})]
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '🔔 Авто: ВЫКЛ'


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
    bot.pending_actions[100] = ('DESIRED_PRICE', 'ggsel')
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
        COMPETITOR_URLS=['https://example.com/item-1'],
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💰 Моя цена: 0.2649₽' in args[0]


@pytest.mark.asyncio
async def test_status_prefers_live_api_price_over_state():
    class ApiClient:
        def get_my_price(self, product_id):
            assert product_id == 1
            return 0.2711

    bot = TelegramBot(
        api_clients={'ggsel': ApiClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
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
        COMPETITOR_URLS=['https://example.com/item-1'],
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💰 Моя цена: 0.2711₽' in args[0]


@pytest.mark.asyncio
async def test_status_formats_live_api_price_to_4dp():
    class ApiClient:
        def get_my_price(self, _product_id):
            return 0.25

    bot = TelegramBot(
        api_clients={'ggsel': ApiClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
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
        COMPETITOR_URLS=['https://example.com/item-1'],
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💰 Моя цена: 0.2500₽' in args[0]


@pytest.mark.asyncio
async def test_status_falls_back_to_state_when_live_api_fails():
    class ApiClient:
        def get_my_price(self, _product_id):
            raise RuntimeError('api timeout')

    bot = TelegramBot(
        api_clients={'ggsel': ApiClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
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
        COMPETITOR_URLS=['https://example.com/item-1'],
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💰 Моя цена: 0.2649₽' in args[0]


@pytest.mark.asyncio
async def test_pending_price_action_formats_to_4dp(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('UNDERCUT_VALUE', 'ggsel')
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
async def test_profile_switch_clears_pending_action():
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 2},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot._state = lambda _profile: {'auto_mode': True}
    bot._set_pending_action(100, 'MIN_PRICE', 'ggsel')
    update = make_update('🧩 DIGISELLER')

    await bot.handle_message(update, None)

    assert bot._active_profile(100) == 'digiseller'
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Незавершённый ввод сброшен' in args[0]


@pytest.mark.asyncio
async def test_pending_action_is_not_applied_to_other_profile(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 2},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot._state = lambda _profile: {'auto_mode': True}
    bot._runtime = lambda _profile: make_runtime([])

    called = {'value': False}

    def fake_set_runtime_setting(*_args, **_kwargs):
        called['value'] = True

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.chat_profile[100] = 'digiseller'
    update = make_update('0.25')

    await bot.handle_pending_action(100, 1, '0.25', update)

    assert called['value'] is False
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'активный профиль был изменён' in args[0]


@pytest.mark.asyncio
async def test_add_url_duplicate_shows_info_and_keeps_pending(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('ADD_URL', 'ggsel')
    bot._runtime = lambda _profile: make_runtime(['https://example.com/item'])

    monkeypatch.setattr(
        telegram_module.storage,
        'get_competitor_urls',
        lambda *_args, **_kwargs: ['https://example.com/item'],
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'normalize_competitor_urls',
        lambda urls: list(dict.fromkeys(u.strip().rstrip('/') for u in urls)),
    )
    set_calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_competitor_urls',
        lambda *args, **kwargs: set_calls.append((args, kwargs)),
    )
    update = make_update('https://example.com/item/')

    await bot.handle_pending_action(100, 1, 'https://example.com/item/', update)

    assert set_calls == []
    assert bot.pending_actions.get(100) == ('ADD_URL', 'ggsel')
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'URL уже есть в списке' in args[0]


@pytest.mark.asyncio
async def test_add_url_saves_normalized_value(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('ADD_URL', 'ggsel')
    bot._runtime = lambda _profile: make_runtime(['https://example.com/item'])
    bot.send_settings = AsyncMock()

    monkeypatch.setattr(
        telegram_module.storage,
        'get_competitor_urls',
        lambda *_args, **_kwargs: ['https://example.com/item'],
    )

    def fake_normalize(urls):
        normalized = []
        seen = set()
        for value in urls:
            item = value.strip().lower().rstrip('/')
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    monkeypatch.setattr(
        telegram_module.storage,
        'normalize_competitor_urls',
        fake_normalize,
    )
    saved = {}

    def fake_set_competitor_urls(urls, **kwargs):
        saved['urls'] = urls
        saved['kwargs'] = kwargs

    monkeypatch.setattr(
        telegram_module.storage,
        'set_competitor_urls',
        fake_set_competitor_urls,
    )
    update = make_update('HTTPS://EXAMPLE.COM/new-item/')

    await bot.handle_pending_action(100, 1, 'HTTPS://EXAMPLE.COM/new-item/', update)

    assert saved['urls'] == [
        'https://example.com/item',
        'https://example.com/new-item',
    ]
    assert saved['kwargs']['profile_id'] == 'ggsel'
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '✅ URL добавлен: https://example.com/new-item'


@pytest.mark.asyncio
async def test_add_url_invalid_value_shows_error_and_keeps_pending(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('ADD_URL', 'ggsel')
    bot._runtime = lambda _profile: make_runtime(['https://example.com/item'])

    monkeypatch.setattr(
        telegram_module.storage,
        'normalize_competitor_urls',
        lambda urls: [],
    )
    set_calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_competitor_urls',
        lambda *args, **kwargs: set_calls.append((args, kwargs)),
    )
    update = make_update('example.com/no-scheme')

    await bot.handle_pending_action(100, 1, 'example.com/no-scheme', update)

    assert set_calls == []
    assert bot.pending_actions.get(100) == ('ADD_URL', 'ggsel')
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '❌ Нужен валидный URL (http/https)'


@pytest.mark.asyncio
async def test_remove_url_invalid_index_shows_error_and_keeps_pending(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('REMOVE_URL', 'ggsel')
    bot._runtime = lambda _profile: make_runtime(['https://example.com/item'])

    monkeypatch.setattr(
        telegram_module.storage,
        'get_competitor_urls',
        lambda *_args, **_kwargs: [
            'https://example.com/1',
            'https://example.com/2',
        ],
    )
    set_calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_competitor_urls',
        lambda *args, **kwargs: set_calls.append((args, kwargs)),
    )
    update = make_update('99')

    await bot.handle_pending_action(100, 1, '99', update)

    assert set_calls == []
    assert bot.pending_actions.get(100) == ('REMOVE_URL', 'ggsel')
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '❌ Неверный номер URL'


@pytest.mark.asyncio
async def test_status_shows_monitoring_disabled_when_no_urls():
    bot = make_bot()
    bot._state = lambda _profile: {
        'last_target_price': None,
        'last_price': 0.2649,
        'last_competitor_min': None,
        'last_update': None,
        'last_competitor_rank': None,
        'last_competitor_parse_at': None,
        'last_competitor_url': None,
        'last_competitor_method': None,
        'auto_mode': True,
        'update_count': 0,
        'skip_count': 0,
    }
    bot._runtime = lambda _profile: SimpleNamespace(
        MODE='STEP_UP',
        CHECK_INTERVAL=60,
        COMPETITOR_URLS=[],
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '📡 Мониторинг: ВЫКЛ (нет URL)' in args[0]


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
    update = make_update('/diag')

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
    update = make_update('/diag')

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
    assert 'Current price: 0.3300' in second_args[0]
    assert 'Probe price: 0.3300' in second_args[0]
    assert 'Verify price: 0.3300' in second_args[0]


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


@pytest.mark.asyncio
async def test_cmd_smoke_includes_token_perms_when_present(monkeypatch):
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
            current_price=0.22,
            probe_price=0.22,
            verify_price=0.22,
            token_perms_ok=True,
            token_perms_desc='products.read, products.write',
            error=None,
        ),
    )

    await bot.cmd_smoke(update, None)

    assert update.message.reply_text.await_count == 2
    second_args, _second_kwargs = update.message.reply_text.await_args_list[1]
    assert 'Token perms: OK (products.read, products.write)' in second_args[0]


@pytest.mark.asyncio
async def test_cmd_smoke_accepts_profile_arg_from_command(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 9001},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    update = make_update('/smoke digiseller')
    context = SimpleNamespace(args=['digiseller'])

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
            token_perms_ok=True,
            token_perms_desc='ok',
            error=None,
        ),
    )

    await bot.cmd_smoke(update, context)

    assert update.message.reply_text.await_count == 2
    second_args, _second_kwargs = update.message.reply_text.await_args_list[1]
    assert 'Профиль: DIGISELLER' in second_args[0]


@pytest.mark.asyncio
async def test_cmd_smoke_accepts_plati_alias_from_command(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': object(), 'digiseller': object()},
        profile_products={'ggsel': 1, 'digiseller': 9001},
        profile_default_urls={'ggsel': [], 'digiseller': []},
        profile_labels={'ggsel': 'GGSEL', 'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    update = make_update('/smoke plati')
    context = SimpleNamespace(args=['plati'])

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
            token_perms_ok=True,
            token_perms_desc='ok',
            error=None,
        ),
    )

    await bot.cmd_smoke(update, context)

    assert update.message.reply_text.await_count == 2
    second_args, _second_kwargs = update.message.reply_text.await_args_list[1]
    assert 'Профиль: DIGISELLER' in second_args[0]


@pytest.mark.asyncio
async def test_cmd_smoke_rejects_unknown_profile_arg():
    bot = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    update = make_update('/smoke unknown')
    context = SimpleNamespace(args=['unknown'])

    await bot.cmd_smoke(update, context)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Неизвестный профиль' in args[0]


@pytest.mark.asyncio
async def test_diagnostics_formats_product_price_to_4dp():
    class GGClient:
        def check_api_access(self):
            return True

        def get_product(self, _product_id):
            return SimpleNamespace(price=0.33)

    bot = TelegramBot(
        api_clients={'ggsel': GGClient()},
        profile_products={'ggsel': 100},
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
    update = make_update('/diag')

    await bot.send_diagnostics(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Product: OK (0.3300₽)' in args[0]
