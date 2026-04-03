import pytest

import src.scheduler as scheduler_mod
from src.logic import PriceDecision
from src.rsc_parser import ParseResult
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

    async def notify_skip(
        self,
        current_price,
        target_price,
        competitor_price,
        reason,
        profile_name=None,
    ):
        self.skips.append(
            {
                'current_price': current_price,
                'target_price': target_price,
                'competitor_price': competitor_price,
                'reason': reason,
                'profile_name': profile_name,
            }
        )

    async def notify_price_updated(
        self,
        old_price,
        new_price,
        competitor_price,
        reason,
        profile_name=None,
    ):
        self.updates.append(
            {
                'old_price': old_price,
                'new_price': new_price,
                'competitor_price': competitor_price,
                'reason': reason,
                'profile_name': profile_name,
            }
        )

    async def notify_competitor_price_changed(
        self,
        old_price,
        new_price,
        delta,
        rank=None,
        url=None,
        profile_name=None,
    ):
        self.competitor_changes.append(
            {
                'old_price': old_price,
                'new_price': new_price,
                'delta': delta,
                'rank': rank,
                'url': url,
                'profile_name': profile_name,
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
        scheduler_mod.rsc_parser,
        'parse_url',
        lambda url, timeout=10, cookies=None: ParseResult(
            success=True,
            price=0.315,
            error=None,
            offers=[],
            rank=3,
            method='stealth_requests',
            status_code=200,
            url=url,
        ),
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
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        product_id=cfg.GGSEL_PRODUCT_ID,
    )

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
        scheduler_mod.rsc_parser,
        'parse_url',
        lambda url, timeout=10, cookies=None: ParseResult(
            success=True,
            price=0.30,
            error=None,
            offers=[],
            rank=1,
            method='stealth_requests',
            status_code=200,
            url=url,
        ),
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
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        product_id=cfg.GGSEL_PRODUCT_ID,
    )

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert len(bot.skips) == 1


@pytest.mark.asyncio
async def test_scheduler_skips_when_product_id_invalid(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.update_state(last_price=0.35)

    cfg = Config()
    cfg.GGSEL_PRODUCT_ID = 0
    cfg.COMPETITOR_URLS = ['https://example.com/item']

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    parse_called = {'value': False}

    def fake_parse(url, timeout=10, cookies=None):
        parse_called['value'] = True
        return ParseResult(
            success=True,
            price=0.3,
            error=None,
            offers=[],
            rank=1,
            method='stealth_requests',
            status_code=200,
            url=url,
        )

    monkeypatch.setattr(scheduler_mod.rsc_parser, 'parse_url', fake_parse)

    bot = DummyTelegramBot()
    api = DummyApiClient(current_price=0.35)
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=0,
    )

    await scheduler.run_cycle()

    assert parse_called['value'] is False
    assert len(bot.errors) == 1
    assert 'Некорректный product_id' in bot.errors[0]
    assert test_storage.get_state()['skip_count'] == 1
