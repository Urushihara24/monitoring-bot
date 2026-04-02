"""
Конфигурация auto-pricing бота
"""

import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class Config:
    """Конфигурация бота"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_ADMIN_IDS: List[int] = None
    
    # GGSEL API
    # Секретный API key (используется для получения access token через /apilogin)
    GGSEL_API_KEY: str = os.getenv('GGSEL_API_KEY', '')
    # Опционально: можно явно передать готовый access token
    GGSEL_ACCESS_TOKEN: str = os.getenv('GGSEL_ACCESS_TOKEN', '')
    GGSEL_SELLER_ID: int = int(os.getenv('GGSEL_SELLER_ID', '8175'))
    GGSEL_PRODUCT_ID: int = int(os.getenv('GGSEL_PRODUCT_ID', '0'))
    GGSEL_BASE_URL: str = 'https://seller.ggsel.com/api_sellers/api'
    GGSEL_LANG: str = os.getenv('GGSEL_LANG', 'ru-RU')
    GGSEL_REQUIRE_API_ON_START: bool = _env_bool('GGSEL_REQUIRE_API_ON_START', False)
    GGSEL_ENABLED: bool = _env_bool('GGSEL_ENABLED', True)

    # DigiSeller API (второй профиль)
    DIGISELLER_API_KEY: str = os.getenv('DIGISELLER_API_KEY', '')
    DIGISELLER_ACCESS_TOKEN: str = os.getenv('DIGISELLER_ACCESS_TOKEN', '')
    DIGISELLER_SELLER_ID: int = int(os.getenv('DIGISELLER_SELLER_ID', '0'))
    DIGISELLER_PRODUCT_ID: int = int(os.getenv('DIGISELLER_PRODUCT_ID', '0'))
    DIGISELLER_BASE_URL: str = os.getenv(
        'DIGISELLER_BASE_URL',
        'https://api.digiseller.com/api',
    )
    DIGISELLER_LANG: str = os.getenv('DIGISELLER_LANG', 'ru-RU')
    DIGISELLER_REQUIRE_API_ON_START: bool = _env_bool(
        'DIGISELLER_REQUIRE_API_ON_START',
        False,
    )
    DIGISELLER_ENABLED: bool = _env_bool('DIGISELLER_ENABLED', False)
    DIGISELLER_COMPETITOR_URLS: List[str] = None
    
    # Конкуренты (список URL)
    COMPETITOR_URLS: List[str] = None
    # Cookies для доступа к защищенным страницам конкурента
    # Формат: "name1=value1; name2=value2"
    COMPETITOR_COOKIES: str = os.getenv('COMPETITOR_COOKIES', '')
    COMPETITOR_COOKIES_BACKUP_PATH: str = os.getenv(
        'COMPETITOR_COOKIES_BACKUP_PATH',
        'data/cookies_backup.json',
    )

    # RSC parser
    RSC_MAX_RETRIES: int = int(os.getenv('RSC_MAX_RETRIES', '2'))
    
    # Основные настройки цен
    MIN_PRICE: float = float(os.getenv('MIN_PRICE', '0.25'))
    MAX_PRICE: float = float(os.getenv('MAX_PRICE', '10.0'))
    DESIRED_PRICE: float = float(os.getenv('DESIRED_PRICE', '0.35'))
    # Насколько быть ниже конкурента (пример: 0.30 -> 0.2949)
    UNDERCUT_VALUE: float = float(os.getenv('UNDERCUT_VALUE', '0.0051'))
    
    # Режим при достижении MIN_PRICE: FIXED или STEP_UP
    MODE: str = os.getenv('MODE', 'FIXED')
    FIXED_PRICE: float = float(os.getenv('FIXED_PRICE', '0.35'))
    STEP_UP_VALUE: float = float(os.getenv('STEP_UP_VALUE', '0.05'))
    
    # Фильтр слабого конкурента
    LOW_PRICE_THRESHOLD: float = float(os.getenv('LOW_PRICE_THRESHOLD', '0'))
    # До какого уровня считаем логику "ceil(до 0.1) - undercut"
    WEAK_PRICE_CEIL_LIMIT: float = float(os.getenv('WEAK_PRICE_CEIL_LIMIT', '0.3'))
    # Фильтр по позиции в выдаче категории
    POSITION_FILTER_ENABLED: bool = _env_bool('POSITION_FILTER_ENABLED', False)
    WEAK_POSITION_THRESHOLD: int = int(os.getenv('WEAK_POSITION_THRESHOLD', '20'))
    
    # Cooldown (секунды)
    COOLDOWN_SECONDS: int = int(os.getenv('COOLDOWN_SECONDS', '30'))
    
    # Ignore delta
    IGNORE_DELTA: float = float(os.getenv('IGNORE_DELTA', '0.001'))
    
    # Интервал проверки (секунды)
    CHECK_INTERVAL: int = int(os.getenv('CHECK_INTERVAL', '30'))
    # Быстрый интервал (секунды): используется как рекомендуемый диапазон в UI
    FAST_CHECK_INTERVAL_MIN: int = int(os.getenv('FAST_CHECK_INTERVAL_MIN', '20'))
    FAST_CHECK_INTERVAL_MAX: int = int(os.getenv('FAST_CHECK_INTERVAL_MAX', '60'))

    # Уведомления
    NOTIFY_SKIP: bool = _env_bool('NOTIFY_SKIP', False)
    NOTIFY_SKIP_COOLDOWN_SECONDS: int = int(os.getenv('NOTIFY_SKIP_COOLDOWN_SECONDS', '300'))
    
    NOTIFY_COMPETITOR_CHANGE: bool = _env_bool('NOTIFY_COMPETITOR_CHANGE', True)
    COMPETITOR_CHANGE_DELTA: float = float(os.getenv('COMPETITOR_CHANGE_DELTA', '0.0001'))
    COMPETITOR_CHANGE_COOLDOWN_SECONDS: int = int(os.getenv('COMPETITOR_CHANGE_COOLDOWN_SECONDS', '60'))
    NOTIFY_PARSER_ISSUES: bool = _env_bool('NOTIFY_PARSER_ISSUES', True)
    PARSER_ISSUE_COOLDOWN_SECONDS: int = int(os.getenv('PARSER_ISSUE_COOLDOWN_SECONDS', '300'))

    # Защита от убытков и резких колебаний
    HARD_FLOOR_ENABLED: bool = _env_bool('HARD_FLOOR_ENABLED', True)
    MAX_DOWN_STEP: float = float(os.getenv('MAX_DOWN_STEP', '0.03'))
    FAST_REBOUND_DELTA: float = float(os.getenv('FAST_REBOUND_DELTA', '0.01'))
    FAST_REBOUND_BYPASS_COOLDOWN: bool = _env_bool(
        'FAST_REBOUND_BYPASS_COOLDOWN',
        True,
    )
    
    # Логирование
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_MAX_BYTES: int = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    def __post_init__(self):
        # Парсим списки из строк
        if self.TELEGRAM_ADMIN_IDS is None:
            ids_str = os.getenv('TELEGRAM_ADMIN_IDS', '')
            self.TELEGRAM_ADMIN_IDS = [int(x.strip()) for x in ids_str.split(',') if x.strip()]

        if self.COMPETITOR_URLS is None:
            urls_str = os.getenv('COMPETITOR_URLS', '')
            self.COMPETITOR_URLS = [x.strip() for x in urls_str.split(',') if x.strip()]
        
        if self.DIGISELLER_COMPETITOR_URLS is None:
            d_urls_str = os.getenv('DIGISELLER_COMPETITOR_URLS', '')
            self.DIGISELLER_COMPETITOR_URLS = [
                x.strip() for x in d_urls_str.split(',') if x.strip()
            ]


# Глобальный экземпляр конфигурации
config = Config()
