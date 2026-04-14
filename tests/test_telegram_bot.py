import logging
from types import SimpleNamespace

import pytest
from telegram import ReplyKeyboardMarkup
from telegram.error import TimedOut

from src.telegram_bot import (
    BTN_AUTO_OFF,
    BTN_AUTO_ON,
    BTN_BACK,
    BTN_CHAT_RULES,
    BTN_MODE,
    BTN_PRODUCT_NEXT,
    BTN_PRODUCT_PREV,
    BTN_PRODUCT_REMOVE,
    BTN_PRICE,
    BTN_PRODUCTS,
    BTN_SETTINGS,
    BTN_STATUS,
    TelegramBot,
)


class DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies = []

    async def reply_text(self, text: str, reply_markup=None):
        self.replies.append((text, reply_markup))


class DummyUser:
    def __init__(self, user_id: int):
        self.id = user_id


class DummyChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class DummyUpdate:
    def __init__(self, text: str, user_id: int = 1, chat_id: int = 101):
        self.effective_user = DummyUser(user_id)
        self.effective_chat = DummyChat(chat_id)
        self.message = DummyMessage(text)


@pytest.fixture
def bot():
    b = TelegramBot(
        api_clients={'ggsel': object()},
        profile_products={'ggsel': 1},
        profile_default_urls={'ggsel': ['https://example.com/item']},
        profile_labels={'ggsel': 'GGSEL'},
    )
    b.admin_ids = {1}
    b._state = lambda _profile: {'auto_mode': True}
    return b


@pytest.mark.asyncio
async def test_keyboards_are_reply(bot):
    assert isinstance(bot.get_main_keyboard('ggsel'), ReplyKeyboardMarkup)
    assert isinstance(bot.get_settings_keyboard(), ReplyKeyboardMarkup)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('button', 'method_name'),
    [
        (BTN_STATUS, 'send_status'),
        (BTN_SETTINGS, 'send_settings'),
        (BTN_MODE, 'toggle_mode'),
        (BTN_CHAT_RULES, 'start_chat_rules'),
    ],
)
async def test_buttons_dispatch_to_methods(bot, monkeypatch, button, method_name):
    called = {}

    async def _stub(*_args, **_kwargs):
        called['ok'] = True

    monkeypatch.setattr(bot, method_name, _stub)
    upd = DummyUpdate(button)
    await bot.handle_message(upd, None)
    assert called.get('ok') is True


@pytest.mark.asyncio
@pytest.mark.parametrize('button', [BTN_AUTO_ON, BTN_AUTO_OFF])
async def test_auto_buttons_dispatch_toggle(bot, monkeypatch, button):
    called = []

    async def _stub(_update, *, enabled):
        called.append(enabled)

    monkeypatch.setattr(bot, 'set_auto_enabled', _stub)
    await bot.handle_message(DummyUpdate(button), None)
    expected = button == BTN_AUTO_ON
    assert called == [expected]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('button', 'step'),
    [
        (BTN_PRODUCT_PREV, -1),
        (BTN_PRODUCT_NEXT, 1),
    ],
)
async def test_product_switch_buttons_dispatch(bot, monkeypatch, button, step):
    called = []

    async def _stub(chat_id, update, *, step):
        assert chat_id == 101
        called.append(step)

    monkeypatch.setattr(bot, 'switch_active_product', _stub)
    await bot.handle_message(DummyUpdate(button), None)
    assert called == [step]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('button', 'expected_action'),
    [
        (BTN_PRICE, 'DESIRED_PRICE'),
        (BTN_PRODUCTS, 'MANAGE_PRODUCTS'),
        (BTN_PRODUCT_REMOVE, 'REMOVE_PRODUCT'),
    ],
)
async def test_buttons_set_pending_actions(bot, button, expected_action):
    upd = DummyUpdate(button, chat_id=555)
    await bot.handle_message(upd, None)
    assert bot.pending_actions[555] == (expected_action, 'ggsel')
    assert upd.message.replies
    assert isinstance(upd.message.replies[-1][1], ReplyKeyboardMarkup)


@pytest.mark.asyncio
async def test_back_clears_pending(bot):
    upd = DummyUpdate(BTN_BACK, chat_id=777)
    bot.pending_actions[777] = ('MIN_PRICE', 'ggsel')
    await bot.handle_message(upd, None)
    assert 777 not in bot.pending_actions
    assert upd.message.replies


@pytest.mark.asyncio
async def test_unknown_message_shows_hint(bot):
    upd = DummyUpdate('неизвестная команда')
    await bot.handle_message(upd, None)
    assert upd.message.replies
    assert 'Используй кнопки' in upd.message.replies[-1][0]


@pytest.mark.asyncio
async def test_access_denied(bot):
    upd = DummyUpdate(BTN_STATUS, user_id=999)
    await bot.handle_message(upd, None)
    assert upd.message.replies
    assert 'Нет доступа' in upd.message.replies[-1][0]


@pytest.mark.asyncio
async def test_handle_app_error_timeout_logs_warning(bot, caplog):
    caplog.set_level(logging.WARNING)
    context = type('Ctx', (), {'error': TimedOut('connect timeout')})()

    await bot.handle_app_error(None, context)

    assert any('Telegram timeout' in r.message for r in caplog.records)
    assert not any(r.levelname == 'ERROR' for r in caplog.records)


@pytest.mark.asyncio
async def test_handle_app_error_unknown_logs_error(bot, caplog):
    caplog.set_level(logging.ERROR)
    context = type('Ctx', (), {'error': ValueError('boom')})()

    await bot.handle_app_error(None, context)

    assert any('Unhandled telegram exception' in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_send_settings_hides_legacy_price_limits(bot, monkeypatch):
    monkeypatch.setattr(bot, '_active_profile', lambda _chat_id: 'ggsel')
    monkeypatch.setattr(bot, '_product_id', lambda _profile_id: 4697439)
    monkeypatch.setattr(bot, '_state_for_product', lambda *_args, **_kwargs: {
        'auto_mode': True,
    })
    monkeypatch.setattr(
        bot,
        '_runtime_for_product',
        lambda *_args, **_kwargs: SimpleNamespace(
            COMPETITOR_URLS=['https://example.com/competitor'],
            MODE='DUMPING',
            CHECK_INTERVAL=30,
            UPDATE_ONLY_ON_COMPETITOR_CHANGE=True,
        ),
    )
    monkeypatch.setattr(
        bot,
        '_format_tracked_products',
        lambda *_args, **_kwargs: ['4697439 (основной, активный): 1 URL'],
    )
    monkeypatch.setattr(
        bot,
        '_format_tracking_pairs',
        lambda *_args, **_kwargs: ['4697439 ↔ https://example.com/competitor'],
    )
    monkeypatch.setattr(
        bot,
        '_active_product_slot',
        lambda *_args, **_kwargs: (1, 1),
    )

    upd = DummyUpdate(BTN_SETTINGS)
    await bot.send_settings(101, upd)

    assert upd.message.replies
    text = upd.message.replies[-1][0]
    assert 'MIN:' not in text
    assert 'MAX:' not in text
    assert 'Желаемая' not in text
    assert 'Шаг:' not in text
