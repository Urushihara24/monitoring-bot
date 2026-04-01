"""
Distill.io Parser для мониторинга цен

Интеграция с Distill.io API как fallback для основных парсеров.
Distill.io отслеживает изменения на страницах и предоставляет данные через API.

Документация Distill.io API:
https://distill.io/web-monitoring-api

Поддерживаемые режимы:
1. Distill Cloud API (платный, с вебхуками)
2. Локальный Distill Web Monitor (бесплатный, через файлы)
3. Email парсинг уведомлений
"""

import logging
import os
import re
import json
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass
class DistillResult:
    """Результат получения цены из Distill.io"""
    success: bool
    price: Optional[float] = None
    error: Optional[str] = None
    url: str = ""
    method: str = "unknown"  # cloud_api, local_files, email
    last_updated: Optional[datetime] = None
    raw_data: Optional[dict] = None


class DistillParser:
    """
    Парсер через Distill.io

    Стратегия:
    1. Distill Cloud API (если настроен)
    2. Локальные файлы Distill Web Monitor
    3. Парсинг email уведомлений (IMAP)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        monitor_ids: Optional[List[str]] = None,
        local_data_dir: Optional[str] = None,
        email_enabled: bool = False,
    ):
        self.api_key = api_key
        self.monitor_ids = monitor_ids or []
        self.local_data_dir = Path(local_data_dir) if local_data_dir else None
        self.email_enabled = email_enabled
        
        # Кэш данных
        self._cache: dict = {}
        self._cache_time: dict = {}
        
        logger.info(f"Distill Parser инициализирован: API={bool(api_key)}, monitors={len(self.monitor_ids)}, local={bool(local_data_dir)}")

    def _parse_price_from_text(self, text: str) -> Optional[float]:
        """
        Извлечение цены из текста
        
        Поддерживаемые форматы:
        - 0.35₽, 0,35₽
        - 0.35 RUB, 0,35 RUB
        - ₽0.35, RUB 0.35
        """
        patterns = [
            r'(\d{1,3}[\.,]\d{2,4})\s*₽',
            r'(\d{1,3}[\.,]\d{2,4})\s*RUB',
            r'₽\s*(\d{1,3}[\.,]\d{2,4})',
            r'RUB\s*(\d{1,3}[\.,]\d{2,4})',
            r'price[:\s=]+(\d{1,3}[\.,]\d{2,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '.')
                try:
                    price = float(price_str)
                    # Проверка на разумность цены
                    if 0.01 <= price <= 1000:
                        return price
                except ValueError:
                    continue
        
        return None

    def fetch_from_cloud_api(self, monitor_id: str, timeout: int = 10) -> DistillResult:
        """
        Получение данных из Distill Cloud API
        
        Args:
            monitor_id: ID монитора в Distill.io
            timeout: Таймаут запроса
            
        Returns:
            DistillResult с ценой или ошибкой
        """
        if not self.api_key:
            return DistillResult(success=False, error="API key не указан", method="cloud_api")
        
        url = f"https://api.distill.io/monitors/{monitor_id}/data"
        headers = {
            'X-Distill-API-Key': self.api_key,
            'Accept': 'application/json',
        }
        
        try:
            logger.debug(f"Запрос к Distill Cloud API: {url}")
            resp = requests.get(url, headers=headers, timeout=timeout)
            
            if resp.status_code == 401:
                return DistillResult(success=False, error="Неверный API key", method="cloud_api")
            
            if resp.status_code == 429:
                return DistillResult(success=False, error="Rate limit Distill API", method="cloud_api")
            
            if resp.status_code != 200:
                return DistillResult(success=False, error=f"HTTP {resp.status_code}", method="cloud_api")
            
            data = resp.json()
            
            # Извлекаем последнюю запись
            if not data.get('data'):
                return DistillResult(success=False, error="Нет данных", method="cloud_api")
            
            latest = data['data'][0]  # Последняя запись
            content = latest.get('content', '')
            
            price = self._parse_price_from_text(content)
            
            if price is None:
                return DistillResult(
                    success=False,
                    error="Цена не найдена в данных",
                    method="cloud_api",
                    raw_data=data
                )
            
            last_updated = datetime.fromisoformat(latest['timestamp'].replace('Z', '+00:00'))
            
            logger.info(f"✅ Distill Cloud API: цена={price}₽, обновлено={last_updated}")
            
            return DistillResult(
                success=True,
                price=price,
                method="cloud_api",
                last_updated=last_updated,
                raw_data=data
            )
            
        except requests.exceptions.Timeout:
            return DistillResult(success=False, error="Timeout Distill API", method="cloud_api")
        except Exception as e:
            logger.error(f"Ошибка Distill Cloud API: {e}", exc_info=True)
            return DistillResult(success=False, error=str(e), method="cloud_api")

    def fetch_from_local_files(self, url: str) -> DistillResult:
        """
        Получение данных из локальных файлов Distill Web Monitor
        
        Distill Web Monitor сохраняет данные в:
        - Windows: %APPDATA%/Distill Web Monitor/data/
        - Mac: ~/Library/Application Support/Distill Web Monitor/data/
        - Linux: ~/.config/Distill Web Monitor/data/
        
        Args:
            url: URL монитора для поиска
            
        Returns:
            DistillResult с ценой или ошибкой
        """
        if not self.local_data_dir:
            return DistillResult(success=False, error="Local data dir не указан", method="local_files")
        
        try:
            # Ищем файлы данных
            data_files = list(self.local_data_dir.glob('**/*.json'))
            
            if not data_files:
                return DistillResult(success=False, error="Нет файлов данных", method="local_files")
            
            # Ищем файл для нужного URL
            target_file = None
            for file in data_files:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Проверяем URL
                    if url in str(data.get('url', '')):
                        target_file = file
                        break
                except (json.JSONDecodeError, IOError):
                    continue
            
            if not target_file:
                # Если не нашли по URL, берём последний файл
                target_file = max(data_files, key=lambda f: f.stat().st_mtime)
                logger.warning(f"Файл для URL не найден, используем последний: {target_file}")
            
            # Читаем данные
            with open(target_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Извлекаем цену из контента
            content = data.get('content', data.get('diff', ''))
            price = self._parse_price_from_text(content)
            
            if price is None:
                # Пробуем извлечь из diff
                diff = data.get('diff', '')
                price = self._parse_price_from_text(diff)
            
            if price is None:
                return DistillResult(
                    success=False,
                    error="Цена не найдена в локальных данных",
                    method="local_files",
                    raw_data=data
                )
            
            last_updated = datetime.fromtimestamp(target_file.stat().st_mtime)
            
            logger.info(f"✅ Distill Local Files: цена={price}₽, файл={target_file.name}")
            
            return DistillResult(
                success=True,
                price=price,
                method="local_files",
                last_updated=last_updated,
                raw_data=data
            )
            
        except Exception as e:
            logger.error(f"Ошибка чтения локальных файлов: {e}", exc_info=True)
            return DistillResult(success=False, error=str(e), method="local_files")

    def fetch_from_email(
        self,
        imap_server: str,
        imap_port: int,
        username: str,
        password: str,
        timeout: int = 30
    ) -> DistillResult:
        """
        Получение цены из email уведомлений Distill.io
        
        Args:
            imap_server: IMAP сервер (например, imap.gmail.com)
            imap_port: IMAP порт (993 для SSL)
            username: Email для входа
            password: Пароль приложения
            timeout: Таймаут подключения
            
        Returns:
            DistillResult с ценой или ошибкой
        """
        if not self.email_enabled:
            return DistillResult(success=False, error="Email parsing отключен", method="email")
        
        try:
            import imaplib
            from email.parser import BytesParser
            from email.policy import default
            
            # Подключение к IMAP
            logger.debug(f"Подключение к IMAP: {imap_server}:{imap_port}")
            
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=timeout)
            mail.login(username, password)
            mail.select('INBOX')
            
            # Поиск писем от Distill.io
            status, messages = mail.search(None, '(FROM "noreply@distill.io" SUBJECT "Price Alert")')
            
            if status != 'OK' or not messages[0]:
                return DistillResult(success=False, error="Письма от Distill.io не найдены", method="email")
            
            # Берём последнее письмо
            latest_msg_id = messages[0].split()[-1]
            status, msg_data = mail.fetch(latest_msg_id, '(RFC822)')
            
            if status != 'OK':
                return DistillResult(success=False, error="Не удалось прочитать письмо", method="email")
            
            # Парсим письмо
            parser = BytesParser(policy=default)
            email_msg = parser.parsebytes(msg_data[0][1])
            
            # Извлекаем тело письма
            body = ""
            if email_msg.is_multipart():
                for part in email_msg.walk():
                    if part.get_content_type() == 'text/plain':
                        try:
                            body = part.get_content(decode=True).decode('utf-8')
                            break
                        except:
                            continue
            else:
                body = email_msg.get_content(decode=True).decode('utf-8')
            
            mail.close()
            mail.logout()
            
            # Извлекаем цену из тела письма
            price = self._parse_price_from_text(body)
            
            if price is None:
                return DistillResult(
                    success=False,
                    error="Цена не найдена в письме",
                    method="email",
                    raw_data={'body': body[:500]}
                )
            
            logger.info(f"✅ Distill Email: цена={price}₽")
            
            return DistillResult(
                success=True,
                price=price,
                method="email",
                last_updated=datetime.now()
            )
            
        except ImportError:
            return DistillResult(success=False, error="imaplib недоступен", method="email")
        except Exception as e:
            logger.error(f"Ошибка email parsing: {e}", exc_info=True)
            return DistillResult(success=False, error=str(e), method="email")

    def get_price(
        self,
        url: str,
        timeout: int = 10,
        use_cache: bool = True,
        cache_ttl_seconds: int = 300
    ) -> DistillResult:
        """
        Получение цены (автоматический выбор метода)
        
        Приоритет методов:
        1. Cloud API (если настроен)
        2. Local Files (если настроен)
        3. Email (если включен)
        
        Args:
            url: URL монитора
            timeout: Таймаут запроса
            use_cache: Использовать кэш
            cache_ttl_seconds: Время жизни кэша
            
        Returns:
            DistillResult с ценой или ошибкой
        """
        # Проверка кэша
        if use_cache and url in self._cache:
            cache_age = (datetime.now() - self._cache_time.get(url, datetime.min)).total_seconds()
            if cache_age < cache_ttl_seconds:
                logger.debug(f"Используем кэш для {url} (возраст: {cache_age:.0f}s)")
                return self._cache[url]
        
        result = DistillResult(success=False, error="Нет доступных методов", url=url)
        
        # 1. Cloud API
        if self.api_key and self.monitor_ids:
            for monitor_id in self.monitor_ids:
                result = self.fetch_from_cloud_api(monitor_id, timeout)
                if result.success:
                    break
        
        # 2. Local Files
        if not result.success and self.local_data_dir:
            result = self.fetch_from_local_files(url)
        
        # 3. Email (требует дополнительных настроек, вызывается отдельно)
        # if not result.success and self.email_enabled:
        #     result = self.fetch_from_email(...)
        
        # Кэширование
        if use_cache:
            self._cache[url] = result
            self._cache_time[url] = datetime.now()
        
        return result

    def clear_cache(self):
        """Очистка кэша"""
        self._cache.clear()
        self._cache_time.clear()
        logger.debug("Distill cache очищен")


# Глобальный экземпляр (инициализируется в main с конфигом)
distill_parser: Optional[DistillParser] = None


def init_distill_parser(config) -> DistillParser:
    """
    Инициализация Distill парсера из конфига
    
    Args:
        config: Объект конфигурации
        
    Returns:
        Настроенный DistillParser
    """
    global distill_parser
    
    # Получаем настройки из конфига
    api_key = getattr(config, 'DISTILL_API_KEY', None) or os.getenv('DISTILL_API_KEY')
    monitor_ids_str = getattr(config, 'DISTILL_MONITOR_IDS', '') or os.getenv('DISTILL_MONITOR_IDS', '')
    monitor_ids = [x.strip() for x in monitor_ids_str.split(',') if x.strip()]
    
    local_data_dir = getattr(config, 'DISTILL_LOCAL_DATA_DIR', None) or os.getenv('DISTILL_LOCAL_DATA_DIR')
    email_enabled = getattr(config, 'DISTILL_EMAIL_ENABLED', False)
    
    distill_parser = DistillParser(
        api_key=api_key,
        monitor_ids=monitor_ids,
        local_data_dir=local_data_dir,
        email_enabled=email_enabled,
    )
    
    return distill_parser
