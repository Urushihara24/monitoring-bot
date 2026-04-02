"""Тесты устойчивости scheduler при протухании cookies."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.scheduler as scheduler_module
from src.distill_parser import DistillResult
from src.rsc_parser import ParseResult
from src.scheduler import Scheduler


class DummyApiClient:
    """Заглушка API клиента."""


class DummyTelegramBot:
    """Заглушка Telegram бота."""


@pytest.mark.asyncio
async def test_parse_retries_after_cookie_refresh(monkeypatch):
    """После успешного refresh cookies должен быть retry парсинга."""
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='old_cookie=1')

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None, **kwargs):
        parse_calls.append(cookies)
        if len(parse_calls) == 1:
            return ParseResult(
                success=False,
                error='expired',
                url=url,
                method='stealth_requests',
                cookies_expired=True,
            )
        return ParseResult(
            success=True,
            price=0.3349,
            url=url,
            method='stealth_requests',
        )

    monkeypatch.setattr(
        scheduler_module,
        'rsc_parser',
        SimpleNamespace(parse_url=fake_parse),
    )
    monkeypatch.setattr(scheduler_module.config, 'AUTO_UPDATE_COOKIES', True)
    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_config',
        lambda *_args, **_kwargs: SimpleNamespace(
            COMPETITOR_COOKIES='fresh_cookie=1',
            RSC_USE_PLAYWRIGHT=True,
            RSC_USE_SELENIUM_FALLBACK=True,
            SELENIUM_USE_REAL_PROFILE=False,
            SELENIUM_CHROME_USER_DATA_DIR='',
            SELENIUM_CHROME_PROFILE_DIR='Default',
            SELENIUM_HEADLESS=True,
        ),
    )

    refresh_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, '_update_cookies_now', refresh_mock)

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert result.price == 0.3349
    assert parse_calls == ['old_cookie=1', 'fresh_cookie=1']
    refresh_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_uses_distill_fallback_when_refresh_failed(monkeypatch):
    """Если refresh не удался, должен сработать Distill fallback."""
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='old_cookie=1')

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None, **kwargs):
        parse_calls.append(cookies)
        return ParseResult(
            success=False,
            error='expired',
            url=url,
            method='stealth_requests',
            cookies_expired=True,
        )

    monkeypatch.setattr(
        scheduler_module,
        'rsc_parser',
        SimpleNamespace(parse_url=fake_parse),
    )
    monkeypatch.setattr(scheduler_module.config, 'AUTO_UPDATE_COOKIES', True)

    refresh_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(scheduler, '_update_cookies_now', refresh_mock)
    scheduler.distill = SimpleNamespace(
        api_key='distill_key',
        local_data_dir=None,
        get_price=lambda _url, timeout=10: DistillResult(
            success=True,
            price=0.3210,
            method='cloud_api',
        ),
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert result.price == 0.321
    assert result.method == 'distill_cloud_api'
    assert parse_calls == ['old_cookie=1']
    refresh_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_skips_refresh_when_auto_update_disabled(monkeypatch):
    """При AUTO_UPDATE_COOKIES=false refresh не должен запускаться."""
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='old_cookie=1')

    def fake_parse(url, timeout=15, cookies=None, **kwargs):
        return ParseResult(
            success=False,
            error='expired',
            url=url,
            method='stealth_requests',
            cookies_expired=True,
        )

    monkeypatch.setattr(
        scheduler_module,
        'rsc_parser',
        SimpleNamespace(parse_url=fake_parse),
    )
    monkeypatch.setattr(scheduler_module.config, 'AUTO_UPDATE_COOKIES', False)

    refresh_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, '_update_cookies_now', refresh_mock)
    scheduler.distill = SimpleNamespace(
        api_key='distill_key',
        local_data_dir=None,
        get_price=lambda _url, timeout=10: DistillResult(
            success=True,
            price=0.315,
            method='cloud_api',
        ),
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert result.price == 0.315
    refresh_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_cookies_from_env_updates_runtime(monkeypatch, tmp_path):
    """Cookies из .env должны попадать в runtime без перезапуска."""
    env_text = 'COMPETITOR_COOKIES=fresh_cookie=1$$o6; another=2\n'
    (tmp_path / '.env').write_text(env_text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
    )

    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: 'old_cookie=1',
    )
    set_calls = []

    def fake_set_runtime_setting(key, value, **kwargs):
        set_calls.append((key, value, kwargs))

    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    synced = await scheduler._sync_cookies_from_env()

    assert synced is True
    assert len(set_calls) == 1
    key, value, kwargs = set_calls[0]
    assert key == 'COMPETITOR_COOKIES'
    assert value == 'fresh_cookie=1$o6; another=2'
    assert kwargs.get('profile_id') == 'ggsel'
    assert kwargs.get('source') == 'env_sync'


@pytest.mark.asyncio
async def test_sync_cookies_from_env_no_runtime_write_when_same(
    monkeypatch,
    tmp_path,
):
    """Если cookies в .env не изменились, runtime не должен перезаписываться."""
    env_text = 'COMPETITOR_COOKIES=same_cookie=1\n'
    (tmp_path / '.env').write_text(env_text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
    )

    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: 'same_cookie=1',
    )

    set_mock = Mock()
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        set_mock,
    )

    synced = await scheduler._sync_cookies_from_env()

    assert synced is True
    set_mock.assert_not_called()
