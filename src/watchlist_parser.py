"""
Парсер Google Watchlist для мониторинга цен конкурентов

Использует Google Sheets API или парсинг публичных страниц
"""

import logging
from typing import Optional, List
from dataclasses import dataclass
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class WatchlistResult:
    """Результат парсинга Watchlist"""
    success: bool
    price: Optional[float] = None
    error: Optional[str] = None
    url: str = ""
    timestamp: Optional[str] = None  # Время последнего обновления


class GoogleWatchlistParser:
    """
    Парсер Google Watchlist/Sheets
    
    Поддерживаемые форматы:
    1. Публичные Google Sheets (published to web)
    2. Google Sites страницы
    3. Прямые ссылки на таблицы
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        logger.info("Google Watchlist Parser инициализирован")
    
    def parse_url(self, url: str, timeout: int = 10) -> WatchlistResult:
        """
        Парсинг цены из Google Watchlist
        
        Args:
            url: URL Google Sheets/Sites
            timeout: Таймаут запроса
            
        Returns:
            WatchlistResult с ценой или ошибкой
        """
        logger.info(f"📊 Парсинг Watchlist: {url}")
        
        try:
            resp = self.session.get(url, timeout=timeout)
            
            if resp.status_code != 200:
                logger.error(f"HTTP ошибка: {resp.status_code}")
                return WatchlistResult(success=False, error=f"HTTP {resp.status_code}", url=url)
            
            # Определяем тип страницы и парсим
            if 'docs.google.com/spreadsheets' in url:
                price = self._parse_google_sheet(resp.text)
            elif 'sites.google.com' in url:
                price = self._parse_google_sites(resp.text)
            else:
                # Универсальный парсинг
                price = self._parse_generic(resp.text)
            
            if price is None:
                return WatchlistResult(success=False, error="Цена не найдена", url=url)
            
            logger.info(f"✅ Watchlist цена: {price}")
            return WatchlistResult(success=True, price=price, url=url)
            
        except Exception as e:
            logger.error(f"Ошибка парсинга Watchlist: {e}", exc_info=True)
            return WatchlistResult(success=False, error=str(e), url=url)
    
    def _parse_google_sheet(self, html: str) -> Optional[float]:
        """Парсинг Google Sheets (published to web)"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ищем ячейки с ценами по паттернам
        patterns = [
            r'(\d+[\.,]\d{2,4})\s*₽',  # 0.35₽, 0,35₽
            r'(\d+[\.,]\d{2,4})\s*RUB',  # 0.35 RUB
            r'price[:\s]*(\d+[\.,]\d{2,4})',  # price: 0.35
        ]
        
        text = soup.get_text()
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '.')
                try:
                    return float(price_str)
                except ValueError:
                    continue
        
        return None
    
    def _parse_google_sites(self, html: str) -> Optional[float]:
        """Парсинг Google Sites"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ищем элементы с ценами
        price_selectors = [
            '[class*="price"]',
            '[data-price]',
            '.g-price',
        ]
        
        for selector in price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text().strip()
                price = self._extract_price_from_text(text)
                if price:
                    return price
        
        return self._parse_generic(html)
    
    def _parse_generic(self, html: str) -> Optional[float]:
        """Универсальный парсинг"""
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        # Ищем цену в тексте
        patterns = [
            r'(\d{2,3}[\.,]\d{2,4})\s*₽',  # 0.35₽
            r'(\d{2,3}[\.,]\d{2,4})\s*RUB',
            r'price[:\s=]+(\d{2,3}[\.,]\d{2,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '.')
                try:
                    price = float(price_str)
                    if 0.01 < price < 100:  # Разумный диапазон
                        return price
                except ValueError:
                    continue
        
        return None
    
    def _extract_price_from_text(self, text: str) -> Optional[float]:
        """Извлечение цены из текста"""
        patterns = [
            r'(\d+[\.,]\d{2,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1).replace(',', '.'))
                except ValueError:
                    continue
        
        return None


# Глобальный экземпляр
watchlist_parser = GoogleWatchlistParser()
