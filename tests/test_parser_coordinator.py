from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modular_scheduler import ModularScheduler
from src.parser_coordinator import ParserCoordinator
from src.rsc_parser import ParseResult


class FakeParser:
    def __init__(self, results: list[ParseResult]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, object]] = []

    def parse_url(self, url: str, *, timeout: int, cookies):
        self.calls.append(
            {
                'url': url,
                'timeout': timeout,
                'cookies': cookies,
            }
        )
        return self._results.pop(0)


class FakeStorage:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    def set_runtime_setting(
        self,
        key: str,
        value: str,
        *,
        source: str,
        profile_id: str,
    ) -> None:
        self.writes.append(
            {
                'key': key,
                'value': value,
                'source': source,
                'profile_id': profile_id,
            }
        )


def _coordinator(
    *,
    parser: FakeParser,
    runtime_loader,
    sync_result: bool = False,
    backup_result: bool = False,
    storage: FakeStorage | None = None,
):
    sync_calls: list[bool] = []
    backup_calls: list[bool] = []

    async def sync_cookies_from_env(*, force_reload: bool = False) -> bool:
        sync_calls.append(force_reload)
        return sync_result

    async def reload_cookies_from_backup() -> bool:
        backup_calls.append(True)
        return backup_result

    coordinator = ParserCoordinator(
        profile_id='ggsel',
        profile_name='GGSEL',
        runtime_loader=runtime_loader,
        sync_cookies_from_env=sync_cookies_from_env,
        reload_cookies_from_backup=reload_cookies_from_backup,
        parser=parser,
        runtime_storage=storage or FakeStorage(),
    )
    return coordinator, sync_calls, backup_calls


@pytest.mark.asyncio
async def test_plati_market_is_parsed_without_runtime_cookies():
    parser = FakeParser(
        [ParseResult(success=True, price=1.23, method='fixture')]
    )
    runtime = SimpleNamespace(COMPETITOR_COOKIES='secret-cookie')
    coordinator, sync_calls, backup_calls = _coordinator(
        parser=parser,
        runtime_loader=lambda: runtime,
    )

    result = await coordinator.parse_competitor_price(
        'https://plati.market/itm/example/1',
        runtime,
    )

    assert result.success is True
    assert parser.calls == [
        {
            'url': 'https://plati.market/itm/example/1',
            'timeout': 15,
            'cookies': None,
        }
    ]
    assert sync_calls == []
    assert backup_calls == []


@pytest.mark.asyncio
async def test_expired_cookies_refresh_from_runtime_before_no_cookie_fallback():
    parser = FakeParser(
        [
            ParseResult(
                success=False,
                error='expired',
                cookies_expired=True,
                method='fixture',
            ),
            ParseResult(success=True, price=0.44, method='fixture-refreshed'),
        ]
    )
    initial_runtime = SimpleNamespace(COMPETITOR_COOKIES='old-cookie')
    refreshed_runtime = SimpleNamespace(COMPETITOR_COOKIES='new-cookie')
    coordinator, sync_calls, backup_calls = _coordinator(
        parser=parser,
        runtime_loader=lambda: refreshed_runtime,
        sync_result=True,
    )

    result = await coordinator.parse_competitor_price(
        'https://ggsel.net/catalog/product/1',
        initial_runtime,
    )

    assert result.success is True
    assert [call['cookies'] for call in parser.calls] == [
        'old-cookie',
        'new-cookie',
    ]
    assert sync_calls == [True]
    assert backup_calls == []


@pytest.mark.asyncio
async def test_successful_no_cookie_retry_clears_stale_runtime_cookie():
    parser = FakeParser(
        [
            ParseResult(
                success=False,
                error='expired',
                cookies_expired=True,
                method='fixture',
            ),
            ParseResult(success=True, price=0.45, method='fixture-no-cookie'),
        ]
    )
    storage = FakeStorage()
    runtime = SimpleNamespace(COMPETITOR_COOKIES='old-cookie')
    coordinator, sync_calls, backup_calls = _coordinator(
        parser=parser,
        runtime_loader=lambda: runtime,
        sync_result=False,
        backup_result=False,
        storage=storage,
    )

    result = await coordinator.parse_competitor_price(
        'https://ggsel.net/catalog/product/2',
        runtime,
    )

    assert result.success is True
    assert [call['cookies'] for call in parser.calls] == [
        'old-cookie',
        None,
    ]
    assert sync_calls == [True]
    assert backup_calls == [True]
    assert storage.writes == [
        {
            'key': 'COMPETITOR_COOKIES',
            'value': '',
            'source': 'auto_clear_expired',
            'profile_id': 'ggsel',
        }
    ]


@pytest.mark.asyncio
async def test_modular_scheduler_delegates_parse_to_component(monkeypatch):
    scheduler = ModularScheduler(
        object(),
        object(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=123,
    )
    expected = ParseResult(success=True, price=0.5, method='delegated')
    calls: list[tuple[str, object, int]] = []

    async def fake_parse(url: str, runtime, timeout: int = 15):
        calls.append((url, runtime, timeout))
        return expected

    monkeypatch.setattr(
        scheduler._parser_coordinator,
        'parse_competitor_price',
        fake_parse,
    )
    runtime = SimpleNamespace(COMPETITOR_COOKIES='')

    result = await scheduler._parse_competitor_price(
        'https://ggsel.net/catalog/product/3',
        runtime,
        timeout=9,
    )

    assert result is expected
    assert calls == [
        ('https://ggsel.net/catalog/product/3', runtime, 9),
    ]
