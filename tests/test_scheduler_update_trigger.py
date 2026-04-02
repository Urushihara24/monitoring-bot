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
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_run_cycle_skips_price_update_when_competitor_unchanged(monkeypatch):
    api_client = SimpleNamespace(
        get_my_price=Mock(side_effect=AssertionError('must not be called')),
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
    assert api_client.get_my_price.call_count == 0
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
