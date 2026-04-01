"""
RSC Parser для ggsel.net

Поддерживает два режима:
1. stealth_requests без cookies (локальная разработка)
2. requests с cookies (продакшн на сервере)
"""

import logging
from typing import Optional, List
from dataclasses import dataclass

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


class RSCParser:
    """
    Универсальный парсер цен с ggsel.net
    
    Автоматически выбирает режим:
    - Если есть cookies → использует requests (для сервера)
    - Если нет cookies → использует stealth_requests (локально)
    """
    
    def __init__(self, cookie_string: str = ""):
        self.cookie_string = cookie_string.strip() if cookie_string else ""
        self.fail_count = 0
        self._session = None
        
        if self.cookie_string:
            # Режим с cookies (продакшн)
            import requests
            self._session = requests.Session()
            self._session.headers["Cookie"] = self.cookie_string
            self._session.headers["Referer"] = "https://ggsel.net/"
            logger.info(f"RSC Parser: режим с cookies ({len(self.cookie_string)} символов)")
        else:
            # Режим без cookies (локальная разработка)
            import stealth_requests
            self._stealth = stealth_requests
            logger.info("RSC Parser: режим stealth_requests (без cookies)")
    
    def parse_url(self, url: str, timeout: int = 10) -> ParseResult:
        """
        Парсинг цены с URL конкурента
        
        Args:
            url: URL товара (например, https://ggsel.net/catalog/product/...-102124601)
            timeout: Таймаут запроса в секундах
        
        Returns:
            ParseResult с ценой за 1 V-Buck или ошибкой
        """
        try:
            # Выполняем запрос в зависимости от режима
            if self._session:
                # requests с cookies
                resp = self._session.get(url, timeout=timeout)
            else:
                # stealth_requests без cookies
                resp = self._stealth.get(url, timeout=timeout)
            
            # Проверяем статус
            if resp.status_code == 429:
                self.fail_count += 1
                logger.warning(f"Rate limit (429). Fail count: {self.fail_count}")
                return ParseResult(success=False, error="Rate limit (429)", url=url)
            
            if resp.status_code != 200:
                self.fail_count += 1
                logger.error(f"HTTP статус: {resp.status_code}")
                return ParseResult(success=False, error=f"HTTP {resp.status_code}", url=url)
            
            self.fail_count = 0
            
            # Парсим HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем input поля с ценой и количеством V-Bucks
            units_to_pay = soup.find('input', {'name': 'unitsToPay'})
            units_to_get = soup.find('input', {'name': 'unitsToGet'})
            
            if not units_to_pay or not units_to_get:
                logger.warning("Input поля не найдены")
                return ParseResult(success=False, error="Input поля не найдены", url=url)
            
            # Получаем значения
            try:
                min_price = float(units_to_pay.get('value', '0'))
                vbucks_amount = int(units_to_get.get('value', '0'))
            except ValueError as e:
                logger.warning(f"Некорректные значения: {e}")
                return ParseResult(success=False, error="Некорректные значения", url=url)
            
            if min_price <= 0 or vbucks_amount <= 0:
                logger.warning(f"Некорректные значения: price={min_price}, vbucks={vbucks_amount}")
                return ParseResult(success=False, error="Некорректные значения", url=url)
            
            # Считаем цену за 1 V-Buck
            price_per_vbuck = round(min_price / vbucks_amount, 4)
            
            logger.info(f"Мин. цена: {min_price}₽ за {vbucks_amount} V-Bucks = {price_per_vbuck}₽/V-Buck")
            
            return ParseResult(
                success=True,
                price=price_per_vbuck,
                url=url,
                offers=[Offer(price=price_per_vbuck)]
            )
            
        except Exception as e:
            self.fail_count += 1
            logger.error(f"Ошибка парсинга: {e}", exc_info=True)
            return ParseResult(success=False, error=str(e), url=url)


# Глобальный экземпляр (создаётся при импорте)
# Cookies загружаются из конфига автоматически
try:
    from .config import config
    rsc_parser = RSCParser(config.COMPETITOR_COOKIES)
except Exception as e:
    logger.warning(f"Не удалось загрузить cookies из конфига: {e}")
    rsc_parser = RSCParser()
