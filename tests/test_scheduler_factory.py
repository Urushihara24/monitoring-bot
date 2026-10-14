from types import SimpleNamespace

import pytest

from src.scheduler import Scheduler
from src.scheduler_factory import (
    DryRunScheduler,
    create_scheduler,
    dry_run_enabled,
)


class FakeClient:
    def __init__(self):
        self.update_calls = []

    def update_price(self, *, product_id, new_price):
        self.update_calls.append((product_id, new_price))
        return True


class FakeTelegram:
    pass


def _scheduler_kwargs(client=None):
    return {
        'api_client': client or FakeClient(),
        'telegram_bot': FakeTelegram(),
        'profile_id': 'ggsel',
        'base_profile_id': 'ggsel',
        'profile_name': 'GGSEL',
        'product_id': 123,
        'competitor_urls': [],
        'chat_autoreply_enabled': True,
    }


def test_dry_run_flag_parsing_is_fail_closed():
    assert dry_run_enabled({}) is False
    assert dry_run_enabled({'DRY_RUN': 'true'}) is True
    assert dry_run_enabled({'DRY_RUN': 'YES'}) is True
    assert dry_run_enabled({'DRY_RUN': '0'}) is False

    with pytest.raises(ValueError, match='DRY_RUN must be one of'):
        dry_run_enabled({'DRY_RUN': 'treu'})


def test_factory_uses_dry_run_scheduler_when_enabled(monkeypatch):
    monkeypatch.setenv('DRY_RUN', 'true')

    scheduler = create_scheduler(**_scheduler_kwargs())

    assert isinstance(scheduler, DryRunScheduler)


def test_factory_keeps_production_scheduler_by_default(monkeypatch):
    monkeypatch.delenv('DRY_RUN', raising=False)

    scheduler = create_scheduler(**_scheduler_kwargs())

    assert type(scheduler) is Scheduler


@pytest.mark.asyncio
async def test_dry_run_blocks_price_write_and_exposes_virtual_verification_price():
    client = FakeClient()
    scheduler = DryRunScheduler(**_scheduler_kwargs(client))
    decision = SimpleNamespace(old_price=0.36, reason='dumping')

    success = await scheduler._update_price(0.3449, decision)

    assert success is True
    assert client.update_calls == []
    assert scheduler._read_current_price() == 0.3449
    assert decision.reason == 'dry_run:dumping'


@pytest.mark.asyncio
async def test_dry_run_suppresses_marketplace_chat_writes():
    scheduler = DryRunScheduler(**_scheduler_kwargs())

    assert await scheduler._run_chat_autoreply() is None
