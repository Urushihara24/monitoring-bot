import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import chat_autoreply as chat_keys
from src.telegram_bot import (
    BTN_AUTO_OFF,
    BTN_AUTO_ON,
    BTN_BACK,
    BTN_CHAT_AUTOREPLY_OFF,
    BTN_CHAT_AUTOREPLY_ON,
    BTN_CHAT_EMPTY_ONLY_OFF,
    BTN_CHAT_EMPTY_ONLY_ON,
    BTN_CHAT_POLICY,
    BTN_CHAT_SMART_NON_EMPTY_OFF,
    BTN_CHAT_SMART_NON_EMPTY_ON,
    BTN_CHAT_RULES,
    BTN_MAX,
    BTN_MODE,
    BTN_MIN,
    BTN_PRODUCT_NEXT,
    BTN_PRODUCT_PREV,
    BTN_PRODUCT_REMOVE,
    BTN_PRICE_GUARD,
    BTN_PRICE,
    BTN_PRODUCTS,
    BTN_PROFILE,
    BTN_RAISE,
    BTN_REBOUND_OFF,
    BTN_ROUNDING,
    BTN_SETTINGS,
    BTN_STATUS,
    BTN_UNDERCUT,
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


def test_runtime_profile_id_for_primary_product_is_product_scoped():
    bot = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 4697439},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    assert bot._runtime_profile_id_for_product('ggsel', 4697439) == (
        'ggsel:4697439'
    )
    assert bot._runtime_profile_id_for_product('ggsel', 0) == 'ggsel'


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


def make_callback_update(data: str):
    message = SimpleNamespace(
        edit_text=AsyncMock(),
        reply_text=AsyncMock(),
    )
    callback_query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=message,
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=100),
        callback_query=callback_query,
    )


def make_runtime(competitor_urls=None):
    return SimpleNamespace(
        MIN_PRICE=0.2,
        MAX_PRICE=1.0,
        DESIRED_PRICE=0.35,
        UNDERCUT_VALUE=0.0051,
        RAISE_VALUE=0.0049,
        SHOWCASE_ROUND_STEP=0.01,
        REBOUND_TO_DESIRED_ON_MIN=False,
        MODE='STEP_UP',
        CHECK_INTERVAL=30,
        UPDATE_ONLY_ON_COMPETITOR_CHANGE=True,
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


def test_build_chat_rules_items_prefers_friend_variants_only():
    bot = make_bot()
    payload = {
        'options': [
            {
                'name': 'Укажите свой ник в Fortnite',
                'variants': [
                    {'text': 'Пример ника'},
                ],
            },
            {
                'name': 'Наши аккаунты в друзьях?',
                'variants': [
                    {'text': 'Нет. Добавлю после оплаты'},
                    {'text': 'Да. Проверил(а), в друзьях'},
                ],
            },
            {
                'name': 'Изучили описание товара?',
                'variants': [
                    {'text': 'Да (я буду заказывать предметы, а не В-Баксы)'},
                ],
            },
        ],
    }

    items = bot._build_chat_rules_items(payload)

    assert len(items) == 2
    values = [item['value'] for item in items]
    assert 'Нет. Добавлю после оплаты' in values
    assert 'Да. Проверил(а), в друзьях' in values


def test_build_chat_rules_items_uses_human_label_when_name_is_numeric():
    bot = make_bot()
    payload = {
        'options': [
            {
                'name': '32496',
                'label': 'Наши аккаунты ***8rabbit в друзьях?',
                'variants': [
                    {'value': 1, 'text': 'Нет. Добавлю после оплаты'},
                    {'value': 2, 'text': 'Да. Проверил(а), в друзьях'},
                ],
            },
        ],
    }

    items = bot._build_chat_rules_items(payload)

    assert len(items) == 2
    assert all(item['option'] == 'Наши аккаунты ***8rabbit в друзьях?' for item in items)


def test_settings_keyboard_is_not_overloaded():
    bot = make_bot()
    texts = keyboard_texts(bot.get_settings_keyboard())
    assert '📤 Экспорт' not in texts
    assert '📥 Импорт' not in texts
    assert BTN_PRODUCTS not in texts
    assert BTN_PRODUCT_REMOVE in texts
    assert BTN_PRODUCT_PREV not in texts
    assert BTN_PRODUCT_NEXT not in texts
    assert BTN_PRICE in texts
    assert BTN_PRICE_GUARD in texts
    assert BTN_MIN not in texts
    assert BTN_MAX not in texts
    assert BTN_UNDERCUT not in texts
    assert BTN_RAISE not in texts
    assert BTN_ROUNDING not in texts
    assert BTN_REBOUND_OFF not in texts
    assert BTN_MODE in texts
    assert BTN_AUTO_OFF in texts
    assert BTN_AUTO_ON not in texts


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
    assert BTN_CHAT_EMPTY_ONLY_OFF in texts
    assert BTN_CHAT_EMPTY_ONLY_ON not in texts
    assert BTN_CHAT_SMART_NON_EMPTY_ON in texts
    assert BTN_CHAT_SMART_NON_EMPTY_OFF not in texts
    assert BTN_CHAT_POLICY in texts
    assert BTN_CHAT_RULES in texts


def test_main_keyboard_is_not_overloaded():
    bot = make_bot()
    texts = keyboard_texts(bot.get_main_keyboard('ggsel'))
    assert '🩺 Диагностика' not in texts
    assert BTN_PRODUCTS in texts
    assert BTN_PRODUCT_PREV in texts
    assert BTN_PRODUCT_NEXT in texts
    assert BTN_AUTO_ON not in texts
    assert BTN_AUTO_OFF not in texts
    settings_texts = keyboard_texts(bot.get_settings_keyboard())
    assert BTN_AUTO_ON not in settings_texts


@pytest.mark.asyncio
async def test_products_button_opens_inline_products_menu(monkeypatch):
    bot = make_bot()
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: make_runtime(['https://example.com/item']),
    )
    monkeypatch.setattr(
        bot,
        '_format_tracked_products',
        lambda *_args, **_kwargs: ['4697439 active'],
    )
    monkeypatch.setattr(bot, '_product_id', lambda _profile: 4697439)
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {
                'product_id': 4697439,
                'competitor_urls': ['https://example.com/item'],
                'enabled': True,
            }
        ],
    )

    update = make_update(BTN_PRODUCTS)
    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    _args, kwargs = update.message.reply_text.await_args
    markup = kwargs['reply_markup']
    assert hasattr(markup, 'inline_keyboard')
    flat = [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]
    assert '➕ Товар' in flat
    assert '🔗 Конкурент' in flat
    assert '✏️ Переименовать' in flat
    assert '🗑 Удалить активный' in flat


@pytest.mark.asyncio
async def test_products_button_realigns_stale_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    captured = {'product_id': None}

    def fake_runtime_for_product(_profile, product_id):
        captured['product_id'] = product_id
        return make_runtime([])

    monkeypatch.setattr(bot, '_runtime_for_product', fake_runtime_for_product)
    update = make_update(BTN_PRODUCTS)

    await bot.handle_message(update, None)

    assert bot.profile_products['ggsel'] == 4697439
    assert captured['product_id'] == 4697439


@pytest.mark.asyncio
async def test_products_button_clears_existing_pending_action(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: make_runtime([]),
    )
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    update = make_update(BTN_PRODUCTS)

    await bot.handle_message(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at


@pytest.mark.asyncio
async def test_products_callback_add_sets_pending_action():
    bot = make_bot()
    update = make_callback_update('pm:a')

    await bot.handle_callback_query(update, None)

    assert bot.pending_actions[100] == ('PRODUCT_ADD', 'ggsel')
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_products_callback_add_url_realigns_stale_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    update = make_callback_update('pm:u')

    await bot.handle_callback_query(update, None)

    assert bot.profile_products['ggsel'] == 4697439
    assert bot.pending_actions[100] == ('PRODUCT_ADD_URL', 'ggsel')
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_products_callback_add_url_without_active_pair_clears_pending(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 999
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [],
    )
    update = make_callback_update('pm:u')

    await bot.handle_callback_query(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_products_callback_rename_without_active_pair_clears_pending(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 999
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [],
    )
    update = make_callback_update('pm:n')

    await bot.handle_callback_query(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_products_callback_refresh_realigns_stale_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    captured = {'product_id': None}

    def fake_runtime_for_product(_profile, product_id):
        captured['product_id'] = product_id
        return make_runtime([])

    monkeypatch.setattr(bot, '_runtime_for_product', fake_runtime_for_product)
    update = make_callback_update('pm:r')

    await bot.handle_callback_query(update, None)

    assert bot.profile_products['ggsel'] == 4697439
    assert captured['product_id'] == 4697439


@pytest.mark.asyncio
async def test_products_callback_refresh_clears_existing_pending_action(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: make_runtime([]),
    )
    update = make_callback_update('pm:r')

    await bot.handle_callback_query(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at


@pytest.mark.asyncio
async def test_products_callback_select_active_product_refreshes_menu(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4697439
    monkeypatch.setattr(
        bot,
        '_tracked_product_ids',
        lambda _profile, runtime=None: [4697439, 5104800],
    )
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
            {'product_id': 5104800, 'competitor_urls': [], 'enabled': True},
        ],
    )
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: make_runtime([]),
    )
    monkeypatch.setattr(bot, '_product_name', lambda _profile, pid: f'P{pid}')
    monkeypatch.setattr(bot, '_format_tracked_products', lambda *_args, **_kwargs: ['x'])
    monkeypatch.setattr(bot, '_ensure_product_auto_name', AsyncMock())
    update = make_callback_update('pm:s:5104800')

    await bot.handle_callback_query(update, None)

    assert bot.profile_products['ggsel'] == 5104800
    update.callback_query.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_products_callback_select_active_product_clears_pending(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4697439
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    monkeypatch.setattr(
        bot,
        '_tracked_product_ids',
        lambda _profile, runtime=None: [4697439, 5104800],
    )
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
            {'product_id': 5104800, 'competitor_urls': [], 'enabled': True},
        ],
    )
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: make_runtime([]),
    )
    monkeypatch.setattr(bot, '_product_name', lambda _profile, pid: f'P{pid}')
    monkeypatch.setattr(
        bot,
        '_format_tracked_products',
        lambda *_args, **_kwargs: ['x'],
    )
    monkeypatch.setattr(bot, '_ensure_product_auto_name', AsyncMock())
    update = make_callback_update('pm:s:5104800')

    await bot.handle_callback_query(update, None)

    assert bot.profile_products['ggsel'] == 5104800
    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at
    update.callback_query.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_guard_button_opens_inline_panel():
    bot = make_bot()
    update = make_update(BTN_PRICE_GUARD)

    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    _args, kwargs = update.message.reply_text.await_args
    markup = kwargs['reply_markup']
    assert hasattr(markup, 'inline_keyboard')
    flat = [button.text for row in markup.inline_keyboard for button in row]
    assert BTN_MIN in flat
    assert BTN_MAX in flat
    assert BTN_UNDERCUT in flat
    assert BTN_RAISE in flat


@pytest.mark.asyncio
async def test_price_guard_button_without_active_pair_shows_error(monkeypatch):
    bot = make_bot()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [],
    )
    update = make_update(BTN_PRICE_GUARD)

    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Нет активной пары' in args[0]


@pytest.mark.asyncio
async def test_price_guard_button_clears_existing_pending_action():
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    update = make_update(BTN_PRICE_GUARD)

    await bot.handle_message(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at


@pytest.mark.asyncio
async def test_price_guard_rounding_callback_isolated_for_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    bot._tracked_product_ids = lambda _profile, runtime=None: [999]
    bot._runtime_for_product = lambda _profile, _product: SimpleNamespace(
        SHOWCASE_ROUND_STEP=0.01,
        REBOUND_TO_DESIRED_ON_MIN=False,
        MIN_PRICE=0.25,
        MAX_PRICE=0.40,
        UNDERCUT_VALUE=0.0051,
        RAISE_VALUE=0.0049,
    )
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
    update = make_callback_update('pc:round')

    await bot.handle_callback_query(update, None)

    assert captured['key'] == 'SHOWCASE_ROUND_STEP'
    assert captured['profile_id'] == 'ggsel:999'
    update.callback_query.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_guard_rounding_callback_clears_existing_pending_action(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 999
    bot._tracked_product_ids = lambda _profile, runtime=None: [999]
    bot._runtime_for_product = lambda _profile, _product: SimpleNamespace(
        SHOWCASE_ROUND_STEP=0.01,
        REBOUND_TO_DESIRED_ON_MIN=False,
        MIN_PRICE=0.25,
        MAX_PRICE=0.40,
        UNDERCUT_VALUE=0.0051,
        RAISE_VALUE=0.0049,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda *_args, **_kwargs: True,
    )
    update = make_callback_update('pc:round')

    await bot.handle_callback_query(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at


@pytest.mark.asyncio
async def test_price_guard_min_callback_without_active_pair_clears_pending(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 999
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [],
    )
    update = make_callback_update('pc:min')

    await bot.handle_callback_query(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_pending_product_rename_uses_plain_text(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('PRODUCT_RENAME', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 4697439
    bot.send_settings = AsyncMock()

    runtime_store = {}
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda key, value, user_id=None, source='system', profile_id='ggsel': (
            runtime_store.__setitem__((profile_id, key), value)
        ),
    )
    update = make_update('Новый тестовый товар')

    await bot.handle_pending_action(100, 1, 'Новый тестовый товар', update)

    assert runtime_store[('ggsel', 'PRODUCT_ALIAS:4697439')] == 'Новый тестовый товар'
    assert 100 not in bot.pending_actions
    bot.send_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_buttons_route_to_handlers():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}

    bot.send_status = AsyncMock()
    bot.set_auto_enabled = AsyncMock()
    bot.set_chat_autoreply_enabled = AsyncMock()
    bot.set_chat_autoreply_only_empty_chat = AsyncMock()
    bot.set_chat_autoreply_smart_non_empty = AsyncMock()
    bot.cycle_chat_autoreply_policy = AsyncMock()
    bot.start_chat_rules = AsyncMock()
    bot.open_price_guard_panel = AsyncMock()
    bot.send_settings = AsyncMock()

    status = make_update(BTN_STATUS)
    await bot.handle_message(status, None)
    bot.send_status.assert_awaited_once()

    auto = make_update(BTN_AUTO_ON)
    await bot.handle_message(auto, None)
    bot.set_auto_enabled.assert_any_await(auto, enabled=True)

    auto_off = make_update(BTN_AUTO_OFF)
    await bot.handle_message(auto_off, None)
    bot.set_auto_enabled.assert_any_await(auto_off, enabled=False)

    settings = make_update(BTN_SETTINGS)
    await bot.handle_message(settings, None)
    bot.send_settings.assert_awaited_once_with(100, settings)

    price_guard = make_update(BTN_PRICE_GUARD)
    await bot.handle_message(price_guard, None)
    bot.open_price_guard_panel.assert_awaited_once_with(100, price_guard)

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

    chat_empty_on = make_update(BTN_CHAT_EMPTY_ONLY_ON)
    await bot.handle_message(chat_empty_on, None)
    bot.set_chat_autoreply_only_empty_chat.assert_any_await(
        100, 1, chat_empty_on, enabled=True
    )

    chat_empty_off = make_update(BTN_CHAT_EMPTY_ONLY_OFF)
    await bot.handle_message(chat_empty_off, None)
    bot.set_chat_autoreply_only_empty_chat.assert_any_await(
        100, 1, chat_empty_off, enabled=False
    )

    chat_smart_on = make_update(BTN_CHAT_SMART_NON_EMPTY_ON)
    await bot.handle_message(chat_smart_on, None)
    bot.set_chat_autoreply_smart_non_empty.assert_any_await(
        100, 1, chat_smart_on, enabled=True
    )

    chat_smart_off = make_update(BTN_CHAT_SMART_NON_EMPTY_OFF)
    await bot.handle_message(chat_smart_off, None)
    bot.set_chat_autoreply_smart_non_empty.assert_any_await(
        100, 1, chat_smart_off, enabled=False
    )

    chat_policy = make_update(BTN_CHAT_POLICY)
    await bot.handle_message(chat_policy, None)
    bot.cycle_chat_autoreply_policy.assert_awaited_once_with(
        100, 1, chat_policy
    )

    chat_rules = make_update(BTN_CHAT_RULES)
    await bot.handle_message(chat_rules, None)
    bot.start_chat_rules.assert_awaited_once_with(100, chat_rules)


@pytest.mark.asyncio
@pytest.mark.parametrize('button', [BTN_STATUS, BTN_SETTINGS, BTN_PROFILE])
async def test_navigation_buttons_clear_existing_pending_action(button):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.send_status = AsyncMock()
    bot.send_settings = AsyncMock()
    update = make_update(button)

    await bot.handle_message(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at


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
async def test_settings_button_price_sets_pending_action():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot._runtime = lambda _profile: SimpleNamespace(
        FAST_CHECK_INTERVAL_MIN=20,
        FAST_CHECK_INTERVAL_MAX=60,
    )
    update = make_update(BTN_PRICE)

    await bot.handle_message(update, None)

    assert bot.pending_actions[100] == ('DESIRED_PRICE', 'ggsel')
    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('button', [BTN_PRODUCTS, BTN_PRODUCT_REMOVE])
async def test_product_buttons_open_inline_manager(button):
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot._runtime = lambda _profile: SimpleNamespace(
        FAST_CHECK_INTERVAL_MIN=20,
        FAST_CHECK_INTERVAL_MAX=60,
    )
    bot._runtime_for_product = lambda *_args, **_kwargs: make_runtime([])
    update = make_update(button)

    await bot.handle_message(update, None)

    update.message.reply_text.assert_awaited_once()
    _args, kwargs = update.message.reply_text.await_args
    assert hasattr(kwargs['reply_markup'], 'inline_keyboard')


@pytest.mark.asyncio
async def test_mode_and_product_buttons_call_toggles():
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.toggle_mode = AsyncMock()
    bot.switch_active_product = AsyncMock()

    mode = make_update(BTN_MODE)
    await bot.handle_message(mode, None)
    bot.toggle_mode.assert_awaited_once_with(100, 1, mode)

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
    assert captured[-1][1] == 'SHOWCASE_CYCLE'

    bot._runtime = lambda _profile: SimpleNamespace(MODE='SHOWCASE_CYCLE')
    await bot.toggle_mode(100, 1, update)
    assert captured[-1][1] == 'FOLLOW'

    bot._runtime = lambda _profile: SimpleNamespace(MODE='FOLLOW')
    await bot.toggle_mode(100, 1, update)
    assert captured[-1][1] == 'DUMPING'


def test_next_mode_for_digiseller_skips_showcase_cycle():
    bot = make_bot()
    assert bot._next_mode_for_profile('digiseller', 'DUMPING') == 'RAISE'
    assert bot._next_mode_for_profile('digiseller', 'RAISE') == 'FOLLOW'


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
    bot._tracked_product_ids = (
        lambda profile, runtime=None: [2] if profile == 'digiseller' else [1]
    )
    bot.send_settings = AsyncMock()
    update = make_update(BTN_AUTO_ON)

    calls = []

    def fake_set_auto_mode(
        enabled,
        *,
        profile_id='ggsel',
        user_id=None,
        source='system',
    ):
        calls.append((enabled, profile_id, user_id, source))

    monkeypatch.setattr(
        telegram_module.storage,
        'set_auto_mode',
        fake_set_auto_mode,
    )

    await bot.toggle_auto(update)

    assert calls == [(False, 'digiseller:2', 1, 'telegram')]
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '🔔 Автоцена (DIGISELLER / 2): ВЫКЛ'


@pytest.mark.asyncio
async def test_set_auto_enabled_true_marks_pair_enabled(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4697439
    bot._tracked_product_ids = lambda _profile, runtime=None: [4697439]
    bot._runtime_for_product = lambda _profile, _product: make_runtime(
        ['https://example.com/item']
    )
    bot.send_settings = AsyncMock()
    update = make_update(BTN_AUTO_OFF)

    auto_calls = []
    runtime_calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_auto_mode',
        lambda enabled, *, profile_id='ggsel', user_id=None, source='system': (
            auto_calls.append((enabled, profile_id, user_id, source))
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda key, value, user_id=None, source='system', profile_id='ggsel': (
            runtime_calls.append((key, value, user_id, source, profile_id))
        ),
    )

    await bot.set_auto_enabled(update, enabled=True)

    assert auto_calls == [(True, 'ggsel:4697439', 1, 'telegram')]
    assert ('PAIR_ENABLED', 'true', 1, 'telegram', 'ggsel:4697439') in runtime_calls


@pytest.mark.asyncio
async def test_set_auto_enabled_rejects_when_active_pair_missing(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 0
    bot._tracked_product_ids = lambda _profile, runtime=None: []
    bot.send_settings = AsyncMock()

    calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_auto_mode',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    update = make_update(BTN_AUTO_ON)

    await bot.set_auto_enabled(update, enabled=True)

    assert calls == []
    bot.send_settings.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Нет активной пары' in args[0]


@pytest.mark.asyncio
async def test_set_auto_enabled_rejects_when_competitor_url_missing(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4697439
    bot._tracked_product_ids = lambda _profile, runtime=None: [4697439]
    bot._runtime_for_product = lambda _profile, _product: SimpleNamespace(
        COMPETITOR_URLS=[],
    )
    bot.send_settings = AsyncMock()
    calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_auto_mode',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    update = make_update(BTN_AUTO_ON)

    await bot.set_auto_enabled(update, enabled=True)

    assert calls == []
    bot.send_settings.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'не задан URL конкурента' in args[0]


@pytest.mark.asyncio
async def test_pending_price_value_not_applied_without_active_pair(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 0
    bot._tracked_product_ids = lambda _profile, runtime=None: []

    calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    update = make_update('0.25')

    await bot.handle_pending_action(100, 1, '0.25', update)

    assert calls == []
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Нет активной пары' in args[0]


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
async def test_set_chat_autoreply_only_empty_chat_updates_runtime_setting(
    monkeypatch,
):
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
    update = make_update(BTN_CHAT_EMPTY_ONLY_ON)

    await bot.set_chat_autoreply_only_empty_chat(100, 1, update, enabled=True)

    assert captured == {
        'key': 'CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
        'value': 'true',
        'user_id': 1,
        'source': 'telegram',
        'profile_id': 'ggsel',
    }
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '📭 Отправка только в пустой чат: ВКЛ'


@pytest.mark.asyncio
async def test_chat_rules_button_opens_editor(monkeypatch):
    class ProductWithOptionsClient(ChatCapableClient):
        def get_product_info(self, _product_id, timeout=10, lang=None):
            return {
                'options': [
                    {
                        'name': 'Наши аккаунты в друзьях',
                        'variants': [
                            {'id': 1, 'text': 'Нет. Добавлю после оплаты.'},
                            {'id': 2, 'text': 'Да. Проверил(а), в друзьях'},
                        ],
                    }
                ]
            }

    bot = TelegramBot(
        api_clients={'ggsel': ProductWithOptionsClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'ggsel'
    store = {}
    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        lambda key, profile_id='ggsel', **_kwargs: store.get(
            (profile_id, key)
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda key, value, user_id=None, source='system', profile_id='ggsel': (
            store.__setitem__((profile_id, key), value)
        ),
    )
    update = make_update(BTN_CHAT_RULES)

    await bot.handle_message(update, None)

    assert bot.pending_actions[100] == ('CHAT_RULES', 'ggsel')
    assert bot.chat_rules_context[100]['product_id'] == 1
    assert len(bot.chat_rules_context[100]['items']) == 2
    assert update.message.reply_text.await_count == 2
    first_args, _first_kwargs = update.message.reply_text.await_args_list[0]
    second_args, _second_kwargs = update.message.reply_text.await_args_list[1]
    assert '📝 Правила авто-инструкций' in first_args[0]
    assert 'Включение/выключение теперь кнопками' in second_args[0]


def test_chat_rules_rebinds_legacy_text_key_to_id_key():
    bot = make_bot()
    items = [
        {
            'key': 'id:32496:152937',
            'legacy_key': chat_keys.option_rule_key(
                'Наши аккаунты в друзьях?',
                'Нет. Добавлю после оплаты',
            ),
            'option': 'Наши аккаунты в друзьях?',
            'value': 'Нет. Добавлю после оплаты',
            'label': 'Наши аккаунты в друзьях? -> Нет. Добавлю после оплаты',
        }
    ]
    rules = {
        items[0]['legacy_key']: {
            'enabled': True,
            'text': 'legacy text',
        }
    }

    migrated, changed = bot._chat_rules_rebind_legacy_keys(
        rules=rules,
        items=items,
    )

    assert changed is True
    assert items[0]['legacy_key'] not in migrated
    assert migrated['id:32496:152937']['enabled'] is True
    assert migrated['id:32496:152937']['text'] == 'legacy text'


@pytest.mark.asyncio
async def test_chat_rules_pending_commands_save_rule(monkeypatch):
    class ProductWithOptionsClient(ChatCapableClient):
        def get_product_info(self, _product_id, timeout=10, lang=None):
            return {
                'options': [
                    {
                        'name': 'Наши аккаунты в друзьях',
                        'variants': [
                            {'id': 1, 'text': 'Нет. Добавлю после оплаты.'},
                        ],
                    }
                ]
            }

    bot = TelegramBot(
        api_clients={'ggsel': ProductWithOptionsClient()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    bot.chat_profile[100] = 'ggsel'
    store = {}
    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        lambda key, profile_id='ggsel', **_kwargs: store.get(
            (profile_id, key)
        ),
    )

    def fake_set_runtime_setting(
        key,
        value,
        user_id=None,
        source='system',
        profile_id='ggsel',
    ):
        store[(profile_id, key)] = value

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    await bot.handle_message(make_update(BTN_CHAT_RULES), None)
    await bot.handle_message(make_update('text 1 Тестовая инструкция'), None)

    payload = store[('ggsel', chat_keys.rules_key(1))]
    data = json.loads(payload)
    assert data['rules']
    only_key = next(iter(data['rules']))
    assert data['rules'][only_key]['enabled'] is True
    assert data['rules'][only_key]['text'] == 'Тестовая инструкция'


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
    assert '🎯 Цена по стратегии: 0.2649₽' in args[0]


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
            'CHAT_AUTOREPLY_POLICY:5077639': 'CODE_ONLY',
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
    assert '🧭 Режим отправки: Только при коде' in args[0]
    assert '📨 Отправлено: 7' in args[0]
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
        bot,
        '_chat_autoreply_supported',
        lambda _profile: True,
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
    assert '📨 Отправлено: 4' in args[0]


@pytest.mark.asyncio
async def test_status_ggsel_keeps_strategy_price_when_api_differs():
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
    assert '💰 Моя цена: 0.2649₽' in args[0]
    assert '🎯 Цена по стратегии: 0.2649₽' in args[0]
    assert '📡 API (округл.)' not in args[0]


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
    assert '💰 Моя цена: 0.2649₽' in args[0]
    assert '📡 API (округл.)' not in args[0]


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
    assert '🎯 Цена по стратегии: 0.2649₽' in args[0]


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
    bot._tracked_product_ids = lambda _profile, runtime=None: [999]
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
async def test_cycle_chat_policy_realigns_stale_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': ['https://example.com'], 'enabled': True},
        ],
    )
    monkeypatch.setattr(
        telegram_module.config,
        'GGSEL_CHAT_AUTOREPLY_ENABLED',
        True,
    )
    monkeypatch.setattr(
        bot,
        '_chat_autoreply_supported',
        lambda _profile: True,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        lambda *_args, **_kwargs: None,
    )
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
    update = make_update(BTN_CHAT_POLICY)

    await bot.cycle_chat_autoreply_policy(100, 1, update)

    assert bot.profile_products['ggsel'] == 4697439
    assert captured['key'] == 'CHAT_AUTOREPLY_POLICY:4697439'
    assert captured['profile_id'] == 'ggsel'
    bot.send_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_chat_rules_realigns_stale_active_product(monkeypatch):
    class FakeClient:
        def get_product_info(self, _product_id, timeout=10, lang=None):
            return {
                'options': [
                    {
                        'name': 'Наши аккаунты в друзьях?',
                        'variants': [
                            {'text': 'Нет. Добавлю после оплаты'},
                            {'text': 'Да. Проверил(а), в друзьях'},
                        ],
                    }
                ]
            }

    bot = TelegramBot(
        api_clients={'ggsel': FakeClient()},
        profile_products={'ggsel': 999},
        profile_default_urls={'ggsel': ['https://example.com']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': ['https://example.com'], 'enabled': True},
        ],
    )
    monkeypatch.setattr(
        bot,
        '_chat_autoreply_supported',
        lambda _profile: True,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        lambda *_args, **_kwargs: None,
    )
    update = make_update(BTN_CHAT_RULES)

    await bot.start_chat_rules(100, update)

    assert bot.profile_products['ggsel'] == 4697439
    assert bot.chat_rules_context[100]['product_id'] == 4697439
    assert bot.pending_actions[100] == ('CHAT_RULES', 'ggsel')
    assert update.message.reply_text.await_count >= 1


@pytest.mark.asyncio
async def test_pending_price_action_isolated_for_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 999, 'competitor_urls': [], 'enabled': True},
        ],
    )
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
async def test_pending_price_action_realigns_stale_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 999
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    observed = {'runtime_product_id': None}

    def fake_runtime_for_product(_profile, product_id):
        observed['runtime_product_id'] = product_id
        return SimpleNamespace(
            MIN_PRICE=0.2,
            MAX_PRICE=1.0,
            FAST_CHECK_INTERVAL_MIN=20,
            FAST_CHECK_INTERVAL_MAX=60,
        )

    monkeypatch.setattr(bot, '_runtime_for_product', fake_runtime_for_product)
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

    assert observed['runtime_product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 4697439
    assert captured['key'] == 'MIN_PRICE'
    assert captured['profile_id'] == 'ggsel:4697439'


@pytest.mark.asyncio
async def test_pending_manage_products_add(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MANAGE_PRODUCTS', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda _profile_id, runtime=None: [],
    )

    captured = {}
    captured_runtime_urls = {}
    captured_auto_mode = {}
    captured_mode = {}

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
        'set_competitor_urls',
        lambda urls, user_id=None, source='system', profile_id='ggsel': (
            captured_runtime_urls.update(
                {
                    'urls': list(urls),
                    'user_id': user_id,
                    'source': source,
                    'profile_id': profile_id,
                }
            )
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_auto_mode',
        lambda enabled, profile_id='ggsel', user_id=None, source='system': (
            captured_auto_mode.update(
                {
                    'enabled': enabled,
                    'profile_id': profile_id,
                    'user_id': user_id,
                    'source': source,
                }
            )
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda key, value, user_id=None, source='system', profile_id='ggsel': (
            captured_mode.update(
                {
                    'key': key,
                    'value': value,
                    'user_id': user_id,
                    'source': source,
                    'profile_id': profile_id,
                }
            )
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'get_last_setting_change',
        lambda key, profile_id='ggsel': None,
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

    assert captured == {}
    assert bot.pending_actions.get(100) == ('MANAGE_PRODUCTS', 'ggsel')
    assert bot.manage_products_context.get(100) == {
        'profile_id': 'ggsel',
        'product_id': 4697439,
        'set_at': bot.manage_products_context[100]['set_at'],
    }
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Подтверди добавление/выбор товара' in args[0]

    update.message.reply_text.reset_mock()

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
    assert captured_runtime_urls == {
        'urls': [],
        'user_id': 1,
        'source': 'telegram',
        'profile_id': 'ggsel:4697439',
    }
    assert captured_auto_mode == {
        'enabled': False,
        'profile_id': 'ggsel:4697439',
        'user_id': 1,
        'source': 'telegram_add_product',
    }
    assert captured_mode == {
        'key': 'MODE',
        'value': 'FOLLOW',
        'user_id': 1,
        'source': 'telegram_add_product',
        'profile_id': 'ggsel:4697439',
    }
    assert 100 not in bot.pending_actions
    assert 100 not in bot.manage_products_context
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Товар 4697439 добавлен' in args[0]


@pytest.mark.asyncio
async def test_pending_manage_products_add_inline_pair(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MANAGE_PRODUCTS', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.send_settings = AsyncMock()
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda _profile_id, runtime=None: [],
    )

    captured = {}
    captured_runtime_urls = {}
    captured_auto_mode = {}
    captured_mode = {}

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
        'set_competitor_urls',
        lambda urls, user_id=None, source='system', profile_id='ggsel': (
            captured_runtime_urls.update(
                {
                    'urls': list(urls),
                    'user_id': user_id,
                    'source': source,
                    'profile_id': profile_id,
                }
            )
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_auto_mode',
        lambda enabled, profile_id='ggsel', user_id=None, source='system': (
            captured_auto_mode.update(
                {
                    'enabled': enabled,
                    'profile_id': profile_id,
                    'user_id': user_id,
                    'source': source,
                }
            )
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda key, value, user_id=None, source='system', profile_id='ggsel': (
            captured_mode.update(
                {
                    'key': key,
                    'value': value,
                    'user_id': user_id,
                    'source': source,
                    'profile_id': profile_id,
                }
            )
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'get_last_setting_change',
        lambda key, profile_id='ggsel': None,
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
    assert captured_runtime_urls == {
        'urls': ['https://a.example/item'],
        'user_id': 1,
        'source': 'telegram',
        'profile_id': 'ggsel:4697439',
    }
    assert captured_auto_mode == {
        'enabled': False,
        'profile_id': 'ggsel:4697439',
        'user_id': 1,
        'source': 'telegram_add_product',
    }
    assert captured_mode == {
        'key': 'MODE',
        'value': 'FOLLOW',
        'user_id': 1,
        'source': 'telegram_add_product',
        'profile_id': 'ggsel:4697439',
    }
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Пара(ы) добавлены: 1' in args[0]


@pytest.mark.asyncio
async def test_pending_manage_products_set_alias_for_active_product(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('MANAGE_PRODUCTS', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 4697439
    bot.send_settings = AsyncMock()

    runtime_store = {}

    monkeypatch.setattr(
        telegram_module.storage,
        'set_runtime_setting',
        lambda key, value, user_id=None, source='system', profile_id='ggsel': (
            runtime_store.__setitem__((profile_id, key), value)
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'get_runtime_setting',
        lambda key, profile_id='ggsel', inherit_parent=True, default=None: (
            runtime_store.get((profile_id, key), default)
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'delete_runtime_setting',
        lambda key, user_id=None, source='system', profile_id='ggsel': (
            runtime_store.pop((profile_id, key), None) is not None
        ),
    )
    update = make_update('name active Тестовый товар')

    await bot.handle_pending_action(100, 1, 'name active Тестовый товар', update)

    assert runtime_store.get(
        ('ggsel', 'PRODUCT_ALIAS:4697439')
    ) == 'Тестовый товар'
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'Имя товара сохранено' in args[0]
    bot.send_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_pending_remove_product_success_switches_active(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('REMOVE_PRODUCT', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 4697439
    bot.send_settings = AsyncMock()
    bot._runtime_for_product = lambda _profile, _product: make_runtime([])

    state = {'removed': False}

    def fake_tracked_ids(_profile, runtime=None):
        return [4697439, 5104800] if not state['removed'] else [5104800]

    bot._tracked_product_ids = fake_tracked_ids

    captured = {}
    cleanup_calls = []
    purge_calls = []

    def fake_remove_tracked_product(*, profile_id='ggsel', product_id=0):
        captured['profile_id'] = profile_id
        captured['product_id'] = product_id
        state['removed'] = True
        return True

    monkeypatch.setattr(
        telegram_module.storage,
        'remove_tracked_product',
        fake_remove_tracked_product,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'delete_runtime_setting',
        lambda key, user_id=None, source='system', profile_id='ggsel': (
            cleanup_calls.append(
                {
                    'key': key,
                    'user_id': user_id,
                    'source': source,
                    'profile_id': profile_id,
                }
            )
            or True
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'purge_product_runtime_data',
        lambda profile_id='ggsel', product_id=0: (
            purge_calls.append(
                {
                    'profile_id': profile_id,
                    'product_id': product_id,
                }
            )
            or {}
        ),
    )
    update = make_update('active')

    await bot.handle_pending_action(100, 1, 'active', update)

    assert captured == {'profile_id': 'ggsel', 'product_id': 4697439}
    cleanup_keys = [item['key'] for item in cleanup_calls]
    assert 'PRODUCT_ALIAS:4697439' in cleanup_keys
    assert 'PRODUCT_AUTO_NAME:4697439' in cleanup_keys
    assert purge_calls == []
    assert bot.profile_products['ggsel'] == 5104800
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '✅ Товар удалён: 4697439'


@pytest.mark.asyncio
async def test_pending_remove_product_active_realigns_stale_active_product(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('REMOVE_PRODUCT', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 999
    bot.send_settings = AsyncMock()

    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    remove_calls = []

    state = {'removed': False}

    def fake_tracked_ids(_profile, runtime=None):
        return [] if state['removed'] else [4697439]

    def fake_remove_product_with_cleanup_stateful(**kwargs):
        remove_calls.append(kwargs)
        state['removed'] = True
        return True

    monkeypatch.setattr(
        bot,
        '_remove_product_with_cleanup',
        fake_remove_product_with_cleanup_stateful,
    )
    monkeypatch.setattr(
        bot,
        '_tracked_product_ids',
        fake_tracked_ids,
    )
    update = make_update('active')

    await bot.handle_pending_action(100, 1, 'active', update)

    assert remove_calls
    assert remove_calls[0]['product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 0
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '✅ Товар удалён: 4697439'


def test_tracked_products_realigns_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4682996
    runtime = make_runtime(['https://example.com/item'])
    monkeypatch.setattr(
        telegram_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': 4697439,
                'competitor_urls': ['https://example.com/item'],
                'enabled': True,
            }
        ],
    )

    tracked = bot._tracked_products('ggsel', runtime=runtime)

    assert tracked[0]['product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 4697439


def test_tracked_products_resets_active_product_when_empty(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4682996
    runtime = make_runtime([])
    monkeypatch.setattr(
        telegram_module.storage,
        'list_tracked_products',
        lambda **kwargs: [],
    )

    tracked = bot._tracked_products('ggsel', runtime=runtime)

    assert tracked == []
    assert bot.profile_products['ggsel'] == 0


def test_settings_keyboard_uses_realigned_product_for_state_lookup(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4682996
    runtime = make_runtime(['https://example.com/item'])
    monkeypatch.setattr(
        telegram_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': 4697439,
                'competitor_urls': ['https://example.com/item'],
                'enabled': True,
            }
        ],
    )
    bot._runtime = lambda _profile: runtime
    captured = {'product_id': None}

    def fake_state_for_product(_profile, product_id):
        captured['product_id'] = product_id
        return {'auto_mode': False}

    bot._state_for_product = fake_state_for_product

    markup = bot.get_settings_keyboard('ggsel')

    assert captured['product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 4697439
    assert BTN_AUTO_ON in keyboard_texts(markup)


def test_format_price_guard_text_uses_realigned_active_product(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4682996
    runtime_parent = make_runtime(['https://example.com/item'])
    monkeypatch.setattr(
        telegram_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': 4697439,
                'competitor_urls': ['https://example.com/item'],
                'enabled': True,
            }
        ],
    )
    bot._runtime = lambda _profile: runtime_parent
    observed = {'product_id': None}

    def fake_runtime_for_product(_profile, product_id):
        observed['product_id'] = product_id
        return SimpleNamespace(
            MIN_PRICE=0.25,
            MAX_PRICE=0.40,
            UNDERCUT_VALUE=0.0051,
            RAISE_VALUE=0.0049,
            SHOWCASE_ROUND_STEP=0.01,
            REBOUND_TO_DESIRED_ON_MIN=False,
        )

    bot._runtime_for_product = fake_runtime_for_product

    text = bot._format_price_guard_text('ggsel')

    assert observed['product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 4697439
    assert 'Товар: 4697439' in text


@pytest.mark.asyncio
async def test_status_uses_realigned_product_for_state_lookup(monkeypatch):
    bot = make_bot()
    bot.profile_products['ggsel'] = 4682996
    runtime = make_runtime(['https://example.com/item'])
    monkeypatch.setattr(
        telegram_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': 4697439,
                'competitor_urls': ['https://example.com/item'],
                'enabled': True,
            }
        ],
    )
    bot._runtime = lambda _profile: runtime
    bot._runtime_for_product = lambda _profile, _product_id: runtime
    bot._product_runtime_source = lambda _profile, _product_id: 'товарные'
    bot._is_pair_enabled = lambda _profile, _product_id: True
    bot._chat_autoreply_meta = lambda _profile: None
    captured = {'product_id': None}

    def fake_state_for_product(_profile, product_id):
        captured['product_id'] = product_id
        return {
            'last_target_price': 0.3449,
            'last_price': 0.3449,
            'last_competitor_min': 0.35,
            'last_update': None,
            'last_competitor_rank': None,
            'last_competitor_parse_at': None,
            'last_competitor_url': 'https://example.com/item',
            'last_competitor_method': 'api4_goods',
            'auto_mode': True,
            'update_count': 0,
            'skip_count': 0,
        }

    bot._state_for_product = fake_state_for_product
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    assert captured['product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 4697439
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '4697439' in args[0]


@pytest.mark.asyncio
async def test_cmd_smoke_uses_realigned_active_product(monkeypatch):
    class FakeClient:
        pass

    bot = TelegramBot(
        api_clients={'ggsel': FakeClient()},
        profile_products={'ggsel': 4682996},
        profile_default_urls={'ggsel': ['https://example.com/item']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    monkeypatch.setattr(bot, '_runtime', lambda _profile: make_runtime([]))
    captured = {}

    def fake_run_profile_smoke(client, product_id, mutate=False, verify_read=True, write_probe=False):
        captured['product_id'] = product_id
        return SimpleNamespace(
            api_access=True,
            product_read_ok=True,
            write_probe_ok=False,
            current_price=0.33,
            probe_price=None,
            verify_price=0.33,
            token_perms_ok=None,
            token_perms_desc=None,
            token_refresh_ok=None,
            token_refresh_desc=None,
            error=None,
        )

    monkeypatch.setattr(telegram_module, 'run_profile_smoke', fake_run_profile_smoke)
    update = make_update('/smoke')
    context = SimpleNamespace(args=[])

    await bot.cmd_smoke(update, context)

    assert captured['product_id'] == 4697439
    assert bot.profile_products['ggsel'] == 4697439
    assert update.message.reply_text.await_count == 2


@pytest.mark.asyncio
async def test_pending_remove_product_allows_last_product(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('REMOVE_PRODUCT', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 4697439
    bot.send_settings = AsyncMock()
    bot._runtime_for_product = lambda _profile, _product: make_runtime([])
    removal_state = {'done': False}

    def fake_tracked_ids(_profile, runtime=None):
        return [] if removal_state['done'] else [4697439]

    bot._tracked_product_ids = fake_tracked_ids

    remove_calls = []
    cleanup_calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'remove_tracked_product',
        lambda **kwargs: (
            remove_calls.append(kwargs)
            or removal_state.update({'done': True})
            or True
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'delete_runtime_setting',
        lambda key, user_id=None, source='system', profile_id='ggsel': (
            cleanup_calls.append((key, profile_id)) or True
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'purge_product_runtime_data',
        lambda profile_id='ggsel', product_id=0: {},
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'clear_tracked_products',
        lambda profile_id='ggsel': [],
    )
    update = make_update('4697439')

    await bot.handle_pending_action(100, 1, '4697439', update)

    assert remove_calls == [{'profile_id': 'ggsel', 'product_id': 4697439}]
    assert 100 not in bot.pending_actions
    assert bot.profile_products['ggsel'] == 0
    assert ('PRODUCT_ALIAS:4697439', 'ggsel') in cleanup_calls
    assert ('PRODUCT_AUTO_NAME:4697439', 'ggsel') in cleanup_calls
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '✅ Товар удалён: 4697439'


@pytest.mark.asyncio
async def test_pending_remove_product_all_keyword_clears_all(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('REMOVE_PRODUCT', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 4697439
    bot._runtime_for_product = lambda _profile, _product: make_runtime([])
    removal_state = {'done': False}

    def fake_tracked_ids(_profile, runtime=None):
        return [] if removal_state['done'] else [4697439, 5104800]

    bot._tracked_product_ids = fake_tracked_ids
    bot.send_settings = AsyncMock()

    monkeypatch.setattr(
        telegram_module.storage,
        'clear_tracked_products',
        lambda profile_id='ggsel': (
            removal_state.update({'done': True}) or [4697439, 5104800]
        ),
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'delete_runtime_setting',
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        telegram_module.storage,
        'purge_product_runtime_data',
        lambda **_kwargs: {},
    )
    update = make_update('all')

    await bot.handle_pending_action(100, 1, 'all', update)

    assert bot.profile_products['ggsel'] == 0
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '✅ Все товары удалены' in args[0]
    bot.send_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_pending_remove_product_unknown_id(monkeypatch):
    bot = make_bot()
    bot.pending_actions[100] = ('REMOVE_PRODUCT', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic()
    bot.profile_products['ggsel'] = 4697439
    bot._runtime_for_product = lambda _profile, _product: make_runtime([])
    bot._tracked_product_ids = lambda _profile, runtime=None: [4697439, 5104800]

    remove_calls = []
    monkeypatch.setattr(
        telegram_module.storage,
        'remove_tracked_product',
        lambda **kwargs: remove_calls.append(kwargs),
    )
    update = make_update('7777777')

    await bot.handle_pending_action(100, 1, '7777777', update)

    assert remove_calls == []
    assert bot.pending_actions.get(100) == ('REMOVE_PRODUCT', 'ggsel')
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert args[0] == '❌ Такого товара нет в списке профиля'


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
    bot.pending_action_started_at[100] = time.monotonic()
    bot.chat_profile[100] = 'digiseller'
    update = make_update('0.25')

    await bot.handle_pending_action(100, 1, '0.25', update)

    assert called['value'] is False
    assert 100 not in bot.pending_actions
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'активный профиль был изменён' in args[0]


@pytest.mark.asyncio
async def test_pending_action_expires_and_is_cleared(monkeypatch):
    bot = make_bot()
    bot._state = lambda _profile: {'auto_mode': True}
    bot.pending_actions[100] = ('MIN_PRICE', 'ggsel')
    bot.pending_action_started_at[100] = time.monotonic() - 1000
    bot.handle_pending_action = AsyncMock()
    update = make_update('0.25')

    await bot.handle_message(update, None)

    assert 100 not in bot.pending_actions
    assert 100 not in bot.pending_action_started_at
    bot.handle_pending_action.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert 'ввод устарел' in args[0].lower()


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


def test_settings_keyboard_shows_auto_on_when_no_active_pair():
    bot = make_bot()
    bot._runtime = lambda _profile: make_runtime(competitor_urls=[])
    bot._state_for_product = lambda _profile, _product_id: {'auto_mode': True}
    bot._has_active_product_pair = lambda _profile, runtime=None: False

    markup = bot.get_settings_keyboard('ggsel')

    assert BTN_AUTO_ON in keyboard_texts(markup)
    assert BTN_AUTO_OFF not in keyboard_texts(markup)


@pytest.mark.asyncio
async def test_status_shows_auto_off_when_no_active_pair():
    bot = make_bot()
    bot._state_for_product = lambda _profile, _product_id: {
        'last_target_price': None,
        'last_price': None,
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
    bot._runtime_for_product = lambda _profile, _product_id: make_runtime(
        competitor_urls=[]
    )
    bot._product_runtime_source = lambda _profile, _product_id: 'товарные'
    bot._is_pair_enabled = lambda _profile, _product_id: False
    bot._format_tracked_products = lambda _profile, runtime=None: ['нет']
    bot._active_product_slot = lambda _profile, runtime=None: (0, 0)
    bot._chat_autoreply_meta = lambda _profile: None
    bot._has_active_product_pair = lambda _profile, runtime=None: False
    update = make_update(BTN_STATUS)

    await bot.send_status(100, update)

    update.message.reply_text.assert_awaited_once()
    args, _kwargs = update.message.reply_text.await_args
    assert '🔔 Авто: ВЫКЛ' in args[0]
    assert '🛡️ Пара активна: —' in args[0]


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
async def test_diagnostics_realigns_stale_active_product(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 999},
        profile_default_urls={'ggsel': ['https://example.com/gg']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [
            {'product_id': 4697439, 'competitor_urls': [], 'enabled': True},
        ],
    )
    observed = {'product_id': None}

    def fake_state_for_product(_profile, product_id):
        observed['product_id'] = product_id
        return {
            'auto_mode': True,
            'last_cycle': None,
            'last_competitor_error': None,
            'last_competitor_block_reason': None,
        }

    monkeypatch.setattr(bot, '_state_for_product', fake_state_for_product)
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: make_runtime(['https://example.com/gg']),
    )
    monkeypatch.setattr(bot, '_api_client', lambda _profile: None)
    update = make_update('/diag')

    await bot.send_diagnostics(100, update)

    assert observed['product_id'] == 4697439
    update.message.reply_text.assert_awaited_once()


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
async def test_cmd_smoke_fails_when_profile_not_configured(monkeypatch):
    bot = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 0},
        profile_default_urls={'ggsel': []},
        profile_labels={'ggsel': 'GGSEL'},
    )
    bot.admin_ids = {1}
    monkeypatch.setattr(
        bot,
        '_tracked_products',
        lambda *_args, **_kwargs: [],
    )
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
