"""Competitor parser coordination for scheduler runtimes.

This module owns the retry/cookie-refresh policy around ``rsc_parser`` so the
runtime scheduler can focus on orchestration and pricing decisions. It does
not change parser semantics, pricing rules, seller writes or persisted-state
meaning.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from .rsc_parser import ParseResult, rsc_parser
from .storage import storage

logger = logging.getLogger(__name__)


class ParserCoordinator:
    """Coordinate one competitor parse including cookie refresh/fallbacks."""

    def __init__(
        self,
        *,
        profile_id: str,
        profile_name: str,
        runtime_loader: Callable[[], Any],
        sync_cookies_from_env: Callable[..., Awaitable[bool]],
        reload_cookies_from_backup: Callable[[], Awaitable[bool]],
        parser: Any = rsc_parser,
        runtime_storage: Any = storage,
    ) -> None:
        self.profile_id = profile_id
        self.profile_name = profile_name
        self._runtime_loader = runtime_loader
        self._sync_cookies_from_env = sync_cookies_from_env
        self._reload_cookies_from_backup = reload_cookies_from_backup
        self._parser = parser
        self._storage = runtime_storage

    async def parse_competitor_price(
        self,
        url: str,
        runtime: Any,
        timeout: int = 15,
    ) -> ParseResult:
        """Parse one competitor URL while preserving historical retry policy."""
        logger.info('[%s] 🔍 Парсинг цены: %s', self.profile_name, url)

        # Use cookies only from current runtime state. Falling back to process
        # config here can resurrect credentials that were intentionally cleared.
        cookies = runtime.COMPETITOR_COOKIES or None
        try:
            host = (urlparse(url).hostname or '').lower()
        except Exception:
            host = ''

        if (
            host in ('plati.market', 'digiseller.market')
            or host.endswith('.plati.market')
            or host.endswith('.digiseller.market')
        ):
            if cookies:
                logger.info(
                    '[%s] Для %s парсим без cookies (избежание 403 anti-bot)',
                    self.profile_name,
                    host,
                )
            cookies = None

        result = await asyncio.to_thread(
            self._parser.parse_url,
            url,
            timeout=timeout,
            cookies=cookies,
        )
        if result.success:
            return result

        if result.cookies_expired and cookies:
            logger.warning(
                '[%s] Cookies протухли для %s, пробую обновить cookies...',
                self.profile_name,
                url,
            )
            synced_from_env = await self._sync_cookies_from_env(
                force_reload=True,
            )
            if not synced_from_env:
                await self._reload_cookies_from_backup()

            refreshed_runtime = self._runtime_loader()
            refreshed_cookies = refreshed_runtime.COMPETITOR_COOKIES or None
            if refreshed_cookies and refreshed_cookies != cookies:
                logger.info(
                    '[%s] Использую обновлённые cookies из runtime '
                    'и повторяю парсинг',
                    self.profile_name,
                )
                refreshed_result = await asyncio.to_thread(
                    self._parser.parse_url,
                    url,
                    timeout=timeout,
                    cookies=refreshed_cookies,
                )
                if refreshed_result.success:
                    return refreshed_result
                result = refreshed_result

            logger.warning(
                '[%s] Повторяю парсинг без cookies для %s...',
                self.profile_name,
                url,
            )
            retry_result = await asyncio.to_thread(
                self._parser.parse_url,
                url,
                timeout=timeout,
                cookies=None,
            )
            if retry_result.success:
                if (
                    cookies
                    and (
                        not refreshed_cookies
                        or refreshed_cookies == cookies
                    )
                ):
                    self._clear_expired_cookies('auto_clear_expired')
                return retry_result

            if (
                cookies
                and (
                    not refreshed_cookies
                    or refreshed_cookies == cookies
                )
            ):
                self._clear_expired_cookies('auto_clear_expired_failed')
            result = retry_result

        return result

    def _clear_expired_cookies(self, source: str) -> None:
        self._storage.set_runtime_setting(
            'COMPETITOR_COOKIES',
            '',
            source=source,
            profile_id=self.profile_id,
        )
        logger.info(
            '[%s] Очистил протухшие runtime cookies (source=%s)',
            self.profile_name,
            source,
        )
