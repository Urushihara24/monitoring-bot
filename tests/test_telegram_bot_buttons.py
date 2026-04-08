from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.telegram_bot import (
    BTN_ADD_URL,
    BTN_AUTO_OFF,
    BTN_AUTO_ON,
    BTN_BACK,
    BTN_CHAT_AUTOREPLY_OFF,
    BTN_CHAT_AUTOREPLY_ON,
    BTN_DOWN,
    BTN_INTERVAL,
    BTN_MAX,
    BTN_MIN,
    BTN_MODE,
    BTN_PRODUCT_NEXT,
    BTN_PRODUCT_PREV,
    BTN_POSITION,
    BTN_PRICE,
    BTN_PRODUCTS,
    BTN_PROFILE,
    BTN_REMOVE_URL,
    BTN_SETTINGS,
    BTN_SETTINGS_ADVANCED,
    BTN_SETTINGS_QUICK,
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
    bot._state = lambda _profile: {'auto_mode': True}
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


class ChatCapableClient:
    def list_chats(self, **_kwargs):
        return []

    def send_chat_message(self, _order_id, _message, timeout=10):
        return True

    def get_order_info(self, _order_id, **_kwargs):
        return {}

    def get_product_info(self, _product_id, timeout=10, lang=None):
        return {}


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
    assert BTN_ADD_URL in texts
    assert BTN_PRODUCTS not in texts
    assert BTN_PRODUCT_PREV not in texts
    assert BTN_PRODUCT_NEXT not in texts
    assert BTN_REMOVE_URL in texts
    assert BTN_PRICE not in texts
    assert BTN_STEP not in texts
    assert BTN_MIN not in texts
    assert BTN_MAX not in texts
    assert BTN_SETTINGS_ADVANCED in texts
    assert BTN_AUTO_OFF in texts
    assert BTN_AUTO_ON not in texts


def test_advanced_settings_keyboard_contains_expert_controls():
    bot = make_bot()
    texts = keyboard_texts(bot.get_settings_keyboard(advanced=True))
    assert BTN_SETTINGS_QUICK in texts
    assert BTN_PRICE in texts
    assert BTN_STEP in texts
    assert BTN_MIN in texts
    assert BTN_MAX in texts
    assert BTN_POSITION in texts
    assert BTN_PRODUCTS not in texts
    assert BTN_PRODUCT_PREV not in texts
    assert BTN_PRODUCT_NEXT not in texts
    assert BTN_AUTO_ON not in texts
    assert BTN_AUTO_OFF not in texts


def test_settings_keyboard_shows_chat_toggle_for_supported_profile():
    bot = TelegramBot(
        api_clients={'ggsel': ChatCapableClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    bot._state = lambda _profile: {'auto_mode': True}
    bot._chat_autoreply_enabled = lambda _profile: False

    texts = keyboard_texts(bot.get_settings_keyboard('ggsel'))
    assert BTN_CHAT_AUTOREPLY_ON in texts
    assert BTN_CHAT_AUTOREPLY_OFF not in texts


def test_main_keyboard_is_not_overloaded():
    bot = make_bot()
    texts = keyboard_texts(bot.get_main_keyboard('ggsel'))
    assert '🩺 Диагностика' not in texts
    assert BTN_PRODUCTS in texts
    assert BTN_PRODUCT_PREV in texts
    assert BTN_PRODUCT_NEXT in texts
    assert BTN_AUTO_ON not in texts
    assert BTN_AUTO_OFF not in texts
    assert BTN_UP not in texts
    assert BTN_DOWN not in texts
    settings_texts = keyboard_texts(bot.get_settings_keyboard())
    assert BTN_AUTO_ON not in settings_texts
    assert BTN_AUTO_OFF in settings_texts
    assert BTN_UP in settings_texts
    assert BTN_DOWN in settings_texts


@pytest.mark.asyncio
async def test_main_buttons_route_to_handlers():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}

    bot.send_status = AsyncMock()
    bot.handle_price_change = AsyncMock()
    bot.set_auto_enabled = AsyncMock()
    bot.set_chat_autoreply_enabled = AsyncMock()
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
    bot.set_auto_enabled.assert_any_await(auto, enabled=True)

    auto_off = make_update(BTN_AUTO_OFF)
    await bot.handle_message(auto_off, None)
    bot.set_auto_enabled.assert_any_await(auto_off, enabled=False)

    settings = make_update(BTN_SETTINGS)
    await bot.handle_message(settings, None)
    bot.send_settings.assert_awaited_once_with(100, settings)

    bot.send_settings.reset_mock()
    adv = make_update(BTN_SETTINGS_ADVANCED)
    await bot.handle_message(adv, None)
    bot.send_settings.assert_awaited_once_with(100, adv)

    bot.send_settings.reset_mock()
    quick = make_update(BTN_SETTINGS_QUICK)
    await bot.handle_message(quick, None)
    bot.send_settings.assert_awaited_once_with(100, quick)

    chat_on = make_update(BTN_CHAT_AUTOREPLY_ON)
    await bot.handle_message(chat_on, None)
    bot.set_chat_autoreply_enabled.assert_any_await(
        100, 1, chat_on, enabled=True
    )

    chat_off = make_update(BTN_CHAT_AUTOREPLY_OFF)
    await bot.handle_message(chat_off, None)
    bot.set_chat_autoreply_enabled.assert_any_await(
        100, 1, chat_off, enabled=False
    )


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
        (BTN_PRODUCTS, 'MANAGE_PRODUCTS'),
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
    bot.switch_active_product = AsyncMock()

    mode = make_update(BTN_MODE)
    await bot.handle_message(mode, None)
    bot.toggle_mode.assert_awaited_once_with(100, 1, mode)

    position = make_update(BTN_POSITION)
    await bot.handle_message(position, None)
    bot.toggle_position_filter.assert_awaited_once_with(100, 1, position)

    prev_product = make_update(BTN_PRODUCT_PREV)
    await bot.handle_message(prev_product, None)
    bot.switch_active_product.assert_any_await(
        100,
        prev_product,
        step=-1,
    )

    next_product = make_update(BTN_PRODUCT_NEXT)
    await bot.handle_message(next_product, None)
    bot.switch_active_product.assert_any_await(
        100,
        next_product,
        step=1,
    )


@pytest.mark.asyncio
async def test_toggle_mode_cycles_through_follow_modes(monkeypatch):
    bot = make_bot()
    bot.chat_profile[100] = 'ggsel'
    bot.send_settings = AsyncMock()
    update = make_update(BTN_MODE)

    captured = []

    def fake_set_runtime_setting(
        key,
        value,
        user_id=None,
        source='system',
        profile_id='ggsel',
    ):
        captured.append((key, value, user_id, source, profile_id))

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    bot._runtime = lambda _profile: SimpleNamespace(MODE='DUMPING')
    await bot.toggle_mode(100, 1, update)
    assert captured[-1][1] == 'RAISE'

    bot._runtime = lambda _profile: SimpleNamespace(MODE='RAISE')
    await bot.toggle_mode(100, 1, update)
    assert captured[-1][1] == 'FOLLOW'

    bot._runtime = lambda _profile: SimpleNamespace(MODE='FOLLOW')
    await bot.toggle_mode(100, 1, update)
    assert captured[-1][1] == 'DUMPING'


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
    bot.send_settings = AsyncMock()
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
    assert args[0] == '🔔 Автоцена (DIGISELLER / 2): ВЫКЛ'


@pytest.mark.asyncio
async def test_set_chat_autoreply_enabled_updates_runtime_setting(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': ChatCapableClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'ggsel'
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
    update = make_update(BTN_CHAT_AUTOREPLY_ON)

    await bot.set_chat_autoreply_enabled(100, 1, update, enabled=True)

    assert captured == {
        'key': 'CHAT_AUTOREPLY_ENABLED',
        'value': 'true',
        'user_id': 1,
        'source': 'telegram',
        'profile_id': 'ggsel',
    }
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '💬 Авто-инструкции: ВКЛ'


@pytest.mark.asyncio
async def test_remove_url_button_calls_handler():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.start_remove_url = AsyncMock()

    remove_url = make_update(BTN_REMOVE_URL)
    await bot.handle_message(remove_url, None)
    bot.start_remove_url.assert_awaited_once_with(100, remove_url)


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
async def test_switch_active_product_cycles_and_clears_pending():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.send_settings = AsyncMock()
    bot.profile_products['ggsel'] = 1002
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot._tracked_product_ids = lambda _profile, runtime=None: [1001, 1002, 1003]
    update = make_update(BTN_PRODUCT_NEXT)

    await bot.switch_active_product(100, update, step=1)

    assert bot.profile_products['ggsel'] == 1003
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert 'Активный товар: 1003 (3/3)' in args[0]
    assert 'Незавершённый ввод сброшен' in args[0]
    assert 'Открой ⚙ Настройки' in args[0]
    assert BTN_SETTINGS in keyboard_texts(kwargs['reply_markup'])
    assert BTN_PRODUCT_PREV in keyboard_texts(kwargs['reply_markup'])
    bot.send_settings.assert_not_called()


@pytest.mark.asyncio
async def test_switch_active_product_with_single_product_keeps_selection():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.send_settings = AsyncMock()
    bot.profile_products['ggsel'] = 1001
    bot._tracked_product_ids = lambda _profile, runtime=None: [1001]
    update = make_update(BTN_PRODUCT_PREV)

    await bot.switch_active_product(100, update, step=-1)

    assert bot.profile_products['ggsel'] == 1001
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.await_args
    assert 'Активный товар: 1001 (1/1)' in args[0]
    assert BTN_SETTINGS in keyboard_texts(kwargs['reply_markup'])
    assert BTN_PRODUCT_NEXT in keyboard_texts(kwargs['reply_markup'])
    bot.send_settings.assert_not_called()


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
async def test_status_shows_last_target_price():
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
    assert '🎯 Выставлено ботом: 0.2649₽' in args[0]


@pytest.mark.asyncio
async def test_status_shows_digiseller_chat_autoreply_block(monkeypatch):
    bot = TelegramBot(
        api_clients={'digiseller': ChatCapableClient()},
        profile_products={'digiseller': 5077639},
        profile_default_urls={'digiseller': ['https://example.com']},
        profile_labels={'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'digiseller'
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

    monkeypatch.setattr(
        telegram_module.config,
        'DIGISELLER_CHAT_AUTOREPLY_ENABLED',
        True,
    )
    monkeypatch.setattr(
        telegram_module.config,
        'DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS',
        [5077639, 5104800],
    )

    def fake_runtime_setting(key, profile_id='ggsel'):
        if profile_id != 'digiseller':
            return None
        mapping = {
            'CHAT_AUTOREPLY_SENT_COUNT': '7',
            'CHAT_AUTOREPLY_DUPLICATE_COUNT': '3',
            'CHAT_AUTOREPLY_LAST_RUN_AT': '2026-04-04T10:00:00',
            'CHAT_AUTOREPLY_LAST_SENT_AT': '2026-04-04T10:01:00Z',
            'CHAT_AUTOREPLY_LAST_ERROR': '',
        }
        return mapping.get(key)

    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        fake_runtime_setting,
    )

    update = make_update(BTN_STATUS)
    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💬 Авто-инструкции: ВКЛ' in args[0]
    assert '📦 Товары: 5077639, 5104800' in args[0]
    assert '📨 Отправлено: 7' in args[0]
    assert '🧷 Дубликаты: 3' in args[0]
    assert '🕓 Последняя отправка:' in args[0]
    assert '10:01:00Z' not in args[0]


@pytest.mark.asyncio
async def test_status_shows_ggsel_chat_autoreply_block(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': ChatCapableClient()},
        profile_products={'ggsel': 4697439},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'ggsel'
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

    monkeypatch.setattr(
        telegram_module.config,
        'GGSEL_CHAT_AUTOREPLY_ENABLED',
        True,
    )
    monkeypatch.setattr(
        telegram_module.config,
        'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS',
        [4697439],
    )

    def fake_runtime_setting(key, profile_id='ggsel'):
        if profile_id != 'ggsel':
            return None
        mapping = {
            'CHAT_AUTOREPLY_SENT_COUNT': '4',
            'CHAT_AUTOREPLY_DUPLICATE_COUNT': '1',
            'CHAT_AUTOREPLY_LAST_SENT_AT': '2026-04-04T11:00:00',
        }
        return mapping.get(key)

    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        fake_runtime_setting,
    )

    update = make_update(BTN_STATUS)
    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💬 Авто-инструкции: ВКЛ' in args[0]
    assert '📦 Товары: 4697439' in args[0]
    assert '📨 Отправлено: 4' in args[0]


@pytest.mark.asyncio
async def test_status_shows_live_api_price_over_state():
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
    assert '🎯 Выставлено ботом: 0.2649₽' in args[0]


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
    assert '🎯 Выставлено ботом: 0.2649₽' in args[0]


@pytest.mark.asyncio
async def test_status_digiseller_uses_target_when_display_unavailable():
    class ApiClient:
        def get_display_price(self, _product_id):
            return None

        def get_my_price(self, _product_id):
            return 1.1

    bot = TelegramBot(
        api_clients={'digiseller': ApiClient()},
        profile_products={'digiseller': 5077639},
        profile_default_urls={'digiseller': []},
        profile_labels={'digiseller': 'DIGISELLER'},
    )
    bot.admin_ids = {1}
    bot._state = lambda _profile: {
        'last_target_price': 0.3249,
        'last_price': 0.3249,
        'last_competitor_min': 0.33,
        'last_update': None,
        'last_competitor_rank': None,
        'last_competitor_parse_at': None,
        'last_competitor_url': 'https://plati.market/itm/name/5077639',
        'last_competitor_method': 'stealth_requests',
        'auto_mode': True,
        'update_count': 1,
        'skip_count': 2,
    }
    bot._runtime = lambda _profile: SimpleNamespace(
        MODE='STEP_UP',
        CHECK_INTERVAL=30,
        COMPETITOR_URLS=[],
    )
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update, profile_id='digiseller')

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '💰 Моя цена: 0.3249₽' in args[0]
    assert '🎯 Выставлено ботом: 0.3249₽' in args[0]


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
    assert args[0] == '✅ UNDERCUT_VALUE (GGSEL / 1) = 0.0051'


@pytest.mark.asyncio
async def test_toggle_mode_isolated_for_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    bot.send_settings = AsyncMock()
    bot._runtime_for_product = lambda _profile, _product: SimpleNamespace(
        MODE='DUMPING'
    )
    update = make_update(BTN_MODE)

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
        captured['profile_id'] = profile_id

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    await bot.toggle_mode(100, 1, update)

    assert captured['key'] == 'MODE'
    assert captured['value'] == 'RAISE'
    assert captured['profile_id'] == 'ggsel:999'


@pytest.mark.asyncio
async def test_pending_price_action_isolated_for_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.send_settings = AsyncMock()
    bot._runtime_for_product = lambda _profile, _product: SimpleNamespace(
        FAST_CHECK_INTERVAL_MIN=20,
        FAST_CHECK_INTERVAL_MAX=60,
    )
    update = make_update('0.30')

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
        captured['profile_id'] = profile_id

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    await bot.handle_pending_action(100, 1, '0.30', update)

    assert captured['key'] == 'MIN_PRICE'
    assert captured['value'] == '0.3'
    assert captured['profile_id'] == 'ggsel:999'


@pytest.mark.asyncio
async def test_pending_manage_products_add(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MANAGE_PRODUCTS', 'ggsel')
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda _profile_id, runtime=None: [],
    )

    captured = {}

    def fake_upsert_tracked_product(
        *,
        profile_id='ggsel',
        product_id=0,
        competitor_urls=None,
        enabled=True,
    ):
        captured['profile_id'] = profile_id
        captured['product_id'] = product_id
        captured['competitor_urls'] = competitor_urls
        captured['enabled'] = enabled

    monkeypatch.setattr(
        telegram_module.storage,
        'upsert_tracked_product',
        fake_upsert_tracked_product,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'normalize_competitor_urls',
        lambda urls: [u.strip() for u in urls if u.strip()],
    )
    update = make_update('4697439')

    await bot.handle_pending_action(
        100,
        1,
        '4697439',
        update,
    )

    assert captured == {
        'profile_id': 'ggsel',
        'product_id': 4697439,
        'competitor_urls': [],
        'enabled': True,
    }
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Товар 4697439 добавлен' in args[0]


@pytest.mark.asyncio
async def test_pending_manage_products_add_inline_pair(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MANAGE_PRODUCTS', 'ggsel')
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda _profile_id, runtime=None: [],
    )

    captured = {}

    def fake_upsert_tracked_product(
        *,
        profile_id='ggsel',
        product_id=0,
        competitor_urls=None,
        enabled=True,
    ):
        captured['profile_id'] = profile_id
        captured['product_id'] = product_id
        captured['competitor_urls'] = competitor_urls
        captured['enabled'] = enabled

    monkeypatch.setattr(
        telegram_module.storage,
        'upsert_tracked_product',
        fake_upsert_tracked_product,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'normalize_competitor_urls',
        lambda urls: [u.strip() for u in urls if u.strip()],
    )
    update = make_update('4697439 https://a.example/item')

    await bot.handle_pending_action(
        100,
        1,
        '4697439 https://a.example/item',
        update,
    )

    assert captured == {
        'profile_id': 'ggsel',
        'product_id': 4697439,
        'competitor_urls': ['https://a.example/item'],
        'enabled': True,
    }
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Пара(ы) добавлены: 1' in args[0]


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

        def list_chats(self, **_kwargs):
            return []

        def send_chat_message(self, _order_id, _message, timeout=10):
            return True

        def get_order_info(self, _order_id, **_kwargs):
            return {}

        def get_product_info(self, _product_id, timeout=10, lang=None):
            return {}

        def get_token_perms_status(self):
            return True, 'products.read, products.write'

        def get_chat_perms_status(self, timeout=8, include_send_probe=False):
            assert timeout == 8
            assert include_send_probe is False
            return True, 'chats.read=OK[http_200]'

        def can_refresh_access_token(self):
            return True

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
    assert 'Chat perms: OK (chats.read=OK[http_200])' in args[0]
    assert 'Token refresh: OK' in args[0]
    assert 'Chat autoreply:' in args[0]
    assert 'Chat dedupe:' in args[0]


@pytest.mark.asyncio
async def test_diagnostics_for_ggsel_has_no_token_perms_line():
    class GGClient:
        def check_api_access(self):
            return True

        def get_product(self, _product_id):
            return SimpleNamespace(price=0.2649)

        def can_refresh_access_token(self):
            return False

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
    assert 'Token refresh: FAIL' in args[0]


@pytest.mark.asyncio
async def test_diagnostics_includes_chat_perms_line_when_supported():
    class GGClient:
        def check_api_access(self):
            return True

        def get_product(self, _product_id):
            return SimpleNamespace(price=0.2649)

        def can_refresh_access_token(self):
            return True

        def get_chat_perms_status(self, timeout=8, include_send_probe=False):
            assert timeout == 8
            assert include_send_probe is False
            return False, 'chats.read=FAIL[http_403]'

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
    assert 'Chat perms: FAIL (chats.read=FAIL[http_403])' in args[0]


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
            token_refresh_ok=False,
            token_refresh_desc='api_secret_missing',
            error=None,
        ),
    )

    await bot.cmd_smoke(update, None)

    assert update.message.reply_text.await_count == 2
    second_args, _second_kwargs = update.message.reply_text.await_args_list[1]
    assert 'Token perms: OK (products.read, products.write)' in second_args[0]
    assert 'Token refresh: FAIL (api_secret_missing)' in second_args[0]


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


@pytest.mark.asyncio
async def test_unknown_pending_action_is_reset_with_warning_message():
    bot = make_bot()
    bot.admin_ids = {1}
    bot.pending_actions[100] = ('UNKNOWN_ACTION', 'ggsel')
    update = make_update('some-value')

    await bot.handle_message(update, None)

    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'неизвестное действие' in args[0].lower()
