"""
RSC Parser для ggsel.net

Использует:
1. stealth_requests (основной метод)
2. Ротация user-agent для обхода anti-bot
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional, List

import stealth_requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Offer:
    """Оффер продавца"""
    price: float
    seller_name: str = ""
    rating: float = 0.0
    reviews_count: int = 0


@dataclass
class ParseResult:
    """Результат парсинга"""
    success: bool
    price: Optional[float] = None
    error: Optional[str] = None
    url: str = ""
    offers: List[Offer] = None
    rank: Optional[int] = None
    method: str = "unknown"
    cookies_expired: bool = False  # Флаг: cookies протухли (401/403/капча)


# User-Agent пул для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class RSCParser:
    """
    Парсер через stealth_requests

    Стратегия:
    1. Запрос через stealth_requests с ротацией UA
    2. Retry logic с экспоненциальной задержкой
    3. Кэширование cookies
    """

    def __init__(self, max_retries: int = 2):
        self.fail_count = 0
        self.success_count = 0
        self.max_retries = max_retries
        logger.info(f"RSC Parser инициализирован (max_retries={max_retries})")

    def _get_random_user_agent(self) -> str:
        """Случайный user-agent из пула"""
        return random.choice(USER_AGENTS)

    def _detect_cookies_expired(self, html: str) -> bool:
        """
        Детекция протухших cookies по HTML-контенту

        Признаки:
        - "Access Denied", "403 Forbidden", "401 Unauthorized"
        - CAPTCHA, QRATOR, Cloudflare challenge
        - Страница с ошибкой доступа
        """
        html_lower = html.lower()

        # Маркеры блокировки доступа
        markers = [
            'access denied',
            '403 forbidden',
            '401 unauthorized',
            'captcha',
            'qrator',
            'cloudflare',
            'checking your browser',
            'ddos protection',
            'attention required',
            'please turn javascript on',
        ]

        for marker in markers:
            if marker in html_lower:
                logger.warning(f"🚫 Детектирована блокировка: '{marker}'")
                return True

        return False

    def _get_headers(self, cookies: Optional[str] = None) -> dict:
        """Заголовки для запроса"""
        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        if cookies:
            headers['Cookie'] = cookies
        return headers

    def _parse_html(self, html: str, url: str) -> ParseResult:
        """Парсинг HTML и извлечение цены"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем input поля с ценой и количеством V-Bucks
            units_to_pay = soup.find('input', {'name': 'unitsToPay'})
            units_to_get = soup.find('input', {'name': 'unitsToGet'})

            if not units_to_pay:
                logger.warning("⚠️ Input поле 'unitsToPay' не найдено")
                # Пробуем альтернативные селекторы
                price_elem = soup.select_one('.product-price, .price, [data-price]')
                if price_elem:
                    try:
                        price_text = price_elem.get_text().strip()
                        price = float(price_text.replace('₽', '').replace('RUB', '').strip())
                        logger.info(f"✅ Цена найдена через альтернативный селектор: {price}")
                        return ParseResult(success=True, price=price, url=url, method="alt_selector")
                    except (ValueError, AttributeError):
                        pass
                return ParseResult(success=False, error="Input поле 'unitsToPay' не найдено", url=url, method="beautifulsoup")

            if not units_to_get:
                logger.warning("⚠️ Input поле 'unitsToGet' не найдено")
                return ParseResult(success=False, error="Input поле 'unitsToGet' не найдено", url=url, method="beautifulsoup")

            # Получаем значения
            try:
                min_price = float(units_to_pay.get('value', '0'))
                vbucks_amount = int(units_to_get.get('value', '0'))
            except ValueError as e:
                logger.warning(f"❌ Некорректные значения: {e}")
                return ParseResult(success=False, error="Некорректные значения", url=url, method="beautifulsoup")

            if min_price <= 0 or vbucks_amount <= 0:
                logger.warning(f"❌ Некорректные значения: min_price={min_price}, vbucks={vbucks_amount}")
                return ParseResult(success=False, error="Некорректные значения", url=url, method="beautifulsoup")

            # Считаем цену за 1 V-Buck
            price_per_vbuck = round(min_price / vbucks_amount, 4)

            return ParseResult(
                success=True,
                price=price_per_vbuck,
                url=url,
                offers=[Offer(price=price_per_vbuck)],
                method="beautifulsoup"
            )
            
        except Exception as e:
            logger.error(f"Ошибка парсинга HTML: {e}", exc_info=True)
            return ParseResult(success=False, error=str(e), url=url, method="beautifulsoup")

    def parse_url(self, url: str, timeout: int = 10, cookies: Optional[str] = None) -> ParseResult:
        """
        Парсинг цены

        Args:
            url: URL товара
            timeout: Таймаут запроса в секундах
            cookies: Cookies для запроса (опционально)

        Returns:
            ParseResult с ценой или ошибкой
        """
        logger.info(f"🔍 НАЧАЛО ПАРСИНГА: {url}")
        start_time = time.time()

        # === ПОПЫТКА: stealth_requests с cookies ===
        headers = self._get_headers(cookies)

        for attempt in range(self.max_retries + 1):
            try:
                resp = stealth_requests.get(url, headers=headers, timeout=timeout)

                # === ДЕТЕКЦИЯ ПРОТУХШИХ COOKIES ПО СТАТУСУ ===
                if resp.status_code in (401, 403):
                    logger.warning(f"🚫 Cookies протухли: HTTP {resp.status_code}")
                    return ParseResult(
                        success=False,
                        error=f"HTTP {resp.status_code} (cookies expired)",
                        url=url,
                        method="stealth_requests",
                        cookies_expired=True
                    )

                if resp.status_code == 429:
                    logger.warning(f"Rate limit (429) для {url}")
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return ParseResult(success=False, error="Rate limit (429)", url=url, method="stealth_requests")

                if resp.status_code != 200:
                    logger.warning(f"HTTP {resp.status_code} для {url}")
                    if attempt < self.max_retries:
                        time.sleep(1)
                        headers['User-Agent'] = self._get_random_user_agent()
                        continue
                    return ParseResult(success=False, error=f"HTTP {resp.status_code}", url=url, method="stealth_requests")

                # === ДЕТЕКЦИЯ ПРОТУХШИХ COOKIES ПО HTML ===
                if self._detect_cookies_expired(resp.text):
                    logger.warning("🚫 Cookies протухли: детектировано по HTML-контенту")
                    return ParseResult(
                        success=False,
                        error="Cookies expired (detected by HTML content)",
                        url=url,
                        method="stealth_requests",
                        cookies_expired=True
                    )

                # Парсим HTML
                result = self._parse_html(resp.text, url)

                if result.success:
                    self.success_count += 1
                    elapsed = time.time() - start_time
                    logger.info(f"🎉 ПАРСИНГ УСПЕШЕН: цена={result.price}₽, время={elapsed:.2f}s")
                    result.method = "stealth_requests"
                    return result

                # Если парсинг не удался, не повторяем
                return result

            except Exception as e:
                logger.warning(f"Попытка {attempt + 1} не удалась: {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    headers['User-Agent'] = self._get_random_user_agent()
                else:
                    logger.error(f"Все попытки исчерпаны: {e}")

        # === НЕУДАЧА ===
        self.fail_count += 1
        elapsed = time.time() - start_time
        logger.warning(f"❌ ПАРСИНГ НЕ УДАЛСЯ: время={elapsed:.2f}s, fail_count={self.fail_count}")

        return ParseResult(
            success=False,
            error="Все методы парсинга исчерпаны",
            url=url,
            method="all_failed"
        )

    def get_stats(self) -> dict:
        """Статистика парсера"""
        total = self.success_count + self.fail_count
        return {
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'success_rate': round(self.success_count / total * 100, 2) if total > 0 else 0,
        }

    def reset_stats(self):
        """Сброс статистики"""
        self.fail_count = 0
        self.success_count = 0


# Глобальный экземпляр
rsc_parser = RSCParser(max_retries=2)
