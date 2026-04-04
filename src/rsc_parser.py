"""RSC parser for ggsel.net based on stealth_requests + BeautifulSoup."""

from __future__ import annotations

import logging
import random
import re
import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

import stealth_requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Offer:
    """Оффер продавца."""

    price: float
    seller_name: str = ''
    rating: float = 0.0
    reviews_count: int = 0


@dataclass
class ParseResult:
    """Результат парсинга цены."""

    success: bool
    price: Optional[float] = None
    error: Optional[str] = None
    url: str = ''
    offers: List[Offer] = field(default_factory=list)
    rank: Optional[int] = None
    method: str = 'unknown'
    cookies_expired: bool = False
    block_reason: Optional[str] = None
    status_code: Optional[int] = None
    elapsed_seconds: Optional[float] = None


USER_AGENTS = [
    (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/121.0.0.0 Safari/537.36'
    ),
    (
        'Mozilla/5.0 (X11; Linux x86_64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/121.0.0.0 Safari/537.36'
    ),
    (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) '
        'Gecko/20100101 Firefox/122.0'
    ),
]

BLOCK_MARKERS = {
    'captcha': ['captcha', 'hcaptcha', 'recaptcha'],
    'qrator': ['qrator'],
    'cloudflare': ['cloudflare', 'checking your browser', 'attention required'],
    'access_denied': ['access denied', 'forbidden', 'not authorized'],
    'javascript_challenge': ['please turn javascript on'],
}


class RSCParser:
    """RSC parser with anti-bot detection and retry logic."""

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.success_count = 0
        self.fail_count = 0
        self.method_success_count: Dict[str, int] = {}
        self.method_fail_count: Dict[str, int] = {}
        logger.info(
            'RSC Parser initialized (max_retries=%s)',
            max_retries,
        )

    def _inc_method_success(self, method: str):
        self.method_success_count[method] = (
            self.method_success_count.get(method, 0) + 1
        )

    def _inc_method_fail(self, method: str):
        self.method_fail_count[method] = (
            self.method_fail_count.get(method, 0) + 1
        )

    def _get_random_user_agent(self) -> str:
        return random.choice(USER_AGENTS)

    def _build_headers(self, cookies: Optional[str]) -> dict:
        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,*/*;q=0.8'
            ),
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        if cookies:
            headers['Cookie'] = cookies
        return headers

    def _detect_block_reason(self, html: str) -> Optional[str]:
        html_lower = html.lower()
        for reason, markers in BLOCK_MARKERS.items():
            for marker in markers:
                if marker in html_lower:
                    return reason
        return None

    def _cookies_expired_by_reason(self, reason: Optional[str]) -> bool:
        return reason in {
            'captcha',
            'qrator',
            'cloudflare',
            'access_denied',
            'javascript_challenge',
            'http_401',
            'http_403',
        }

    def _parse_price_from_text(self, text: str) -> Optional[float]:
        cleaned = text.replace('\xa0', ' ').replace(',', '.')
        m = re.search(r'(\d+(?:\.\d{1,6})?)\s*(?:₽|rub)?', cleaned, re.IGNORECASE)
        if not m:
            return None
        try:
            price = float(m.group(1))
            if price > 0:
                return round(price, 4)
        except ValueError:
            return None
        return None

    def _coerce_price(self, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                price = float(value)
                if price > 0:
                    return round(price, 4)
            except Exception:
                return None
            return None
        if isinstance(value, str):
            return self._parse_price_from_text(value)
        return None

    def _extract_price_from_json_ld_node(self, node) -> Optional[float]:
        if isinstance(node, list):
            for item in node:
                parsed = self._extract_price_from_json_ld_node(item)
                if parsed is not None:
                    return parsed
            return None

        if not isinstance(node, dict):
            return None

        direct_price = self._coerce_price(node.get('price'))
        if direct_price is not None:
            return direct_price

        for offers_key in ('offers', 'offer'):
            offers = node.get(offers_key)
            parsed = self._extract_price_from_json_ld_node(offers)
            if parsed is not None:
                return parsed

        for nested_key in ('mainEntity', 'itemOffered'):
            nested = node.get(nested_key)
            parsed = self._extract_price_from_json_ld_node(nested)
            if parsed is not None:
                return parsed

        return None

    def _extract_price_from_json_ld(self, soup: BeautifulSoup) -> Optional[float]:
        for script in soup.select('script[type="application/ld+json"]'):
            raw = (script.string or script.get_text() or '').strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            parsed = self._extract_price_from_json_ld_node(payload)
            if parsed is not None:
                return parsed
        return None

    def _extract_price_from_meta(self, soup: BeautifulSoup) -> Optional[float]:
        meta_keys = (
            'product:price:amount',
            'og:price:amount',
            'price',
        )
        for key in meta_keys:
            node = soup.find(
                'meta',
                attrs={'property': key},
            ) or soup.find(
                'meta',
                attrs={'name': key},
            )
            if not node:
                continue
            parsed = self._coerce_price(node.get('content'))
            if parsed is not None:
                return parsed
        return None

    def _parse_html(self, html: str, url: str) -> ParseResult:
        """
        Извлечение цены.

        Приоритет:
        1. unitsToPay/unitsToGet -> цена за 1 V-Bucks
        2. JSON-LD offers.price
        3. meta product:price:amount / og:price:amount
        4. data-testid="product-price" / альтернативные price-селекторы
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            units_to_pay = soup.find('input', {'name': 'unitsToPay'})
            units_to_get = soup.find('input', {'name': 'unitsToGet'})
            if units_to_pay and units_to_get:
                try:
                    total_price = float(units_to_pay.get('value', '0'))
                    units = int(units_to_get.get('value', '0'))
                    if total_price > 0 and units > 0:
                        unit_price = round(total_price / units, 4)
                        return ParseResult(
                            success=True,
                            price=unit_price,
                            url=url,
                            offers=[Offer(price=unit_price)],
                        )
                except (ValueError, TypeError):
                    logger.debug(
                        'Некорректные unitsToPay/unitsToGet: %r / %r',
                        units_to_pay.get('value'),
                        units_to_get.get('value'),
                    )

            json_ld_price = self._extract_price_from_json_ld(soup)
            if json_ld_price is not None:
                return ParseResult(
                    success=True,
                    price=json_ld_price,
                    url=url,
                    offers=[Offer(price=json_ld_price)],
                )

            meta_price = self._extract_price_from_meta(soup)
            if meta_price is not None:
                return ParseResult(
                    success=True,
                    price=meta_price,
                    url=url,
                    offers=[Offer(price=meta_price)],
                )

            selectors = [
                '[data-testid="product-price"]',
                '[data-test="productPrice"]',
                '.ProductBuyBlock-module-scss-module__Tn6mfa__amount',
                '.product-price',
                '.price',
                '[data-price]',
            ]
            for selector in selectors:
                node = soup.select_one(selector)
                if not node:
                    continue
                price = self._parse_price_from_text(node.get_text(strip=True))
                if price is not None:
                    return ParseResult(
                        success=True,
                        price=price,
                        url=url,
                        offers=[Offer(price=price)],
                    )

            return ParseResult(
                success=False,
                error='Цена не найдена в HTML',
                url=url,
            )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f'Ошибка парсинга HTML: {e}',
                url=url,
            )

    def _blocked_result(
        self,
        url: str,
        method: str,
        *,
        error: str,
        block_reason: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> ParseResult:
        return ParseResult(
            success=False,
            error=error,
            url=url,
            method=method,
            block_reason=block_reason,
            status_code=status_code,
            cookies_expired=self._cookies_expired_by_reason(block_reason),
        )

    def _parse_with_stealth(
        self,
        url: str,
        timeout: int,
        cookies: Optional[str],
    ) -> ParseResult:
        method = 'stealth_requests'
        headers = self._build_headers(cookies)
        for attempt in range(self.max_retries + 1):
            try:
                resp = stealth_requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                )
                if resp.status_code in (401, 403):
                    reason = f'http_{resp.status_code}'
                    return self._blocked_result(
                        url,
                        method,
                        error=f'HTTP {resp.status_code}',
                        block_reason=reason,
                        status_code=resp.status_code,
                    )
                if resp.status_code == 429:
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                        headers['User-Agent'] = self._get_random_user_agent()
                        continue
                    return self._blocked_result(
                        url,
                        method,
                        error='HTTP 429',
                        block_reason='http_429',
                        status_code=resp.status_code,
                    )
                if resp.status_code != 200:
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                        headers['User-Agent'] = self._get_random_user_agent()
                        continue
                    return ParseResult(
                        success=False,
                        error=f'HTTP {resp.status_code}',
                        url=url,
                        method=method,
                        status_code=resp.status_code,
                    )

                block_reason = self._detect_block_reason(resp.text)
                if block_reason:
                    return self._blocked_result(
                        url,
                        method,
                        error=f'Anti-bot block detected: {block_reason}',
                        block_reason=block_reason,
                    )

                result = self._parse_html(resp.text, url)
                result.method = method
                result.status_code = resp.status_code
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    headers['User-Agent'] = self._get_random_user_agent()
                    continue
                return ParseResult(
                    success=False,
                    error=f'{method} exception: {e}',
                    url=url,
                    method=method,
                )
        return ParseResult(
            success=False,
            error='stealth_requests exhausted',
            url=url,
            method=method,
        )

    def _extract_goods_id(self, url: str) -> Optional[str]:
        match = re.search(r'-(\d+)(?:[/?#]|$)', url)
        if not match:
            return None
        return match.group(1)

    def _is_ggsel_domain(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or '').lower()
        except Exception:
            return False
        if not host:
            return False
        allowed = ('ggsel.net', 'ggsel.com')
        return any(host == domain or host.endswith(f'.{domain}') for domain in allowed)

    def _parse_with_goods_api(self, url: str, timeout: int) -> ParseResult:
        """
        Fallback через публичный endpoint api4.ggsel.com/goods/<id>.
        """
        method = 'api4_goods'
        goods_id = self._extract_goods_id(url)
        if not goods_id:
            return ParseResult(
                success=False,
                error='Не удалось извлечь id товара из URL',
                url=url,
                method=method,
            )

        api_url = f'https://api4.ggsel.com/goods/{goods_id}'
        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'application/json,text/plain,*/*',
        }
        try:
            resp = stealth_requests.get(
                api_url,
                headers=headers,
                timeout=timeout,
            )
            if resp.status_code != 200:
                return ParseResult(
                    success=False,
                    error=f'API fallback HTTP {resp.status_code}',
                    url=url,
                    method=method,
                    status_code=resp.status_code,
                )

            payload = resp.json()
            if not isinstance(payload, dict):
                return ParseResult(
                    success=False,
                    error='API fallback: invalid JSON payload',
                    url=url,
                    method=method,
                )
            data = payload.get('data') or {}
            price = None
            prices_unit = data.get('prices_unit')
            if isinstance(prices_unit, dict):
                # Для товаров с количеством (например V-Bucks) приоритетнее
                # unit_amount — это цена за 1 единицу.
                price = self._coerce_price(prices_unit.get('unit_amount'))
                if price is None:
                    price = self._coerce_price(prices_unit.get('unit_amount_min'))

            if price is None:
                price = self._coerce_price(data.get('price'))

            if price is None:
                return ParseResult(
                    success=False,
                    error='API fallback: поле price отсутствует',
                    url=url,
                    method=method,
                )
            if price <= 0:
                return ParseResult(
                    success=False,
                    error='API fallback: невалидная цена',
                    url=url,
                    method=method,
                )

            return ParseResult(
                success=True,
                price=price,
                url=url,
                offers=[Offer(price=price)],
                method=method,
                status_code=resp.status_code,
            )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f'API fallback exception: {e}',
                url=url,
                method=method,
            )

    def parse_url(
        self,
        url: str,
        timeout: int = 10,
        cookies: Optional[str] = None,
    ) -> ParseResult:
        """Parse URL using stealth_requests with public API fallback."""
        logger.info(f'🔍 НАЧАЛО ПАРСИНГА: {url}')
        started = time.time()
        result = self._parse_with_stealth(url, timeout, cookies)
        if result.success:
            elapsed = time.time() - started
            result.elapsed_seconds = elapsed
            self.success_count += 1
            self._inc_method_success(result.method)
            logger.info(
                '🎉 ПАРСИНГ УСПЕШЕН: цена=%s₽, время=%.2fs',
                result.price,
                elapsed,
            )
            return result

        self._inc_method_fail(result.method)

        if not self._is_ggsel_domain(url):
            self.fail_count += 1
            elapsed = time.time() - started
            result.elapsed_seconds = elapsed
            logger.warning(
                '❌ ПАРСИНГ НЕ УДАЛСЯ: время=%.2fs, fail_count=%s, error=%s',
                elapsed,
                self.fail_count,
                result.error,
            )
            return result

        api_result = self._parse_with_goods_api(url, timeout)
        if api_result.success:
            elapsed = time.time() - started
            api_result.elapsed_seconds = elapsed
            self.success_count += 1
            self._inc_method_success(api_result.method)
            logger.info(
                '🎉 ПАРСИНГ УСПЕШЕН (api fallback): цена=%s₽, время=%.2fs',
                api_result.price,
                elapsed,
            )
            return api_result
        self._inc_method_fail(api_result.method)

        self.fail_count += 1
        elapsed = time.time() - started
        if api_result.error:
            base_error = result.error or 'stealth parse failed'
            result.error = f'{base_error} | {api_result.error}'
        result.elapsed_seconds = elapsed
        logger.warning(
            '❌ ПАРСИНГ НЕ УДАЛСЯ: время=%.2fs, fail_count=%s, error=%s',
            elapsed,
            self.fail_count,
            result.error,
        )
        return result

rsc_parser = RSCParser(max_retries=2)
