"""
RSC Parser для ggsel.net с каскадом fallback:
stealth_requests -> Playwright -> Selenium.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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
    """
    Каскадный парсер с anti-bot fallback-цепочкой.
    """

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.success_count = 0
        self.fail_count = 0
        self.method_success_count: Dict[str, int] = {}
        self.method_fail_count: Dict[str, int] = {}
        logger.info(
            'RSC Parser инициализирован '
            f'(max_retries={max_retries})'
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

    def _parse_cookie_string(self, cookies: Optional[str]) -> List[dict]:
        if not cookies:
            return []
        result = []
        for chunk in cookies.split(';'):
            chunk = chunk.strip()
            if not chunk or '=' not in chunk:
                continue
            name, value = chunk.split('=', 1)
            name = name.strip()
            value = value.strip()
            if not name or not value:
                continue
            result.append(
                {
                    'name': name,
                    'value': value,
                    'domain': '.ggsel.net',
                    'path': '/',
                }
            )
        return result

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

    def _parse_html(self, html: str, url: str) -> ParseResult:
        """
        Извлечение цены.

        Приоритет:
        1. unitsToPay/unitsToGet -> цена за 1 V-Bucks
        2. data-testid="product-price" / альтернативные price-селекторы
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
                    pass

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
                if resp.status_code in (401, 403, 429):
                    reason = f'http_{resp.status_code}'
                    return self._blocked_result(
                        url,
                        method,
                        error=f'HTTP {resp.status_code}',
                        block_reason=reason,
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

    def _parse_with_playwright(
        self,
        url: str,
        timeout: int,
        cookies: Optional[str],
    ) -> ParseResult:
        method = 'playwright'
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            return ParseResult(
                success=False,
                error=f'Playwright import error: {e}',
                url=url,
                method=method,
            )

        browser = None
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self._get_random_user_agent())
                cookie_list = self._parse_cookie_string(cookies)
                if cookie_list:
                    context.add_cookies(cookie_list)
                page = context.new_page()
                response = page.goto(
                    url,
                    wait_until='domcontentloaded',
                    timeout=timeout * 1000,
                )
                status_code = response.status if response else None
                if status_code in (401, 403, 429):
                    reason = f'http_{status_code}'
                    return self._blocked_result(
                        url,
                        method,
                        error=f'HTTP {status_code}',
                        block_reason=reason,
                        status_code=status_code,
                    )
                page.wait_for_timeout(1200)
                html = page.content()
                block_reason = self._detect_block_reason(html)
                if block_reason:
                    return self._blocked_result(
                        url,
                        method,
                        error=f'Anti-bot block detected: {block_reason}',
                        block_reason=block_reason,
                        status_code=status_code,
                    )

                result = self._parse_html(html, url)
                result.method = method
                result.status_code = status_code
                return result
        except Exception as e:
            return ParseResult(
                success=False,
                error=f'{method} exception: {e}',
                url=url,
                method=method,
            )
        finally:
            try:
                if browser is not None:
                    browser.close()
            except Exception:
                pass

    def _parse_with_selenium(
        self,
        url: str,
        timeout: int,
        cookies: Optional[str],
        *,
        use_real_profile: bool,
        user_data_dir: str,
        profile_dir: str,
        headless: bool,
    ) -> ParseResult:
        method = 'selenium'
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except Exception as e:
            return ParseResult(
                success=False,
                error=f'Selenium import error: {e}',
                url=url,
                method=method,
            )

        driver = None
        try:
            options = Options()
            if headless:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'--user-agent={self._get_random_user_agent()}')
            options.add_argument('--disable-gpu')
            options.add_argument('--remote-debugging-port=0')

            chrome_bin = os.environ.get('CHROME_BIN', '/usr/bin/chromium')
            if Path(chrome_bin).exists():
                options.binary_location = chrome_bin

            if use_real_profile and user_data_dir:
                options.add_argument(f'--user-data-dir={user_data_dir}')
                if profile_dir:
                    options.add_argument(f'--profile-directory={profile_dir}')

            chromedriver_path = os.environ.get(
                'CHROMEDRIVER',
                '/usr/bin/chromedriver',
            )
            if Path(chromedriver_path).exists():
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=options)
            else:
                driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(timeout)
            if cookies:
                driver.get('https://ggsel.net')
                for cookie in self._parse_cookie_string(cookies):
                    try:
                        driver.add_cookie(cookie)
                    except Exception:
                        continue
            driver.get(url)
            time.sleep(1.2)

            html = driver.page_source or ''
            title = (driver.title or '').lower()
            if '401' in title or '403' in title:
                code = 401 if '401' in title else 403
                reason = f'http_{code}'
                return self._blocked_result(
                    url,
                    method,
                    error=f'HTTP {code} (detected by title)',
                    block_reason=reason,
                    status_code=code,
                )

            block_reason = self._detect_block_reason(html)
            if block_reason:
                return self._blocked_result(
                    url,
                    method,
                    error=f'Anti-bot block detected: {block_reason}',
                    block_reason=block_reason,
                )

            result = self._parse_html(html, url)
            result.method = method
            return result
        except Exception as e:
            return ParseResult(
                success=False,
                error=f'{method} exception: {e}',
                url=url,
                method=method,
            )
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

    def parse_url(
        self,
        url: str,
        timeout: int = 10,
        cookies: Optional[str] = None,
        *,
        use_playwright: bool = True,
        use_selenium_fallback: bool = True,
        selenium_use_real_profile: bool = False,
        selenium_user_data_dir: str = '',
        selenium_profile_dir: str = 'Default',
        selenium_headless: bool = True,
    ) -> ParseResult:
        """
        Парсинг с каскадным fallback.
        """
        logger.info(f'🔍 НАЧАЛО ПАРСИНГА: {url}')
        started = time.time()
        attempts: List[ParseResult] = []

        stealth_result = self._parse_with_stealth(url, timeout, cookies)
        attempts.append(stealth_result)
        if stealth_result.success:
            elapsed = time.time() - started
            stealth_result.elapsed_seconds = elapsed
            self.success_count += 1
            self._inc_method_success(stealth_result.method)
            logger.info(
                '🎉 ПАРСИНГ УСПЕШЕН (stealth): '
                f'цена={stealth_result.price}₽, время={elapsed:.2f}s'
            )
            return stealth_result
        self._inc_method_fail(stealth_result.method)

        if use_playwright:
            pw_result = self._parse_with_playwright(url, timeout, cookies)
            attempts.append(pw_result)
            if pw_result.success:
                elapsed = time.time() - started
                pw_result.elapsed_seconds = elapsed
                self.success_count += 1
                self._inc_method_success(pw_result.method)
                logger.info(
                    '🎉 ПАРСИНГ УСПЕШЕН (playwright): '
                    f'цена={pw_result.price}₽, время={elapsed:.2f}s'
                )
                return pw_result
            self._inc_method_fail(pw_result.method)

        if use_selenium_fallback:
            sel_result = self._parse_with_selenium(
                url,
                timeout,
                cookies,
                use_real_profile=selenium_use_real_profile,
                user_data_dir=selenium_user_data_dir,
                profile_dir=selenium_profile_dir,
                headless=selenium_headless,
            )
            attempts.append(sel_result)
            if sel_result.success:
                elapsed = time.time() - started
                sel_result.elapsed_seconds = elapsed
                self.success_count += 1
                self._inc_method_success(sel_result.method)
                logger.info(
                    '🎉 ПАРСИНГ УСПЕШЕН (selenium): '
                    f'цена={sel_result.price}₽, время={elapsed:.2f}s'
                )
                return sel_result
            self._inc_method_fail(sel_result.method)

        self.fail_count += 1
        elapsed = time.time() - started
        last_result = attempts[-1]
        cookies_expired = any(r.cookies_expired for r in attempts)
        block_reason = next((r.block_reason for r in attempts if r.block_reason), None)
        status_code = next((r.status_code for r in attempts if r.status_code), None)
        error_chain = ' | '.join(
            f'{r.method}: {r.error}' for r in attempts if r.error
        ) or 'Все методы парсинга исчерпаны'

        logger.warning(
            '❌ ПАРСИНГ НЕ УДАЛСЯ: время=%.2fs, fail_count=%s, error=%s',
            elapsed,
            self.fail_count,
            error_chain,
        )
        return ParseResult(
            success=False,
            error=error_chain,
            url=url,
            method=last_result.method if last_result else 'all_failed',
            cookies_expired=cookies_expired,
            block_reason=block_reason,
            status_code=status_code,
            elapsed_seconds=elapsed,
        )

    def get_stats(self) -> dict:
        total = self.success_count + self.fail_count
        return {
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'success_rate': (
                round(self.success_count / total * 100, 2) if total > 0 else 0
            ),
            'method_success_count': dict(self.method_success_count),
            'method_fail_count': dict(self.method_fail_count),
        }

    def reset_stats(self):
        self.fail_count = 0
        self.success_count = 0
        self.method_success_count.clear()
        self.method_fail_count.clear()


rsc_parser = RSCParser(max_retries=2)
