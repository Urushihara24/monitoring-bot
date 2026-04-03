"""Тесты scheduler для ретрая парсинга при протухших cookies."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.scheduler as scheduler_module
from src.rsc_parser import ParseResult
from src.scheduler import Scheduler


class DummyApiClient:
    """Заглушка API клиента."""


class DummyTelegramBot:
    """Заглушка Telegram бота."""


@pytest.mark.asyncio
async def test_parse_retries_without_cookies_after_expired(monkeypatch):
    """После cookies_expired должен быть retry без cookies."""
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='old_cookie=1')

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None):
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
    async def fake_sync(force_reload=False):
        return False

    async def fake_reload_backup():
        return False

    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        fake_sync,
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        fake_reload_backup,
    )
    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        lambda *args, **kwargs: None,
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert result.price == 0.3349
    assert parse_calls == ['old_cookie=1', None]


@pytest.mark.asyncio
async def test_parse_returns_error_when_retry_failed(monkeypatch):
    """Если повтор без cookies не помог, возвращаем последнюю ошибку."""
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='old_cookie=1')

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None):
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
            success=False,
            error='HTTP 403',
            url=url,
            method='stealth_requests',
            block_reason='http_403',
            status_code=403,
            cookies_expired=True,
        )

    monkeypatch.setattr(
        scheduler_module,
        'rsc_parser',
        SimpleNamespace(parse_url=fake_parse),
    )
    async def fake_sync(force_reload=False):
        return False

    async def fake_reload_backup():
        return False

    monkeypatch.setattr(
        scheduler,
        '_sync_cookies_from_env',
        fake_sync,
    )
    monkeypatch.setattr(
        scheduler,
        '_reload_cookies_from_backup',
        fake_reload_backup,
    )
    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)
    set_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        lambda *args, **kwargs: set_calls.append((args, kwargs)),
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is False
    assert result.error == 'HTTP 403'
    assert result.status_code == 403
    assert parse_calls == ['old_cookie=1', None]
    assert len(set_calls) == 1
    args, kwargs = set_calls[0]
    assert args[0] == 'COMPETITOR_COOKIES'
    assert args[1] == ''
    assert kwargs.get('source') == 'auto_clear_expired_failed'
    assert kwargs.get('profile_id') == 'ggsel'


@pytest.mark.asyncio
async def test_parse_retries_with_refreshed_cookies_before_no_cookies(monkeypatch):
    """После cookies_expired сначала пробуем свежие cookies из runtime."""
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime_cookies = {'value': 'old_cookie=1'}
    runtime = SimpleNamespace(COMPETITOR_COOKIES=runtime_cookies['value'])

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None):
        parse_calls.append(cookies)
        if len(parse_calls) == 1:
            return ParseResult(
                success=False,
                error='expired',
                url=url,
                method='stealth_requests',
                cookies_expired=True,
            )
        if cookies == 'fresh_cookie=2':
            return ParseResult(
                success=True,
                price=0.3311,
                url=url,
                method='stealth_requests',
            )
        return ParseResult(
            success=False,
            error='unexpected cookies',
            url=url,
            method='stealth_requests',
        )

    monkeypatch.setattr(
        scheduler_module,
        'rsc_parser',
        SimpleNamespace(parse_url=fake_parse),
    )

    sync_calls = []

    async def fake_sync(force_reload=False):
        sync_calls.append(force_reload)
        runtime_cookies['value'] = 'fresh_cookie=2'
        return True

    async def fake_reload_backup():
        raise AssertionError('backup reload should not be called')

    monkeypatch.setattr(scheduler, '_sync_cookies_from_env', fake_sync)
    monkeypatch.setattr(scheduler, '_reload_cookies_from_backup', fake_reload_backup)
    set_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        lambda *args, **kwargs: set_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        scheduler,
        '_runtime',
        lambda: SimpleNamespace(COMPETITOR_COOKIES=runtime_cookies['value']),
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert result.price == 0.3311
    assert parse_calls == ['old_cookie=1', 'fresh_cookie=2']
    assert sync_calls == [True]
    assert set_calls == []


@pytest.mark.asyncio
async def test_parse_clears_stale_runtime_cookies_after_no_cookie_success(
    monkeypatch,
):
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='stale_cookie=1')

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None):
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

    async def fake_sync(force_reload=False):
        return False

    async def fake_reload_backup():
        return False

    monkeypatch.setattr(scheduler, '_sync_cookies_from_env', fake_sync)
    monkeypatch.setattr(scheduler, '_reload_cookies_from_backup', fake_reload_backup)
    monkeypatch.setattr(scheduler, '_runtime', lambda: runtime)

    set_calls = []

    def fake_set_runtime_setting(key, value, **kwargs):
        set_calls.append((key, value, kwargs))

    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert parse_calls == ['stale_cookie=1', None]
    assert len(set_calls) == 1
    key, value, kwargs = set_calls[0]
    assert key == 'COMPETITOR_COOKIES'
    assert value == ''
    assert kwargs.get('profile_id') == 'ggsel'
    assert kwargs.get('source') == 'auto_clear_expired'


@pytest.mark.asyncio
async def test_parse_does_not_clear_fresh_runtime_cookies_after_retry_fail(
    monkeypatch,
):
    """
    Если в runtime уже подтянулись новые cookies, они не должны очищаться
    после неуспешного fallback без cookies.
    """
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime_cookies = {'value': 'old_cookie=1'}
    runtime = SimpleNamespace(COMPETITOR_COOKIES=runtime_cookies['value'])

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None):
        parse_calls.append(cookies)
        if len(parse_calls) == 1:
            return ParseResult(
                success=False,
                error='expired',
                url=url,
                method='stealth_requests',
                cookies_expired=True,
            )
        if len(parse_calls) == 2:
            return ParseResult(
                success=False,
                error='fresh_cookies_still_blocked',
                url=url,
                method='stealth_requests',
                cookies_expired=True,
            )
        return ParseResult(
            success=False,
            error='HTTP 403',
            url=url,
            method='stealth_requests',
            status_code=403,
            block_reason='http_403',
            cookies_expired=True,
        )

    monkeypatch.setattr(
        scheduler_module,
        'rsc_parser',
        SimpleNamespace(parse_url=fake_parse),
    )

    async def fake_sync(force_reload=False):
        runtime_cookies['value'] = 'fresh_cookie=2'
        return True

    async def fake_reload_backup():
        raise AssertionError('backup reload should not be called')

    monkeypatch.setattr(scheduler, '_sync_cookies_from_env', fake_sync)
    monkeypatch.setattr(scheduler, '_reload_cookies_from_backup', fake_reload_backup)
    monkeypatch.setattr(
        scheduler,
        '_runtime',
        lambda: SimpleNamespace(COMPETITOR_COOKIES=runtime_cookies['value']),
    )

    set_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        lambda *args, **kwargs: set_calls.append((args, kwargs)),
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is False
    assert parse_calls == ['old_cookie=1', 'fresh_cookie=2', None]
    assert set_calls == []


@pytest.mark.asyncio
async def test_parse_does_not_fallback_to_config_cookies_when_runtime_empty(
    monkeypatch,
):
    scheduler = Scheduler(DummyApiClient(), DummyTelegramBot())
    runtime = SimpleNamespace(COMPETITOR_COOKIES='')

    parse_calls = []

    def fake_parse(url, timeout=15, cookies=None):
        parse_calls.append(cookies)
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
    monkeypatch.setattr(
        scheduler_module.config,
        'COMPETITOR_COOKIES',
        'stale_from_config=1',
    )

    result = await scheduler._parse_competitor_price(
        'https://example.com/product',
        runtime=runtime,
        timeout=5,
    )

    assert result.success is True
    assert parse_calls == [None]


@pytest.mark.asyncio
async def test_sync_cookies_from_env_updates_runtime(monkeypatch, tmp_path):
    """Cookies из .env должны попадать в runtime без перезапуска."""
    env_text = (
        'GGSEL_COMPETITOR_COOKIES=fresh_cookie=1$$o6; another=2\n'
        'COMPETITOR_COOKIES=legacy_cookie=1\n'
    )
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
async def test_sync_cookies_from_custom_env_file_path(monkeypatch, tmp_path):
    """Должен читать cookies из ENV_FILE_PATH, а не только из .env."""
    env_dir = tmp_path / 'config'
    env_dir.mkdir(parents=True, exist_ok=True)
    env_path = env_dir / 'bot.env'
    env_path.write_text(
        'COMPETITOR_COOKIES=custom_cookie=77\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        scheduler_module.config,
        'ENV_FILE_PATH',
        'config/bot.env',
    )

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
    )

    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: '',
    )
    set_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        lambda key, value, **kwargs: set_calls.append((key, value, kwargs)),
    )

    synced = await scheduler._sync_cookies_from_env()

    assert synced is True
    assert len(set_calls) == 1
    key, value, kwargs = set_calls[0]
    assert key == 'COMPETITOR_COOKIES'
    assert value == 'custom_cookie=77'
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


@pytest.mark.asyncio
async def test_sync_cookies_from_env_uses_digiseller_profile_key(
    monkeypatch,
    tmp_path,
):
    """Для профиля digiseller берётся профильный ключ из .env."""
    env_text = (
        'DIGISELLER_COMPETITOR_COOKIES=dig_cookie=1\n'
        'COMPETITOR_COOKIES=shared_cookie=2\n'
    )
    (tmp_path / '.env').write_text(env_text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='digiseller',
        profile_name='DIGISELLER',
    )
    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: '',
    )
    set_calls = []
    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        lambda key, value, **kwargs: set_calls.append((key, value, kwargs)),
    )

    synced = await scheduler._sync_cookies_from_env()

    assert synced is True
    assert len(set_calls) == 1
    key, value, kwargs = set_calls[0]
    assert key == 'COMPETITOR_COOKIES'
    assert value == 'dig_cookie=1'
    assert kwargs.get('profile_id') == 'digiseller'


@pytest.mark.asyncio
async def test_sync_cookies_from_env_uses_cached_file_when_unchanged(
    monkeypatch,
    tmp_path,
):
    env_path = tmp_path / '.env'
    env_path.write_text('COMPETITOR_COOKIES=cached_cookie=1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
    )

    runtime = {'value': 'old_cookie=1'}
    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: runtime['value'],
    )

    set_calls = []

    def fake_set_runtime_setting(key, value, **kwargs):
        runtime['value'] = value
        set_calls.append((key, value, kwargs))

    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    parse_calls = {'count': 0}

    def fake_dotenv_values(_path):
        parse_calls['count'] += 1
        return {'COMPETITOR_COOKIES': 'cached_cookie=1'}

    monkeypatch.setattr(scheduler_module, 'dotenv_values', fake_dotenv_values)

    first = await scheduler._sync_cookies_from_env()
    second = await scheduler._sync_cookies_from_env()

    assert first is True
    assert second is True
    assert parse_calls['count'] == 1
    assert len(set_calls) == 1
    assert set_calls[0][1] == 'cached_cookie=1'


@pytest.mark.asyncio
async def test_sync_cookies_from_env_reloads_when_file_changed(
    monkeypatch,
    tmp_path,
):
    env_path = tmp_path / '.env'
    env_path.write_text('COMPETITOR_COOKIES=first_cookie=1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
    )

    runtime = {'value': ''}
    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: runtime['value'],
    )

    set_calls = []

    def fake_set_runtime_setting(key, value, **kwargs):
        runtime['value'] = value
        set_calls.append((key, value, kwargs))

    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    first = await scheduler._sync_cookies_from_env()
    assert first is True
    assert runtime['value'] == 'first_cookie=1'

    env_path.write_text('COMPETITOR_COOKIES=second_cookie=2\n', encoding='utf-8')
    # Гарантируем смену сигнатуры даже на FS с грубой гранулярностью mtime.
    current = env_path.stat().st_mtime + 1.0
    os.utime(env_path, (current, current))

    second = await scheduler._sync_cookies_from_env()
    assert second is True
    assert runtime['value'] == 'second_cookie=2'
    assert len(set_calls) == 2


@pytest.mark.asyncio
async def test_sync_cookies_from_env_force_reload_bypasses_cache(
    monkeypatch,
    tmp_path,
):
    env_path = tmp_path / '.env'
    env_path.write_text('COMPETITOR_COOKIES=seed_cookie=1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    scheduler = Scheduler(
        DummyApiClient(),
        DummyTelegramBot(),
        profile_id='ggsel',
        profile_name='GGSEL',
    )

    runtime = {'value': ''}
    monkeypatch.setattr(
        scheduler_module.storage,
        'get_runtime_setting',
        lambda *args, **kwargs: runtime['value'],
    )

    set_calls = []

    def fake_set_runtime_setting(key, value, **kwargs):
        runtime['value'] = value
        set_calls.append((key, value, kwargs))

    monkeypatch.setattr(
        scheduler_module.storage,
        'set_runtime_setting',
        fake_set_runtime_setting,
    )

    parse_calls = {'count': 0}

    def fake_dotenv_values(_path):
        parse_calls['count'] += 1
        if parse_calls['count'] == 1:
            return {'COMPETITOR_COOKIES': 'seed_cookie=1'}
        return {'COMPETITOR_COOKIES': 'forced_cookie=2'}

    monkeypatch.setattr(scheduler_module, 'dotenv_values', fake_dotenv_values)

    first = await scheduler._sync_cookies_from_env()
    second = await scheduler._sync_cookies_from_env(force_reload=True)

    assert first is True
    assert second is True
    assert parse_calls['count'] == 2
    assert runtime['value'] == 'forced_cookie=2'
    assert len(set_calls) == 2
