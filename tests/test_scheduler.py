import pytest
from types import SimpleNamespace

import src.scheduler as scheduler_mod
from src.logic import PriceDecision
from src.storage import Storage
from src.config import Config


class DummyApiClient:
    def __init__(self, current_price=0.35, update_ok=True):
        self.current_price = current_price
        self.update_ok = update_ok

    def get_my_price(self, _product_id):
        return self.current_price

    def update_price(self, product_id, new_price):
        self.current_price = new_price
        return self.update_ok


class DummyTelegramBot:
    def __init__(self):
        self.auto_mode = True
        self.errors = []
        self.skips = []
        self.updates = []
        self.competitor_changes = []

    async def notify_error(self, message):
        self.errors.append(message)

    async def notify_skip(self, current_price, target_price, competitor_price, reason):
        self.skips.append(
            {
                'current_price': current_price,
                'target_price': target_price,
                'competitor_price': competitor_price,
                'reason': reason,
            }
        )

    async def notify_price_updated(self, old_price, new_price, competitor_price, reason):
        self.updates.append(
            {
                'old_price': old_price,
                'new_price': new_price,
                'competitor_price': competitor_price,
                'reason': reason,
            }
        )

    async def notify_competitor_price_changed(self, old_price, new_price, delta, rank=None):
        self.competitor_changes.append(
            {
                'old_price': old_price,
                'new_price': new_price,
                'delta': delta,
                'rank': rank,
            }
        )


@pytest.mark.asyncio
async def test_scheduler_notifies_competitor_price_change(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.update_state(last_price=0.35, last_competitor_min=0.3000)

    cfg = Config()
    cfg.GGSEL_PRODUCT_ID = 123
    cfg.COMPETITOR_URLS = ['https://example.com/item']
    cfg.NOTIFY_COMPETITOR_CHANGE = True
    cfg.COMPETITOR_CHANGE_DELTA = 0.001
    cfg.COMPETITOR_CHANGE_COOLDOWN_SECONDS = 0
    cfg.NOTIFY_SKIP = False

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)
    monkeypatch.setattr(
        scheduler_mod.parser,
        'parse_competitors',
        lambda urls, detect_rank=False: [
            SimpleNamespace(success=True, price=0.315, rank=3)
        ],
    )
    monkeypatch.setattr(
        scheduler_mod,
        'calculate_price',
        lambda **kwargs: PriceDecision(
            action='skip',
            price=0.3099,
            reason='test_skip',
            old_price=kwargs.get('current_price'),
            competitor_price=min(kwargs.get('competitor_prices') or [0.315]),
        ),
    )

    bot = DummyTelegramBot()
    api = DummyApiClient(current_price=0.35)
    scheduler = scheduler_mod.Scheduler(api_client=api, telegram_bot=bot)

    await scheduler.run_cycle()

    assert len(bot.competitor_changes) == 1
    change = bot.competitor_changes[0]
    assert change['old_price'] == 0.3000
    assert change['new_price'] == 0.315
    assert change['rank'] == 3


@pytest.mark.asyncio
async def test_scheduler_skip_notifications_are_throttled(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.update_state(last_price=0.35)

    cfg = Config()
    cfg.GGSEL_PRODUCT_ID = 123
    cfg.COMPETITOR_URLS = ['https://example.com/item']
    cfg.NOTIFY_SKIP = True
    cfg.NOTIFY_SKIP_COOLDOWN_SECONDS = 3600
    cfg.NOTIFY_COMPETITOR_CHANGE = False

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)
    monkeypatch.setattr(
        scheduler_mod.parser,
        'parse_competitors',
        lambda urls, detect_rank=False: [
            SimpleNamespace(success=True, price=0.30, rank=1)
        ],
    )
    monkeypatch.setattr(
        scheduler_mod,
        'calculate_price',
        lambda **kwargs: PriceDecision(
            action='skip',
            price=0.2949,
            reason='ignore_delta_base_formula',
            old_price=kwargs.get('current_price'),
            competitor_price=0.30,
        ),
    )

    bot = DummyTelegramBot()
    api = DummyApiClient(current_price=0.35)
    scheduler = scheduler_mod.Scheduler(api_client=api, telegram_bot=bot)

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert len(bot.skips) == 1
