from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import src.scheduler as scheduler_module
from src.logic import PriceDecision
from src.rsc_parser import ParseResult
from src.scheduler import Scheduler


class DummyTelegramBot:
    async def notify_error(self, _text: str):
        return None

    async def notify_skip(self, **_kwargs):
        return None

    async def notify_competitor_price_changed(self, **_kwargs):
        return None

    async def notify_parser_issue(self, **_kwargs):
        return None

    async def notify_price_updated(self, **_kwargs):
        return None


def make_runtime(**kwargs):
    data = {
        'COMPETITOR_URLS': ['https://example.com/item-1'],
        'POSITION_FILTER_ENABLED': False,
        'WEAK_POSITION_THRESHOLD': 20,
        'FAST_REBOUND_DELTA': 0.01,
        'FAST_REBOUND_BYPASS_COOLDOWN': True,
        'COMPETITOR_CHANGE_DELTA': 0.0001,
        'UPDATE_ONLY_ON_COMPETITOR_CHANGE': True,
        'NOTIFY_SKIP': False,
        'IGNORE_DELTA': 0.001,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_run_cycle_skips_price_update_when_competitor_unchanged(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value=0.2649),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': datetime.now(),
        'last_price': 0.2649,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(scheduler, '_sync_cookies_from_env', AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, '_reload_cookies_from_backup', AsyncMock(return_value=False))
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        lambda **_kwargs: PriceDecision(
            action='update',
            price=0.2649,
            reason='base_formula',
            old_price=0.2649,
            competitor_price=0.27,
        ),
    )

    skip_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **kwargs: skip_calls.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )

    await scheduler.run_cycle()

    assert skip_calls, 'skip counter should be incremented'
    assert api_client.get_my_price.call_count == 1
    assert api_client.update_price.call_count == 0


@pytest.mark.asyncio
async def test_run_cycle_recalculates_when_competitor_changed(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value=0.2649),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': None,
        'last_price': 0.2649,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(scheduler, '_sync_cookies_from_env', AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, '_reload_cookies_from_backup', AsyncMock(return_value=False))
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.28,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        lambda **_kwargs: PriceDecision(
            action='skip',
            price=0.2749,
            reason='test_changed',
            old_price=0.2649,
            competitor_price=0.28,
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_skip_throttled', AsyncMock())

    await scheduler.run_cycle()

    assert api_client.get_my_price.call_count == 1


@pytest.mark.asyncio
async def test_run_cycle_skips_cleanly_when_competitor_urls_empty(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value=0.2649),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=123,
        competitor_urls=[],
    )

    runtime = make_runtime(COMPETITOR_URLS=[])
    state = {
        'auto_mode': True,
        'last_competitor_min': None,
        'last_update': None,
        'last_price': 0.2649,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    parse_mock = AsyncMock()
    monkeypatch.setattr(scheduler, '_parse_competitor_price', parse_mock)
    notify_error_mock = AsyncMock()
    monkeypatch.setattr(scheduler, '_notify_error_throttled', notify_error_mock)

    skip_calls = []
    update_state_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **kwargs: skip_calls.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **kwargs: update_state_calls.append(kwargs),
    )

    await scheduler.run_cycle()

    assert skip_calls, 'skip counter should be incremented'
    assert parse_mock.await_count == 0
    assert notify_error_mock.await_count == 0
    assert api_client.get_my_price.call_count == 0
    assert any(
        call.get('last_competitor_error') == 'no_competitor_urls'
        for call in update_state_calls
    )


@pytest.mark.asyncio
async def test_run_cycle_reconciles_when_unchanged_but_price_drift(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value=0.26),
        update_price=Mock(return_value=True),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': None,
        'last_price': 0.26,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_skip_throttled', AsyncMock())
    monkeypatch.setattr(scheduler, '_update_price', AsyncMock(return_value=True))
    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        lambda **_kwargs: PriceDecision(
            action='update',
            price=0.2649,
            reason='base_formula',
            old_price=0.26,
            competitor_price=0.27,
        ),
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_update_count',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'add_price_history',
        lambda **_kwargs: None,
    )

    await scheduler.run_cycle()

    scheduler._update_price.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_cycle_skips_when_target_already_applied(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value=0.26),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': None,
        'last_price': 0.26,
        'last_target_price': 0.2649,
        'last_target_competitor_min': 0.27,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        lambda **_kwargs: PriceDecision(
            action='update',
            price=0.2649,
            reason='base_formula',
            old_price=0.26,
            competitor_price=0.27,
        ),
    )
    skip_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **kwargs: skip_calls.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(scheduler, '_update_price', AsyncMock(return_value=True))

    await scheduler.run_cycle()

    assert skip_calls, 'skip counter should be incremented'
    scheduler._update_price.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_cycle_syncs_last_price_from_api(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value=0.2655),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': datetime.now(),
        'last_price': 0.26,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        lambda **_kwargs: PriceDecision(
            action='skip',
            price=0.2649,
            reason='test_skip',
            old_price=0.2655,
            competitor_price=0.27,
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_skip_throttled', AsyncMock())
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **_kwargs: None,
    )

    update_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **kwargs: update_calls.append(kwargs),
    )

    await scheduler.run_cycle()

    assert any(call.get('last_price') == 0.2655 for call in update_calls)


@pytest.mark.asyncio
async def test_run_cycle_falls_back_to_state_when_get_my_price_raises(monkeypatch):
    def raise_api_error(_product_id):
        raise RuntimeError('api timeout')

    api_client = SimpleNamespace(
        get_my_price=Mock(side_effect=raise_api_error),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': datetime.now(),
        'last_price': 0.2649,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_skip_throttled', AsyncMock())
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **_kwargs: None,
    )

    captured = {}

    def fake_calculate_price(**kwargs):
        captured['current_price'] = kwargs.get('current_price')
        return PriceDecision(
            action='skip',
            price=0.2649,
            reason='test_skip',
            old_price=kwargs.get('current_price'),
            competitor_price=0.27,
        )

    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        fake_calculate_price,
    )

    await scheduler.run_cycle()

    assert captured['current_price'] == 0.2649


@pytest.mark.asyncio
async def test_run_cycle_normalizes_string_current_price(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(return_value='0.2655'),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': datetime.now(),
        'last_price': 0.2649,
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_skip_throttled', AsyncMock())
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **_kwargs: None,
    )

    captured = {}

    def fake_calculate_price(**kwargs):
        captured['current_price'] = kwargs.get('current_price')
        return PriceDecision(
            action='skip',
            price=0.2655,
            reason='test_skip',
            old_price=kwargs.get('current_price'),
            competitor_price=0.27,
        )

    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        fake_calculate_price,
    )

    await scheduler.run_cycle()

    assert captured['current_price'] == 0.2655


@pytest.mark.asyncio
async def test_run_cycle_normalizes_string_state_last_price_fallback(monkeypatch):
    def raise_api_error(_product_id):
        raise RuntimeError('api timeout')

    api_client = SimpleNamespace(
        get_my_price=Mock(side_effect=raise_api_error),
        update_price=Mock(),
    )
    scheduler = Scheduler(
        api_client,
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=['https://example.com/item-1'],
    )

    runtime = make_runtime()
    state = {
        'auto_mode': True,
        'last_competitor_min': 0.27,
        'last_update': datetime.now(),
        'last_price': '0.2649',
    }

    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(scheduler, '_state', lambda: state)
    monkeypatch.setattr(
        scheduler_module,
        'validate_runtime_config',
        lambda _runtime: (True, []),
    )
    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        scheduler,
        '_parse_competitor_price',
        AsyncMock(
            return_value=ParseResult(
                success=True,
                price=0.27,
                url='https://example.com/item-1',
                method='stealth_requests',
            )
        ),
    )
    monkeypatch.setattr(scheduler, '_notify_competitor_change_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_parser_issue_if_needed', AsyncMock())
    monkeypatch.setattr(scheduler, '_notify_skip_throttled', AsyncMock())
    monkeypatch.setattr(
        scheduler_module.storage,
        'update_state',
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'increment_skip_count',
        lambda **_kwargs: None,
    )

    captured = {}

    def fake_calculate_price(**kwargs):
        captured['current_price'] = kwargs.get('current_price')
        return PriceDecision(
            action='skip',
            price=0.2649,
            reason='test_skip',
            old_price=kwargs.get('current_price'),
            competitor_price=0.27,
        )

    monkeypatch.setattr(
        scheduler_module,
        'calculate_price',
        fake_calculate_price,
    )

    await scheduler.run_cycle()

    assert captured['current_price'] == 0.2649
