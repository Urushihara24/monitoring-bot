"""
Парсер цен конкурентов
Обновлённая версия с улучшенной обработкой ошибок
"""

import logging
import time
import re
from typing import Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Результат парсинга"""
    success: bool
    price: Optional[float] = None
    error: Optional[str] = None
    url: str = ''
    rank: Optional[int] = None
    category_url: Optional[str] = None


class CompetitorParser:
    """Парсер цен конкурентов"""

    def __init__(self):
        self.session = requests.Session()
        # Обновлённый User-Agent для обхода блокировок
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })

    def parse_url(
        self,
        url: str,
        max_retries: int = 3,
        timeout: int = 15,
        detect_rank: bool = False,
    ) -> ParseResult:
        """
        Парсинг цены с URL конкурента

        Args:
            url: URL страницы товара
            max_retries: Количество попыток
            timeout: Таймаут запроса

        Returns:
            ParseResult с ценой или ошибкой
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.debug(f'Парсинг {url} (попытка {attempt + 1}/{max_retries})')

                response = self.session.get(url, timeout=timeout, allow_redirects=True)

                # Обработка 401/403
                if response.status_code in (401, 403):
                    logger.warning(f'D доступ запрещён ({response.status_code}): {url}')
                    last_error = f'D доступ запрещён ({response.status_code})'
                    # Пробуем без headers для некоторых сайтов
                    if attempt == max_retries - 1:
                        return ParseResult(success=False, error=last_error, url=url)
                    time.sleep(2 ** attempt)  # Экспоненциальная задержка
                    continue

                # Обработка 404
                if response.status_code == 404:
                    logger.warning(f'Страница не найдена (404): {url}')
                    return ParseResult(success=False, error='Страница не найдена', url=url)

                response.raise_for_status()

                price = self._extract_price(response.text, url)

                if price is not None:
                    rank = None
                    category_url = None
                    if detect_rank:
                        rank, category_url = self._detect_rank_from_product_page(response.text, url)
                    logger.info(f'Найдена цена {price} на {url}')
                    return ParseResult(
                        success=True,
                        price=price,
                        url=url,
                        rank=rank,
                        category_url=category_url,
                    )

                last_error = 'Цена не найдена на странице'
                logger.warning(f'{last_error}: {url}')

            except requests.Timeout:
                last_error = f'Timeout ({timeout}s)'
                logger.warning(f'{last_error}: {url}')

            except requests.RequestException as e:
                last_error = f'Ошибка запроса: {type(e).__name__}'
                logger.error(f'Ошибка запроса {url}: {e}')

            except Exception as e:
                last_error = str(e)
                logger.error(f'Ошибка парсинга {url}: {e}')

            # Пауза между попытками (экспоненциальная)
            if attempt < max_retries - 1:
                time.sleep(1 + attempt)

        return ParseResult(success=False, error=last_error, url=url)

    def parse_competitors(
        self,
        urls: List[str],
        detect_rank: bool = False,
    ) -> List[ParseResult]:
        """
        Парсинг нескольких конкурентов c расширенной информацией

        Returns:
            Список ParseResult
        """
        results: List[ParseResult] = []

        for i, url in enumerate(urls):
            logger.info(f'Парсинг конкурента {i + 1}/{len(urls)}: {url}')
            result = self.parse_url(url, detect_rank=detect_rank)
            results.append(result)

            # Пауза между запросами к разным URL
            if i < len(urls) - 1:
                time.sleep(1)

        return results

    def parse_multiple(self, urls: List[str]) -> List[float]:
        """
        Парсинг цен с нескольких URL

        Args:
            urls: Список URL

        Returns:
            Список найденных цен
        """
        results = self.parse_competitors(urls, detect_rank=False)
        return [r.price for r in results if r.success and r.price is not None]

    def _extract_price(self, html: str, url: str) -> Optional[float]:
        """
        Извлечение цены из HTML

        Поддерживаемые селекторы:
        - .price
        - [class*="price"]
        - [data-testid="price"]
        - [itemprop="price"]
        - и другие
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Селекторы для поиска цены (приоритетные)
        selectors = [
            '.price',  # Стандартный
            '[class*="price"]',  # Любой класс содержащий "price"
            '[data-testid="price"]',  # Test ID
            '[itemprop="price"]',  # Schema.org
            '.product-price',
            '.sale-price',
            '.final-price',
            '[class*="Price"]',
            '.cost',
            '[class*="cost"]',
        ]

        for selector in selectors:
            elements = soup.select(selector)

            for element in elements:
                text = element.get_text().strip()
                price = self._parse_price_text(text)

                if price and price > 0 and price < 100000:  # Разумный предел
                    logger.debug(f'Найдена цена {price} по селектору "{selector}"')
                    return price

        # Если не нашли по селекторам, ищем в тексте страницы
        text = soup.get_text()
        price = self._find_price_in_text(text)

        if price:
            return price

        return None

    def _parse_price_text(self, text: str) -> Optional[float]:
        """
        Парсинг числа из текста

        Поддерживаемые форматы:
        - "123,45 ₽"
        - "1 234.56"
        - "1234"
        - "1,234.56"
        """
        if not text:
            return None

        # Удаляем лишние символы (оставляем цифры, точки, запятые, пробелы)
        cleaned = re.sub(r'[^\d.,\s]', '', text)

        # Удаляем пробелы между тысячами (1 234 → 1234)
        cleaned = cleaned.replace(' ', '')

        # Заменяем запятую на точку
        cleaned = cleaned.replace(',', '.')

        # Извлекаем первое число
        match = re.search(r'(\d+\.?\d*)', cleaned)

        if match:
            try:
                price = float(match.group(1))
                if price > 0 and price < 100000:  # Разумный предел
                    return round(price, 4)
            except ValueError:
                pass

        return None

    def _find_price_in_text(self, text: str) -> Optional[float]:
        """Поиск цены в большом тексте"""
        if not text:
            return None

        # Ищем паттерны типа "123.45", "123,45", "123 ₽"
        patterns = [
            r'(\d+[\s.]?\d*[\s.]?\d*)\s*[₽₽]',  # Цена с символом рубля
            r'цена[:\s]*(\d+[\s.,]?\d*)',  # "цена: 123"
            r'(\d+,\d{2})\s*руб',  # "123,45 руб"
            r'(\d+)\s*рублей',  # "123 рублей"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    price = float(price_str)
                    if price > 0 and price < 100000:  # Разумный предел
                        return round(price, 4)
                except ValueError:
                    pass

        return None

    def _normalize_url(self, raw_url: str) -> str:
        """Нормализация URL для сравнения ссылок"""
        parsed = urlsplit(raw_url.strip())
        path = parsed.path.rstrip('/')
        return urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))

    def _detect_rank_from_product_page(self, html: str, product_url: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Пытается определить позицию товара в категории:
        1) находит ссылки категорий на странице товара
        2) открывает категории и ищет позицию ссылки товара в списке карточек
        """
        soup = BeautifulSoup(html, 'html.parser')
        category_urls: List[str] = []
        seen = set()

        for a in soup.select('a[href]'):
            href = a.get('href', '').strip()
            if not href:
                continue
            absolute = urljoin(product_url, href)
            parsed = urlsplit(absolute)
            path = parsed.path.lower()
            if '/catalog/' not in path or '/catalog/product/' in path:
                continue
            normalized = self._normalize_url(absolute)
            if normalized not in seen:
                seen.add(normalized)
                category_urls.append(normalized)

        # Ограничиваем количество попыток, чтобы не перегружать сайт
        for category_url in category_urls[:3]:
            rank = self._find_product_rank_in_category(category_url, product_url)
            if rank is not None:
                logger.info(f'Определена позиция конкурента: rank={rank}, category={category_url}')
                return rank, category_url

        return None, None

    def _find_product_rank_in_category(self, category_url: str, product_url: str) -> Optional[int]:
        """Ищет позицию товара в карточках категории (первая страница)"""
        try:
            response = self.session.get(category_url, timeout=15, allow_redirects=True)
            response.raise_for_status()
        except Exception as e:
            logger.debug(f'Не удалось открыть категорию {category_url}: {e}')
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        target_path = urlsplit(self._normalize_url(product_url)).path.lower()
        target_tail = target_path.split('/catalog/product/')[-1] if '/catalog/product/' in target_path else target_path

        links: List[str] = []
        seen = set()
        for a in soup.select('a[href*="/catalog/product/"]'):
            href = a.get('href', '').strip()
            if not href:
                continue
            normalized = self._normalize_url(urljoin(category_url, href))
            if normalized in seen:
                continue
            seen.add(normalized)
            links.append(normalized)

        for idx, item_url in enumerate(links, start=1):
            item_path = urlsplit(item_url).path.lower()
            item_tail = item_path.split('/catalog/product/')[-1] if '/catalog/product/' in item_path else item_path
            if item_path == target_path or item_tail == target_tail:
                return idx

        return None


# Глобальный экземпляр
parser = CompetitorParser()
