from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.telegram_settings_flow import TelegramSettingsFlow


class FakeStorage:
    def __init__(self) -> None:
        self.runtime_writes: list[dict[str, object]] = []
        self.auto_writes: list[dict[str, object]] = []

    def set_runtime_setting(
        self,
        key,
        value,
        *,
        user_id=None,
        source=None,
        profile_id=None,
        **_kwargs,
    ) -> None:
        self.runtime_writes.append(
            {
                'key': key,
                'value': value,
                'user_id': user_id,
                'source': source,
                'profile_id': profile_id,
            }
        )

    def set_auto_mode(
        self,
        enabled,
        *,
        profile_id,
        user_id=None,
        source=None,
    ) -> None:
        self.auto_writes.append(
            {
                'enabled': enabled,
                'profile_id': profile_id,
                'user_id': user_id,
                'source': source,
            }
        )


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[tuple[str, object]] = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))


class FakeHost:
    def __init__(self, *, pending_action='DESIRED_PRICE') -> None:
        self.pending_action = pending_action
        self.pending_actions = {10: (pending_action, 'ggsel')}
        self.cleared: list[int] = []
        self.settings_sent = 0
        self.runtime = SimpleNamespace(
            MIN_PRICE=0.10,
            MAX_PRICE=1.00,
            MODE='DUMPING',
            SHOWCASE_ROUND_STEP=0.01,
            REBOUND_TO_DESIRED_ON_MIN=False,
            COMPETITOR_URLS=['https://example.test/competitor'],
        )

    def _active_profile(self, _chat_id):
        return 'ggsel'

    def _runtime(self, _profile_id):
        return self.runtime

    def _runtime_for_product(self, _profile_id, _product_id):
        return self.runtime

    def _has_active_product_pair(self, _profile_id, runtime=None):
        return True

    def _product_id(self, _profile_id):
        return 123

    def _resolve_active_product_id(self, _profile_id, runtime=None):
        return 123

    def _runtime_profile_id_for_product(self, profile_id, product_id):
        return f'{profile_id}:{product_id}'

    def _profile_name(self, _profile_id):
        return 'GGSEL'

    def _mode_label(self, value):
        return str(value)

    def _next_mode_for_profile(self, _profile_id, _mode):
        return 'RAISE'

    def _next_rounding_step(self, _step):
        return 1.0

    def _rounding_label(self, value):
        return f'{value:g}'

    def _chat_autoreply_supported(self, _profile_id):
        return True

    def _chat_autoreply_policy(self, _profile_id, *, product_id=None):
        return 'ON_ORDER'

    def _chat_policy_label(self, value):
        return value

    def _chat_rules_storage_key(self, product_id):
        return f'CHAT_RULES:{product_id}'

    def _get_pending_action(self, _chat_id):
        return self.pending_action, 'ggsel'

    def _is_pending_action_expired(self, _chat_id):
        return False

    def _clear_pending_action(self, chat_id):
        self.cleared.append(chat_id)
        self.pending_actions.pop(chat_id, None)

    def get_settings_keyboard(self, _profile_id=None):
        return 'settings-keyboard'

    def get_main_keyboard(self, _profile_id=None):
        return 'main-keyboard'

    async def _reply_no_active_pair(self, update, profile_id):
        await update.message.reply_text(f'no-pair:{profile_id}')

    async def send_settings(self, _chat_id, _update):
        self.settings_sent += 1


@pytest.mark.asyncio
async def test_numeric_setting_is_validated_persisted_and_closes_pending():
    host = FakeHost(pending_action='DESIRED_PRICE')
    storage = FakeStorage()
    flow = TelegramSettingsFlow(host, runtime_storage=storage)
    message = FakeMessage()
    update = SimpleNamespace(message=message)

    handled = await flow.handle_numeric_pending(
        10,
        777,
        '0,34567',
        update,
    )

    assert handled is True
    assert storage.runtime_writes == [
        {
            'key': 'DESIRED_PRICE',
            'value': '0.3457',
            'user_id': 777,
            'source': 'telegram',
            'profile_id': 'ggsel:123',
        }
    ]
    assert host.cleared == [10]
    assert host.settings_sent == 1
    assert message.replies[-1][0].endswith('= 0.3457')


@pytest.mark.asyncio
async def test_numeric_min_cannot_cross_current_max():
    host = FakeHost(pending_action='MIN_PRICE')
    storage = FakeStorage()
    flow = TelegramSettingsFlow(host, runtime_storage=storage)
    message = FakeMessage()
    update = SimpleNamespace(message=message)

    handled = await flow.handle_numeric_pending(10, 777, '2', update)

    assert handled is True
    assert storage.runtime_writes == []
    assert host.cleared == []
    assert message.replies[-1][0] == '❌ MIN_PRICE не может быть больше MAX_PRICE'


@pytest.mark.asyncio
async def test_auto_enable_writes_auto_mode_and_pair_enabled():
    host = FakeHost()
    storage = FakeStorage()
    flow = TelegramSettingsFlow(host, runtime_storage=storage)
    message = FakeMessage()
    update = SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=10),
        effective_user=SimpleNamespace(id=777),
    )

    await flow.set_auto_enabled(update, enabled=True)

    assert storage.auto_writes == [
        {
            'enabled': True,
            'profile_id': 'ggsel:123',
            'user_id': 777,
            'source': 'telegram',
        }
    ]
    assert storage.runtime_writes == [
        {
            'key': 'PAIR_ENABLED',
            'value': 'true',
            'user_id': 777,
            'source': 'telegram',
            'profile_id': 'ggsel:123',
        }
    ]
    assert host.settings_sent == 1


@pytest.mark.asyncio
async def test_chat_policy_cycles_per_active_product():
    host = FakeHost()
    storage = FakeStorage()
    flow = TelegramSettingsFlow(host, runtime_storage=storage)
    message = FakeMessage()
    update = SimpleNamespace(message=message)

    await flow.cycle_chat_autoreply_policy(10, 777, update)

    assert storage.runtime_writes[-1] == {
        'key': 'CHAT_AUTOREPLY_POLICY:123',
        'value': 'FIRST_BUYER_MESSAGE',
        'user_id': 777,
        'source': 'telegram',
        'profile_id': 'ggsel',
    }


def test_chat_rule_persistence_normalizes_payload():
    host = FakeHost()
    storage = FakeStorage()
    flow = TelegramSettingsFlow(host, runtime_storage=storage)

    flow.save_chat_rules(
        profile_id='ggsel',
        product_id=123,
        rules={
            '  FRIEND::YES  ': {
                'enabled': 1,
                'text': '  custom text  ',
                'option': ' friend ',
                'value': ' yes ',
            },
            'invalid': 'skip-me',
        },
        user_id=777,
    )

    write = storage.runtime_writes[-1]
    assert write['key'] == 'CHAT_RULES:123'
    payload = json.loads(str(write['value']))
    assert payload == {
        'version': 1,
        'rules': {
            'friend::yes': {
                'enabled': True,
                'text': 'custom text',
                'option': 'friend',
                'value': 'yes',
            }
        },
    }
