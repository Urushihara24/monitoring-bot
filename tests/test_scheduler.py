from datetime import datetime, timedelta, timezone
import sqlite3
from types import SimpleNamespace

import pytest

from src import chat_autoreply as chat_keys
import src.scheduler as scheduler_mod
from src.config import Config
from src.logic import PriceDecision
from src.rsc_parser import ParseResult
from src.storage import Storage


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
        self.parser_issues = []
        self.notifications = []

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

    async def notify(self, message):
        self.notifications.append(message)

    async def notify_parser_issue(
        self,
        *,
        url,
        method,
        reason,
        error,
        status_code=None,
        profile_name=None,
    ):
        self.parser_issues.append(
            {
                'url': url,
                'method': method,
                'reason': reason,
                'error': error,
                'status_code': status_code,
                'profile_name': profile_name,
            }
        )


def test_read_current_price_digiseller_skips_my_price_fallback():
    class ApiClient:
        def __init__(self):
            self.display_calls = 0
            self.my_price_calls = 0

        def get_display_price(self, _product_id):
            self.display_calls += 1
            return None

        def get_my_price(self, _product_id):
            self.my_price_calls += 1
            return 1.1

    api = ApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=DummyTelegramBot(),
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    assert scheduler._read_current_price() is None
    assert api.display_calls == 1
    assert api.my_price_calls == 0


def test_read_current_price_ggsel_prefers_card_unit_price(monkeypatch):
    class ApiClient:
        def __init__(self):
            self.my_price_calls = 0

        def get_product_info(self, _product_id, timeout=10):
            return {'url': 'https://ggsel.net/catalog/product/4697439'}

        def get_my_price(self, _product_id):
            self.my_price_calls += 1
            return 0.25

    api = ApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    monkeypatch.setattr(
        scheduler_mod.rsc_parser,
        'parse_url',
        lambda url, timeout=12, cookies=None: ParseResult(
            success=True,
            price=0.2549,
            error=None,
            offers=[],
            rank=None,
            method='stealth_requests',
            status_code=200,
            url=url,
        ),
    )

    runtime = SimpleNamespace(COMPETITOR_COOKIES='foo=bar')
    assert scheduler._read_current_price(runtime=runtime) == 0.2549
    assert api.my_price_calls == 0


def test_read_current_price_ggsel_fallbacks_to_my_price(monkeypatch):
    class ApiClient:
        def __init__(self):
            self.my_price_calls = 0

        def get_product_info(self, _product_id, timeout=10):
            return {'url': 'https://ggsel.net/catalog/product/4697439'}

        def get_my_price(self, _product_id):
            self.my_price_calls += 1
            return 0.2649

    api = ApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    monkeypatch.setattr(
        scheduler_mod.rsc_parser,
        'parse_url',
        lambda url, timeout=12, cookies=None: ParseResult(
            success=False,
            price=None,
            error='HTTP 403',
            offers=[],
            rank=None,
            method='stealth_requests',
            status_code=403,
            url=url,
            block_reason='http_403',
        ),
    )

    runtime = SimpleNamespace(COMPETITOR_COOKIES='foo=bar')
    assert scheduler._read_current_price(runtime=runtime) == 0.2649
    assert api.my_price_calls == 1


def test_read_current_price_ggsel_fallbacks_to_public_before_my_price(
    monkeypatch,
):
    class ApiClient:
        def __init__(self):
            self.my_price_calls = 0
            self.public_calls = 0

        def get_product_info(self, _product_id, timeout=10):
            return {'url': 'https://ggsel.net/catalog/product/4697439'}

        def get_public_price(self, _product_id):
            self.public_calls += 1
            return 0.3349

        def get_my_price(self, _product_id):
            self.my_price_calls += 1
            return 0.33

    api = ApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    monkeypatch.setattr(
        scheduler_mod.rsc_parser,
        'parse_url',
        lambda url, timeout=12, cookies=None: ParseResult(
            success=False,
            price=None,
            error='HTTP 401',
            offers=[],
            rank=None,
            method='stealth_requests',
            status_code=401,
            url=url,
            block_reason='http_401',
            cookies_expired=True,
        ),
    )

    runtime = SimpleNamespace(COMPETITOR_COOKIES='foo=bar')
    assert scheduler._read_current_price(runtime=runtime) == 0.3349
    assert api.public_calls == 1
    assert api.my_price_calls == 0


@pytest.mark.asyncio
async def test_notify_parser_issue_digiseller_transient_403_suppressed(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    monkey_cfg = Config()
    monkey_cfg.DIGISELLER_PRODUCT_ID = 5077639
    monkey_cfg.DIGISELLER_COMPETITOR_URLS = [
        'https://plati.market/itm/name/5655506'
    ]
    monkey_cfg.NOTIFY_PARSER_ISSUES = True
    monkey_cfg.PARSER_ISSUE_COOLDOWN_SECONDS = 0

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', monkey_cfg)

    bot = DummyTelegramBot()
    scheduler = scheduler_mod.Scheduler(
        api_client=DummyApiClient(),
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=monkey_cfg.DIGISELLER_COMPETITOR_URLS,
    )

    runtime = SimpleNamespace(
        NOTIFY_PARSER_ISSUES=True,
        PARSER_ISSUE_COOLDOWN_SECONDS=0,
    )
    result = ParseResult(
        success=False,
        price=None,
        error='HTTP 403',
        url='https://plati.market/itm/name/5655506',
        method='stealth_requests',
        block_reason='http_403',
        status_code=403,
    )

    await scheduler._notify_parser_issue_if_needed(
        runtime=runtime,
        url=result.url,
        result=result,
        fail_streak=1,
    )
    assert bot.parser_issues == []

    await scheduler._notify_parser_issue_if_needed(
        runtime=runtime,
        url=result.url,
        result=result,
        fail_streak=3,
    )
    assert len(bot.parser_issues) == 1
    assert bot.parser_issues[0]['reason'] == 'http_403'


@pytest.mark.asyncio
async def test_notify_error_throttled_disabled_by_runtime_flag(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)

    bot = DummyTelegramBot()
    scheduler = scheduler_mod.Scheduler(
        api_client=DummyApiClient(),
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    runtime = SimpleNamespace(NOTIFY_ERRORS=False)
    await scheduler._notify_error_throttled(
        key='test_error',
        message='test message',
        cooldown_seconds=0,
        runtime=runtime,
    )

    assert bot.errors == []


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


@pytest.mark.asyncio
async def test_scheduler_stores_applied_price_when_api_rounds(monkeypatch, tmp_path):
    class RoundingApiClient(DummyApiClient):
        def update_price(self, product_id, new_price):
            self.current_price = round(float(new_price), 2)
            return self.update_ok

    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.update_state(last_price=0.2600, auto_mode=True)

    cfg = Config()
    cfg.GGSEL_PRODUCT_ID = 123
    cfg.COMPETITOR_URLS = ['https://example.com/item']
    cfg.NOTIFY_SKIP = False

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)
    monkeypatch.setattr(
        scheduler_mod.rsc_parser,
        'parse_url',
        lambda url, timeout=10, cookies=None: ParseResult(
            success=True,
            price=0.26,
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
            action='update',
            price=0.2549,
            reason='base_formula',
            old_price=kwargs.get('current_price'),
            competitor_price=0.26,
        ),
    )

    bot = DummyTelegramBot()
    api = RoundingApiClient(current_price=0.2600, update_ok=True)
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        product_id=cfg.GGSEL_PRODUCT_ID,
    )

    await scheduler.run_cycle()

    state = test_storage.get_state()
    assert state['last_target_price'] == 0.2549
    assert state['last_price'] == 0.25
    assert len(bot.updates) == 1
    assert bot.updates[0]['new_price'] == 0.25


@pytest.mark.asyncio
async def test_scheduler_unknown_rank_gap_forces_weak_mode(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.update_state(last_price=0.31, auto_mode=True)

    cfg = Config()
    cfg.GGSEL_PRODUCT_ID = 123
    cfg.COMPETITOR_URLS = [
        'https://example.com/a',
        'https://example.com/b',
    ]
    cfg.POSITION_FILTER_ENABLED = True
    cfg.WEAK_UNKNOWN_RANK_ENABLED = True
    cfg.WEAK_UNKNOWN_RANK_ABS_GAP = 0.03
    cfg.WEAK_UNKNOWN_RANK_REL_GAP = 0.08
    cfg.NOTIFY_SKIP = False

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    def fake_parse(url, timeout=10, cookies=None):
        price = 0.26 if url.endswith('/a') else 0.34
        return ParseResult(
            success=True,
            price=price,
            error=None,
            offers=[],
            rank=None,
            method='stealth_requests',
            status_code=200,
            url=url,
        )

    monkeypatch.setattr(scheduler_mod.rsc_parser, 'parse_url', fake_parse)
    captured = {}

    def fake_calculate_price(**kwargs):
        captured['force_weak_mode'] = kwargs.get('force_weak_mode')
        return PriceDecision(
            action='skip',
            price=kwargs.get('current_price'),
            reason='test_skip',
            old_price=kwargs.get('current_price'),
            competitor_price=min(kwargs.get('competitor_prices') or [0.26]),
        )

    monkeypatch.setattr(scheduler_mod, 'calculate_price', fake_calculate_price)

    scheduler = scheduler_mod.Scheduler(
        api_client=DummyApiClient(current_price=0.31),
        telegram_bot=DummyTelegramBot(),
        product_id=cfg.GGSEL_PRODUCT_ID,
    )

    await scheduler.run_cycle()

    assert captured['force_weak_mode'] is True


@pytest.mark.asyncio
async def test_scheduler_unknown_rank_small_gap_keeps_normal_mode(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.update_state(last_price=0.31, auto_mode=True)

    cfg = Config()
    cfg.GGSEL_PRODUCT_ID = 123
    cfg.COMPETITOR_URLS = [
        'https://example.com/a',
        'https://example.com/b',
    ]
    cfg.POSITION_FILTER_ENABLED = True
    cfg.WEAK_UNKNOWN_RANK_ENABLED = True
    cfg.WEAK_UNKNOWN_RANK_ABS_GAP = 0.03
    cfg.WEAK_UNKNOWN_RANK_REL_GAP = 0.08
    cfg.NOTIFY_SKIP = False

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    def fake_parse(url, timeout=10, cookies=None):
        price = 0.31 if url.endswith('/a') else 0.32
        return ParseResult(
            success=True,
            price=price,
            error=None,
            offers=[],
            rank=None,
            method='stealth_requests',
            status_code=200,
            url=url,
        )

    monkeypatch.setattr(scheduler_mod.rsc_parser, 'parse_url', fake_parse)
    captured = {}

    def fake_calculate_price(**kwargs):
        captured['force_weak_mode'] = kwargs.get('force_weak_mode')
        return PriceDecision(
            action='skip',
            price=kwargs.get('current_price'),
            reason='test_skip',
            old_price=kwargs.get('current_price'),
            competitor_price=min(kwargs.get('competitor_prices') or [0.31]),
        )

    monkeypatch.setattr(scheduler_mod, 'calculate_price', fake_calculate_price)

    scheduler = scheduler_mod.Scheduler(
        api_client=DummyApiClient(current_price=0.31),
        telegram_bot=DummyTelegramBot(),
        product_id=cfg.GGSEL_PRODUCT_ID,
    )

    await scheduler.run_cycle()

    assert captured['force_weak_mode'] is False


class DummyChatApiClient:
    def __init__(self):
        self.sent_messages = []
        self.product_info_calls = []
        self.message_queries = []
        self.list_chats_calls = 0

    def list_chats(self, **kwargs):
        self.list_chats_calls += 1
        if kwargs.get('page') == 1:
            return [{'id_i': 111, 'id_d': 5077639}]
        return []

    def get_order_info(self, _order_id, **_kwargs):
        return {
            'locale': 'ru-RU',
            'options': [{'value': 'уже в друзьях'}],
            'id_d': 5077639,
        }

    def get_product_info(self, product_id, timeout=10, lang=None):
        self.product_info_calls.append((product_id, lang))
        return {'info': 'Инструкция RU', 'add_info': 'Инструкция add'}

    def send_chat_message(self, order_id, message, timeout=10):
        self.sent_messages.append((order_id, message))
        return True

    def list_messages(self, order_id, **kwargs):
        self.message_queries.append((order_id, kwargs))
        return []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_sent_once(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE = 50
    cfg.DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES = 2
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    bot = DummyTelegramBot()
    api = DummyChatApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:111',
            profile_id='digiseller',
        ) is not None
    )
    assert len(bot.notifications) == 1


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_only_empty_chat_blocks_send(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = True
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NonEmptyChatApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'Покупатель уже писал'}]

    bot = DummyTelegramBot()
    api = NonEmptyChatApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:111',
            profile_id='digiseller',
        ) is None
    )


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_only_empty_chat_runtime_off_allows_send(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
        'false',
        profile_id='digiseller',
    )
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = True
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NonEmptyChatApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'Покупатель уже писал'}]

    bot = DummyTelegramBot()
    api = NonEmptyChatApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_smart_non_empty_allows_greeting(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY = True
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NonEmptyGreetingApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'Здравствуйте, как добавить в друзья?'}]

    bot = DummyTelegramBot()
    api = NonEmptyGreetingApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_smart_non_empty_blocks_done_chat(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY = True
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NonEmptyDoneApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [
                {'message': 'Здравствуйте, когда отправите?', 'buyer': 1},
                {
                    'message': 'Ваш заказ выполнен. Оставите отзыв?',
                    'seller': 1,
                },
            ]

    bot = DummyTelegramBot()
    api = NonEmptyDoneApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_smart_non_empty_allows_buyer_code(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY = True
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NonEmptyCodeApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'X46RP-2KQ77-MM9K9-TFJFD-RYC9Z', 'buyer': 1}]

    bot = DummyTelegramBot()
    api = NonEmptyCodeApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_smart_non_empty_skips_seller_only(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY = True
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NonEmptySellerOnlyApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'Здравствуйте! Ваш заказ выполнен.', 'seller': 1}]

    bot = DummyTelegramBot()
    api = NonEmptySellerOnlyApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_policy_first_buyer_message(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_POLICY:5077639',
        'FIRST_BUYER_MESSAGE',
        profile_id='digiseller',
    )
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = False
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class FirstBuyerMessageApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'Подтвердите, пожалуйста', 'seller': 1}]

    bot = DummyTelegramBot()
    api = FirstBuyerMessageApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_policy_code_only_allows_buyer_code(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_POLICY:5077639',
        'CODE_ONLY',
        profile_id='digiseller',
    )
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = False
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class CodeOnlyApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'X46RP-2KQ77-MM9K9-TFJFD-RYC9Z', 'buyer': 1}]

    bot = DummyTelegramBot()
    api = CodeOnlyApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_ggsel_chat_autoreply_sent_once(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.GGSEL_CHAT_AUTOREPLY_ENABLED = True
    cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.GGSEL_CHAT_AUTOREPLY_PAGE_SIZE = 50
    cfg.GGSEL_CHAT_AUTOREPLY_MAX_PAGES = 2
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    bot = DummyTelegramBot()
    api = DummyChatApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:111',
            profile_id='ggsel',
        ) is not None
    )
    assert len(bot.notifications) == 1


@pytest.mark.asyncio
async def test_scheduler_ggsel_chat_autoreply_uses_chat_product_field(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.GGSEL_CHAT_AUTOREPLY_ENABLED = True
    cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = [4697439]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class GGChatProductApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'product': 4697439}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            # content_id равен order_id, не должен быть принят как product_id.
            return {
                'locale': 'ru-RU',
                'content_id': 111,
                'item_id': 5098522,
                'options': [{'value': 'уже в друзьях'}],
            }

    bot = DummyTelegramBot()
    api = GGChatProductApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_ggsel_chat_autoreply_skips_mismatched_chat_product(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.GGSEL_CHAT_AUTOREPLY_ENABLED = True
    cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = [4697439]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class GGChatProductMismatchApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'product': 5098522}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'content_id': 111,
                'item_id': 5098522,
                'options': [{'value': 'уже в друзьях'}],
            }

    bot = DummyTelegramBot()
    api = GGChatProductMismatchApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_uses_template(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_TEMPLATE_EN_ADD = 'Use template EN'
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class EnglishApi(DummyChatApiClient):
        def __init__(self):
            super().__init__()
            self.order_info_locales = []

        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'id_d': 5077639, 'lang': 'en-US'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            self.order_info_locales.append(_kwargs.get('locale'))
            return {
                'locale': 'en-US',
                'options': [{'value': 'will add'}],
                'id_d': 5077639,
            }

    bot = DummyTelegramBot()
    api = EnglishApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Use template EN')]
    assert api.product_info_calls == []
    assert api.order_info_locales == ['en-US']


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_accepts_chat_product_field(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class DigiChatProductApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'product': 5077639}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'content_id': 111,
                'options': [{'value': 'уже в друзьях'}],
            }

    bot = DummyTelegramBot()
    api = DigiChatProductApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_order_info_locale_fallback(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class LocaleFallbackApi(DummyChatApiClient):
        def __init__(self):
            super().__init__()
            self.order_info_locales = []

        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'id_d': 5077639, 'lang': 'en-US'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            locale = _kwargs.get('locale')
            self.order_info_locales.append(locale)
            if locale == 'en-US':
                return {}
            if locale == 'en':
                return {
                    'locale': 'en-US',
                    'options': [{'value': 'already friend'}],
                    'id_d': 5077639,
                }
            return {}

    bot = DummyTelegramBot()
    api = LocaleFallbackApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.order_info_locales == ['en-US', 'en']
    assert api.sent_messages == [(111, 'Инструкция RU')]


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_uses_add_info(monkeypatch, tmp_path):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class AddModeApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'options': [{'value': 'добавит'}],
                'id_d': 5077639,
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'info': 'Main instruction', 'add_info': 'Add instruction'}

    bot = DummyTelegramBot()
    api = AddModeApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Add instruction')]
    assert api.product_info_calls == [(5077639, 'ru-RU')]


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_prefers_locale_specific_fields(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class LocaleApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'id_d': 5077639, 'lang': 'en-US'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'en-US',
                'options': [{'value': 'already friend'}],
                'id_d': 5077639,
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {
                'info': 'Default RU',
                'info_en': 'English instruction',
            }

    bot = DummyTelegramBot()
    api = LocaleApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'English instruction')]
    assert api.product_info_calls == [(5077639, 'en-US')]


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_prefers_add_info_en_for_add_mode(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class AddLocaleApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'id_d': 5077639, 'lang': 'en-US'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'en-US',
                'options': [{'value': 'will add'}],
                'id_d': 5077639,
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {
                'add_info': 'Default add',
                'add_info_en': 'Add EN',
                'instruction': 'Fallback instruction',
            }

    bot = DummyTelegramBot()
    api = AddLocaleApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Add EN')]
    assert api.product_info_calls == [(5077639, 'en-US')]


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_detects_mode_from_variant_id(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class VariantIdApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'question': 'Уже в друзьях?',
                        'variant_id': 1,
                        'variants': [
                            {'id': 1, 'name': 'Уже в друзьях'},
                            {'id': 2, 'name': 'Добавит'},
                        ],
                    }
                ],
                'add_info': 'Add instruction',
                'info': 'Main instruction',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'info': 'Product info fallback'}

    bot = DummyTelegramBot()
    api = VariantIdApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Main instruction')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_detects_mode_from_bool_choice(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class BoolChoiceApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'Уже в друзьях?',
                        'value': '0',
                    }
                ],
                'add_info': 'Add instruction',
                'info': 'Main instruction',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'info': 'Product info fallback'}

    bot = DummyTelegramBot()
    api = BoolChoiceApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Add instruction')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_maps_selected_id_to_variant_text(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class SelectedIdApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'Выбор сценария',
                        'selected_id': 2,
                        'variants': [
                            {'id': 1, 'name': 'Уже в друзьях'},
                            {'id': 2, 'name': 'Добавит'},
                        ],
                    }
                ],
                'add_info': 'Add instruction',
                'info': 'Main instruction',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'info': 'Product info fallback'}

    bot = DummyTelegramBot()
    api = SelectedIdApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Add instruction')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_uses_selected_variant_instruction(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class VariantInstructionApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'Сценарий',
                        'selected_id': 2,
                        'variants': [
                            {'id': 1, 'name': 'A', 'info': 'Instruction A'},
                            {'id': 2, 'name': 'B', 'info': 'Instruction B'},
                        ],
                    }
                ],
                'info': 'Order default instruction',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'info': 'Product instruction fallback'}

    bot = DummyTelegramBot()
    api = VariantInstructionApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Instruction B')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_uses_selected_variant_add_info(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class VariantAddInfoApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {'name': 'Уже в друзьях?', 'value': '0'},
                    {
                        'name': 'Тип',
                        'selected_id': 7,
                        'variants': [
                            {'id': 7, 'name': 'X', 'add_info': 'Variant add info'},
                        ],
                    },
                ],
                'add_info': 'Order default add',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'add_info': 'Product add fallback'}

    bot = DummyTelegramBot()
    api = VariantAddInfoApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Variant add info')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_prefers_friend_option_over_other_options(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class MixedOptionsApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'Способ оплаты',
                        'selected_id': 1,
                        'variants': [
                            {
                                'id': 1,
                                'name': 'Карта',
                                'add_info': 'Wrong payment instruction',
                            },
                        ],
                    },
                    {
                        'name': 'Уже в друзьях?',
                        'selected_id': 2,
                        'variants': [
                            {'id': 1, 'name': 'Уже в друзьях'},
                            {
                                'id': 2,
                                'name': 'Добавит',
                                'add_info': 'Correct friend instruction',
                            },
                        ],
                    },
                ],
                'add_info': 'Fallback add',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'add_info': 'Product add fallback'}

    bot = DummyTelegramBot()
    api = MixedOptionsApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Correct friend instruction')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_uses_order_info_instruction_first(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class OrderInfoInstructionApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'id_d': 5077639, 'lang': 'en-US'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'en-US',
                'options': [{'value': 'already friend'}],
                'id_d': 5077639,
                'info_en': 'Order instruction EN',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'info_en': 'Product instruction EN'}

    bot = DummyTelegramBot()
    api = OrderInfoInstructionApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Order instruction EN')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_product_info_locale_fallback(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class ProductLocaleFallbackApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'id_d': 5077639, 'lang': 'en-US'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'en-US',
                'options': [{'value': 'already friend'}],
                'id_d': 5077639,
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            if lang == 'en-US':
                return {}
            if lang == 'ru-RU':
                return {'info_ru': 'RU fallback instruction'}
            return {}

    bot = DummyTelegramBot()
    api = ProductLocaleFallbackApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'RU fallback instruction')]
    assert api.product_info_calls == [(5077639, 'en-US'), (5077639, 'ru-RU')]


@pytest.mark.asyncio
async def test_scheduler_ggsel_chat_autoreply_uses_selected_variant_add_info(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.GGSEL_CHAT_AUTOREPLY_ENABLED = True
    cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class GgselVariantApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'Уже в друзьях?',
                        'selected_id': 2,
                        'variants': [
                            {'id': 1, 'name': 'Уже в друзьях'},
                            {
                                'id': 2,
                                'name': 'Добавит',
                                'add_info': 'GG selected add instruction',
                            },
                        ],
                    }
                ],
                'add_info': 'GG default add',
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {'add_info': 'GG product fallback'}

    bot = DummyTelegramBot()
    api = GgselVariantApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'GG selected add instruction')]
    assert api.product_info_calls == []


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_rules_use_product_variant_instruction(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    option_name = 'Наши аккаунты в друзьях'
    selected_value = 'Нет. Добавлю после оплаты.'
    rule_key = chat_keys.option_rule_key(option_name, selected_value)
    test_storage.set_runtime_setting(
        chat_keys.rules_key(5077639),
        (
            '{"version":1,"rules":{'
            f'"{rule_key}":{{"enabled":true,"text":""}}'
            '}}'
        ),
        profile_id='digiseller',
        source='test',
    )

    class RulesApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': option_name,
                        'selected_id': 1,
                        'variants': [
                            {'id': 1, 'text': selected_value},
                            {'id': 2, 'text': 'Да. Проверил(а), в друзьях'},
                        ],
                    }
                ],
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {
                'options': [
                    {
                        'name': option_name,
                        'variants': [
                            {
                                'id': 1,
                                'text': selected_value,
                                'info': 'Инструкция по выбранному параметру',
                            },
                        ],
                    }
                ]
            }

    bot = DummyTelegramBot()
    api = RulesApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция по выбранному параметру')]
    assert api.product_info_calls == [(5077639, 'ru-RU')]


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_rules_match_by_option_variant_ids(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    rule_key = chat_keys.option_variant_rule_key(3066422, 11792090)
    test_storage.set_runtime_setting(
        chat_keys.rules_key(5077639),
        (
            '{"version":1,"rules":{'
            f'"{rule_key}":{{"enabled":true,"text":""}}'
            '}}'
        ),
        profile_id='digiseller',
        source='test',
    )

    class RulesIdApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'option_select_3066422',
                        'selected_id': 11792090,
                        'variants': [
                            {
                                'value': 11792090,
                                'text': 'Нет, добавлю позже (текст может меняться)',
                            },
                            {'value': 11792091, 'text': 'Да, уже в друзьях'},
                        ],
                    }
                ],
            }

        def get_product_info(self, product_id, timeout=10, lang=None):
            self.product_info_calls.append((product_id, lang))
            return {
                'options': [
                    {
                        'id': 3066422,
                        'label': 'Наши аккаунты в друзьях?',
                        'variants': [
                            {
                                'value': 11792090,
                                'text': 'Нет. Добавлю после оплаты',
                                'add_info': 'ID-based instruction',
                            },
                        ],
                    }
                ]
            }

    bot = DummyTelegramBot()
    api = RulesIdApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'ID-based instruction')]
    assert api.product_info_calls == [(5077639, 'ru-RU')]


@pytest.mark.asyncio
async def test_scheduler_ggsel_rules_match_by_user_data_id(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.GGSEL_CHAT_AUTOREPLY_ENABLED = True
    cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = [4697439]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    rule_key = chat_keys.option_variant_rule_key(32496, 152937)
    test_storage.set_runtime_setting(
        chat_keys.rules_key(4697439),
        (
            '{"version":1,"rules":{'
            f'"{rule_key}":{{"enabled":true,"text":"GGSEL user_data_id"}}'
            '}}'
        ),
        profile_id='ggsel',
        source='test',
    )

    class GGSELRulesApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'product': 4697439}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 4697439,
                'options': [
                    {
                        'id': 32496,
                        'name': 'Наши аккаунты ***8rabbit в друзьях?',
                        'user_data': 'Нет. Добавлю после оплаты',
                        'user_data_id': 152937,
                    }
                ],
            }

    bot = DummyTelegramBot()
    api = GGSELRulesApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'GGSEL user_data_id')]


@pytest.mark.asyncio
async def test_scheduler_ggsel_rules_match_by_user_data_text(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.GGSEL_CHAT_AUTOREPLY_ENABLED = True
    cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = [4697439]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    rule_key = chat_keys.option_rule_key(
        'Наши аккаунты ***8rabbit в друзьях?',
        'Нет. Добавлю после оплаты',
    )
    test_storage.set_runtime_setting(
        chat_keys.rules_key(4697439),
        (
            '{"version":1,"rules":{'
            f'"{rule_key}":{{"enabled":true,"text":"GGSEL user_data text"}}'
            '}}'
        ),
        profile_id='ggsel',
        source='test',
    )

    class GGSELTextRulesApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'product': 4697439}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 4697439,
                'options': [
                    {
                        'id': 32496,
                        'name': 'Наши аккаунты ***8rabbit в друзьях?',
                        'user_data': 'Нет. Добавлю после оплаты',
                    }
                ],
            }

    bot = DummyTelegramBot()
    api = GGSELTextRulesApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=4697439,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'GGSEL user_data text')]


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_rules_without_match_skip_order(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    test_storage.set_runtime_setting(
        chat_keys.rules_key(5077639),
        (
            '{"version":1,"rules":{'
            '"другой параметр::другое значение":{"enabled":true,"text":""}'
            '}}'
        ),
        profile_id='digiseller',
        source='test',
    )

    class RulesNoMatchApi(DummyChatApiClient):
        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'id_d': 5077639,
                'options': [
                    {
                        'name': 'Наши аккаунты в друзьях',
                        'selected_id': 1,
                        'variants': [
                            {'id': 1, 'text': 'Нет. Добавлю после оплаты.'},
                        ],
                    }
                ],
            }

    bot = DummyTelegramBot()
    api = RulesNoMatchApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []
    assert bot.notifications == []


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_passes_product_filter_to_list_chats(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639, 5104800]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class FilterCaptureApi(DummyChatApiClient):
        def __init__(self):
            super().__init__()
            self.list_chats_kwargs = []

        def list_chats(self, **kwargs):
            self.list_chats_kwargs.append(kwargs)
            return []

    bot = DummyTelegramBot()
    api = FilterCaptureApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert len(api.list_chats_kwargs) == 2
    assert api.list_chats_kwargs[0].get('product_ids') == [5077639, 5104800]
    assert api.list_chats_kwargs[1].get('product_ids') == [5077639, 5104800]
    assert api.list_chats_kwargs[0].get('filter_new') == 1
    assert api.list_chats_kwargs[1].get('filter_new') is None


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_recent_fallback_picks_new_order(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES = 1
    cfg.DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES = 30
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    now_text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    class RecentFallbackApi(DummyChatApiClient):
        def __init__(self):
            super().__init__()
            self.calls = []

        def list_chats(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get('filter_new') == 1:
                return []
            if kwargs.get('page') == 1:
                return [{
                    'id_i': 111,
                    'id_d': 5077639,
                    'last_date': now_text,
                }]
            return []

    bot = DummyTelegramBot()
    api = RecentFallbackApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == [(111, 'Инструкция RU')]
    assert [call.get('filter_new') for call in api.calls] == [1, None]


@pytest.mark.asyncio
async def test_scheduler_chat_autoreply_skips_order_without_resolved_product_id(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639, 5104800]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class UnknownProductApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            if kwargs.get('page') == 1:
                return [{'id_i': 111, 'lang': 'ru-RU'}]
            return []

        def get_order_info(self, _order_id, **_kwargs):
            return {
                'locale': 'ru-RU',
                'options': [{'value': 'уже в друзьях'}],
            }

    bot = DummyTelegramBot()
    api = UnknownProductApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []
    assert len(bot.notifications) == 0


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_error_not_break_cycle(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class BrokenApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            raise RuntimeError('chat api down')

    bot = DummyTelegramBot()
    api = BrokenApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    state = test_storage.get_state(profile_id='digiseller')
    assert state['skip_count'] == 1
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_LAST_ERROR',
            profile_id='digiseller',
        ) == 'chat api down'
    )


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_perms_fail_fast(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NoPermsApi(DummyChatApiClient):
        def get_chat_perms_status(self, timeout=8, include_send_probe=False):
            assert timeout == 8
            assert include_send_probe is False
            return False, 'chats.read=FAIL[http_401]'

        def list_chats(self, **kwargs):  # pragma: no cover
            raise AssertionError(
                'list_chats should not be called when perms fail'
            )

    bot = DummyTelegramBot()
    api = NoPermsApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    state = test_storage.get_state(profile_id='digiseller')
    assert state['skip_count'] == 1
    last_error = test_storage.get_runtime_setting(
        'CHAT_AUTOREPLY_LAST_ERROR',
        profile_id='digiseller',
    )
    assert 'Недостаточно прав chat API для авто-инструкций' in (last_error or '')
    assert len(bot.errors) == 1
    assert 'chats.read=FAIL[http_401]' in bot.errors[0]


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_perms_no_response_retry_ok(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class FlakyPermsApi(DummyChatApiClient):
        def __init__(self):
            super().__init__()
            self._perms_calls = 0

        def get_chat_perms_status(self, timeout=8, include_send_probe=False):
            assert include_send_probe is False
            self._perms_calls += 1
            if self._perms_calls == 1:
                assert timeout == 8
                return (
                    False,
                    'chats.read=OK[http_200]; messages.read=FAIL[no_response]; '
                    'purchase.read=OK[http_200]',
                )
            assert timeout == 12
            return (
                True,
                'chats.read=OK[http_200]; messages.read=OK[http_200]; '
                'purchase.read=OK[http_200]',
            )

    bot = DummyTelegramBot()
    api = FlakyPermsApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api._perms_calls == 2
    assert api.sent_messages == [(111, 'Инструкция RU')]
    assert not bot.errors
    last_error = test_storage.get_runtime_setting(
        'CHAT_AUTOREPLY_LAST_ERROR',
        profile_id='digiseller',
    )
    assert last_error in (None, '')


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_skips_duplicate_by_messages(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = False
    cfg.DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES = 30
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class DuplicateApi(DummyChatApiClient):
        def list_messages(self, order_id, **kwargs):
            self.message_queries.append((order_id, kwargs))
            return [{'message': 'Инструкция RU'}]

    bot = DummyTelegramBot()
    api = DuplicateApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert api.sent_messages == []
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:111',
            profile_id='digiseller',
        ) is not None
    )
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_DUPLICATE_COUNT',
            profile_id='digiseller',
        ) == '1'
    )


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_cleanup_old_sent_markers(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    old_ts = (datetime.now() - timedelta(days=45)).isoformat()
    fresh_ts = (datetime.now() - timedelta(days=2)).isoformat()
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:old',
        old_ts,
        profile_id='digiseller',
    )
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:fresh',
        fresh_ts,
        profile_id='digiseller',
    )
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_LAST_CLEANUP_AT',
        (datetime.now() - timedelta(hours=48)).isoformat(),
        profile_id='digiseller',
    )

    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS = 30
    cfg.DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS = 1
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NoChatsApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            return []

    bot = DummyTelegramBot()
    api = NoChatsApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:old',
            profile_id='digiseller',
        ) is None
    )
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:fresh',
            profile_id='digiseller',
        ) is not None
    )
    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_LAST_CLEANUP_AT',
            profile_id='digiseller',
        ) is not None
    )


@pytest.mark.asyncio
async def test_scheduler_cleanup_removes_legacy_sent_markers_by_history_age(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:legacy',
        '1',
        profile_id='digiseller',
    )
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_LAST_CLEANUP_AT',
        (datetime.now() - timedelta(hours=48)).isoformat(),
        profile_id='digiseller',
    )

    # Помечаем запись как "старую" через settings_history timestamp.
    with sqlite3.connect(str(tmp_path / 'state.db')) as conn:
        conn.execute(
            '''
            UPDATE settings_history
            SET timestamp = ?
            WHERE profile_id = ? AND key = ?
            ''',
            (
                (datetime.now() - timedelta(days=90)).strftime(
                    '%Y-%m-%d %H:%M:%S'
                ),
                'digiseller',
                'CHAT_AUTOREPLY_SENT:legacy',
            ),
        )
        conn.commit()

    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS = 30
    cfg.DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS = 1
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NoChatsApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            return []

    bot = DummyTelegramBot()
    api = NoChatsApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:legacy',
            profile_id='digiseller',
        ) is None
    )


@pytest.mark.asyncio
async def test_scheduler_cleanup_accepts_utc_z_timestamp(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    old_utc = (
        datetime.now(timezone.utc) - timedelta(days=60)
    ).isoformat().replace('+00:00', 'Z')
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:utc',
        old_utc,
        profile_id='digiseller',
    )
    test_storage.set_runtime_setting(
        'CHAT_AUTOREPLY_LAST_CLEANUP_AT',
        (datetime.now() - timedelta(hours=48)).isoformat(),
        profile_id='digiseller',
    )

    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS = 30
    cfg.DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS = 1
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    class NoChatsApi(DummyChatApiClient):
        def list_chats(self, **kwargs):
            return []

    bot = DummyTelegramBot()
    api = NoChatsApi()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()

    assert (
        test_storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:utc',
            profile_id='digiseller',
        ) is None
    )


@pytest.mark.asyncio
async def test_scheduler_digiseller_chat_autoreply_respects_interval(
    monkeypatch,
    tmp_path,
):
    test_storage = Storage(str(tmp_path / 'state.db'))
    cfg = Config()
    cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED = True
    cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = [5077639]
    cfg.DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS = 3600
    cfg.DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES = 1
    cfg.COMPETITOR_URLS = []

    monkeypatch.setattr(scheduler_mod, 'storage', test_storage)
    monkeypatch.setattr(scheduler_mod, 'config', cfg)

    bot = DummyTelegramBot()
    api = DummyChatApiClient()
    scheduler = scheduler_mod.Scheduler(
        api_client=api,
        telegram_bot=bot,
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=5077639,
        competitor_urls=[],
    )

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert api.list_chats_calls == 2
