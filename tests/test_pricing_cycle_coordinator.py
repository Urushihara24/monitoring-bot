from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modular_scheduler import ModularScheduler
from src.scheduler_factory import DryRunScheduler


class FakeClient:
    def __init__(self) -> None:
        self.update_calls: list[tuple[int, float]] = []

    def update_price(self, *, product_id: int, new_price: float) -> bool:
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


@pytest.mark.asyncio
async def test_modular_scheduler_delegates_complete_pricing_cycle(monkeypatch):
    scheduler = ModularScheduler(**_scheduler_kwargs())
    calls: list[bool] = []

    async def fake_run(*, include_chat_autoreply: bool = True):
        calls.append(include_chat_autoreply)
        return 'cycle-result'

    monkeypatch.setattr(
        scheduler._pricing_cycle_coordinator,
        'run',
        fake_run,
    )

    result = await scheduler.run_cycle(include_chat_autoreply=False)

    assert result == 'cycle-result'
    assert calls == [False]


@pytest.mark.asyncio
async def test_dry_run_intercepts_write_through_pricing_coordinator(monkeypatch):
    client = FakeClient()
    scheduler = DryRunScheduler(**_scheduler_kwargs(client))
    observed: dict[str, object] = {}

    async def fake_run(*, include_chat_autoreply: bool = True):
        decision = SimpleNamespace(old_price=0.36, reason='dumping')
        observed['include_chat_autoreply'] = include_chat_autoreply
        observed['write_result'] = await scheduler._update_price(0.3449, decision)
        observed['virtual_price'] = scheduler._read_current_price()
        observed['reason'] = decision.reason
        return 'dry-run-cycle'

    monkeypatch.setattr(
        scheduler._pricing_cycle_coordinator,
        'run',
        fake_run,
    )

    result = await scheduler.run_cycle(include_chat_autoreply=False)

    assert result == 'dry-run-cycle'
    assert observed == {
        'include_chat_autoreply': False,
        'write_result': True,
        'virtual_price': 0.3449,
        'reason': 'dry_run:dumping',
    }
    assert client.update_calls == []
    assert scheduler._dry_run_price is None
