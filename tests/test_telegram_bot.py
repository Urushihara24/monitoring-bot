import pytest
from telegram import ReplyKeyboardMarkup

from src.telegram_bot import (
    TelegramBot,
    BTN_STATUS,
    BTN_UP,
    BTN_DOWN,
    BTN_AUTO_ON,
    BTN_AUTO_OFF,
    BTN_SETTINGS,
    BTN_DIAGNOSTICS,
    BTN_PRICE,
    BTN_STEP,
    BTN_MIN,
    BTN_MAX,
    BTN_MODE,
    BTN_POSITION,
    BTN_ADD_URL,
    BTN_REMOVE_URL,
    BTN_EXPORT,
    BTN_IMPORT,
    BTN_HISTORY,
    BTN_BACK,
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
    b = TelegramBot(api_client=None)
    b.admin_ids = [1]
    b.auto_mode = True
    return b


@pytest.mark.asyncio
async def test_keyboards_are_reply(bot):
    assert isinstance(bot.get_main_keyboard(), ReplyKeyboardMarkup)
    assert isinstance(bot.get_settings_keyboard(), ReplyKeyboardMarkup)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('button', 'method_name'),
    [
        (BTN_STATUS, 'send_status'),
        (BTN_SETTINGS, 'send_settings'),
        (BTN_DIAGNOSTICS, 'send_diagnostics'),
        (BTN_MODE, 'toggle_mode'),
        (BTN_POSITION, 'toggle_position_filter'),
        (BTN_REMOVE_URL, 'start_remove_url'),
        (BTN_EXPORT, 'export_settings'),
        (BTN_HISTORY, 'show_settings_history'),
    ],
)
async def test_buttons_dispatch_to_methods(bot, monkeypatch, button, method_name):
    called = {}

    async def _stub(*args, **kwargs):
        called['ok'] = True

    monkeypatch.setattr(bot, method_name, _stub)
    upd = DummyUpdate(button)
    await bot.handle_message(upd, None)
    assert called.get('ok') is True


@pytest.mark.asyncio
async def test_up_down_dispatch_price_change(bot, monkeypatch):
    deltas = []

    async def _stub(chat_id, delta, update):
        deltas.append(delta)

    monkeypatch.setattr(bot, 'handle_price_change', _stub)

    await bot.handle_message(DummyUpdate(BTN_UP), None)
    await bot.handle_message(DummyUpdate(BTN_DOWN), None)

    assert deltas == [0.01, -0.01]


@pytest.mark.asyncio
@pytest.mark.parametrize('button', [BTN_AUTO_ON, BTN_AUTO_OFF])
async def test_auto_buttons_dispatch_toggle(bot, monkeypatch, button):
    called = {}

    async def _stub(update):
        called['ok'] = True

    monkeypatch.setattr(bot, 'toggle_auto', _stub)
    await bot.handle_message(DummyUpdate(button), None)
    assert called.get('ok') is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('button', 'expected_action'),
    [
        (BTN_PRICE, 'DESIRED_PRICE'),
        (BTN_STEP, 'UNDERCUT_VALUE'),
        (BTN_MIN, 'MIN_PRICE'),
        (BTN_MAX, 'MAX_PRICE'),
        (BTN_ADD_URL, 'ADD_URL'),
        (BTN_IMPORT, 'IMPORT_SETTINGS'),
    ],
)
async def test_buttons_set_pending_actions(bot, button, expected_action):
    upd = DummyUpdate(button, chat_id=555)
    await bot.handle_message(upd, None)
    assert bot.pending_actions[555] == expected_action
    assert upd.message.replies
    assert isinstance(upd.message.replies[-1][1], ReplyKeyboardMarkup)


@pytest.mark.asyncio
async def test_back_clears_pending(bot):
    upd = DummyUpdate(BTN_BACK, chat_id=777)
    bot.pending_actions[777] = 'MIN_PRICE'
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
