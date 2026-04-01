"""
RSC Parser для ggsel.net без cookies

Использует stealth_requests для обхода QRATOR
"""

import stealth_requests
from bs4 import BeautifulSoup
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
    rank: Optional[int] = None  # Позиция в категории (если есть)


class RSCParser:
    """
    Парсер через stealth_requests (без cookies)
    
    Стратегия:
    1. Запрос через stealth_requests (обходит QRATOR)
    2. Парсинг HTML через BeautifulSoup
    3. Извлечение цены из input полей (unitsToPay, unitsToGet)
    4. Расчёт цены за 1 V-Buck
    """
    
    def __init__(self):
        self.fail_count = 0
        logger.info("RSC Parser инициализирован (режим без cookies)")
    
    def parse_url(self, url: str, timeout: int = 10) -> ParseResult:
        """
        Парсинг цены через stealth_requests
        
        Args:
            url: URL товара (например, https://ggsel.net/catalog/product/...-102124601)
            timeout: Таймаут запроса в секундах
        
        Returns:
            ParseResult с ценой за 1 V-Buck или ошибкой
        """
        logger.info(f"🔍 НАЧАЛО ПАРСИНГА: {url}")
        
        try:
            # Запрос через stealth_requests
            logger.debug(f"Отправка запроса через stealth_requests (timeout={timeout}s)...")
            resp = stealth_requests.get(url, timeout=timeout)
            
            logger.info(f"📥 ПОЛУЧЕН ОТВЕТ: статус={resp.status_code}, длина={len(resp.text)} символов")
            
            if resp.status_code == 429:
                self.fail_count += 1
                logger.warning(f"⚠️ Rate limit (429). Fail count: {self.fail_count}")
                return ParseResult(success=False, error="Rate limit (429)", url=url)
            
            if resp.status_code != 200:
                self.fail_count += 1
                logger.error(f"❌ HTTP ошибка: статус={resp.status_code}")
                logger.debug(f"Тело ответа: {resp.text[:500]}")
                return ParseResult(success=False, error=f"HTTP {resp.status_code}", url=url)
            
            self.fail_count = 0
            logger.info("✅ HTTP статус 200 OK")
            
            # Парсим HTML
            logger.debug("Парсинг HTML через BeautifulSoup...")
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем input поля с ценой и количеством V-Bucks
            logger.debug("Поиск input полей unitsToPay и unitsToGet...")
            units_to_pay = soup.find('input', {'name': 'unitsToPay'})
            units_to_get = soup.find('input', {'name': 'unitsToGet'})
            
            if not units_to_pay:
                logger.warning("⚠️ Input поле 'unitsToPay' не найдено")
                logger.debug(f"Доступные input поля: {[i.get('name') for i in soup.find_all('input', {'name': True})]}")
                return ParseResult(success=False, error="Input поле 'unitsToPay' не найдено", url=url)
            
            if not units_to_get:
                logger.warning("⚠️ Input поле 'unitsToGet' не найдено")
                logger.debug(f"Доступные input поля: {[i.get('name') for i in soup.find_all('input', {'name': True})]}")
                return ParseResult(success=False, error="Input поле 'unitsToGet' не найдено", url=url)
            
            logger.info("✅ Input поля найдены")
            
            # Получаем значения
            try:
                min_price = float(units_to_pay.get('value', '0'))
                vbucks_amount = int(units_to_get.get('value', '0'))
                logger.info(f"💰 Значения: min_price={min_price}₽, vbucks_amount={vbucks_amount}")
            except ValueError as e:
                logger.warning(f"❌ Некорректные значения: {e}")
                logger.debug(f"unitsToPay value: '{units_to_pay.get('value')}'")
                logger.debug(f"unitsToGet value: '{units_to_get.get('value')}'")
                return ParseResult(success=False, error="Некорректные значения", url=url)
            
            if min_price <= 0:
                logger.warning(f"❌ min_price <= 0: {min_price}")
                return ParseResult(success=False, error="Некорректные значения", url=url)
            
            if vbucks_amount <= 0:
                logger.warning(f"❌ vbucks_amount <= 0: {vbucks_amount}")
                return ParseResult(success=False, error="Некорректные значения", url=url)
            
            # Считаем цену за 1 V-Buck
            price_per_vbuck = round(min_price / vbucks_amount, 4)
            
            logger.info(f"✅ РАСЧЁТ: {min_price}₽ / {vbucks_amount} V-Bucks = {price_per_vbuck}₽/V-Buck")
            logger.info(f"🎉 ПАРСИНГ УСПЕШЕН: цена={price_per_vbuck}₽")
            
            return ParseResult(
                success=True,
                price=price_per_vbuck,
                url=url,
                offers=[Offer(price=price_per_vbuck)]
            )
            
        except Exception as e:
            self.fail_count += 1
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {e}", exc_info=True)
            return ParseResult(success=False, error=str(e), url=url)


# Глобальный экземпляр
rsc_parser = RSCParser()
