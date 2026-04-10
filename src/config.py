"""
Конфигурация auto-pricing бота
"""

import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_optional_float(name: str) -> Optional[float]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _env_optional_int(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return int(float(value.strip()))
    except ValueError:
        return None


def _env_optional_str(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _env_optional_bool(name: str) -> Optional[bool]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass
class Config:
    """Конфигурация бота"""

    # Путь к env-файлу для runtime-синхронизации cookies.
    ENV_FILE_PATH: str = os.getenv('ENV_FILE_PATH', '.env')
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_ADMIN_IDS: List[int] = None
    
    # GGSEL API
    # API key или JWT access token (legacy)
    GGSEL_API_KEY: str = os.getenv('GGSEL_API_KEY', '')
    # Явный секрет для подписи /apilogin (если GGSEL_API_KEY = JWT)
    GGSEL_API_SECRET: str = os.getenv('GGSEL_API_SECRET', '')
    # Опционально: можно явно передать готовый access token
    GGSEL_ACCESS_TOKEN: str = os.getenv('GGSEL_ACCESS_TOKEN', '')
    GGSEL_SELLER_ID: int = int(os.getenv('GGSEL_SELLER_ID', '8175'))
    GGSEL_PRODUCT_ID: int = int(os.getenv('GGSEL_PRODUCT_ID', '0'))
    GGSEL_BASE_URL: str = 'https://seller.ggsel.com/api_sellers/api'
    GGSEL_LANG: str = os.getenv('GGSEL_LANG', 'ru-RU')
    GGSEL_REQUIRE_API_ON_START: bool = _env_bool('GGSEL_REQUIRE_API_ON_START', False)
    GGSEL_ENABLED: bool = _env_bool('GGSEL_ENABLED', True)
    GGSEL_COMPETITOR_URLS: List[str] = None
    GGSEL_CHAT_AUTOREPLY_ENABLED: bool = _env_bool(
        'GGSEL_CHAT_AUTOREPLY_ENABLED',
        False,
    )
    GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS: List[int] = None
    GGSEL_CHAT_AUTOREPLY_PAGE_SIZE: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_PAGE_SIZE', '50')
    )
    GGSEL_CHAT_AUTOREPLY_MAX_PAGES: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_MAX_PAGES', '2')
    )
    GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS', '30')
    )
    GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES: bool = _env_bool(
        'GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES',
        True,
    )
    GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT: bool = _env_bool(
        'GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
        True,
    )
    GGSEL_CHAT_AUTOREPLY_SMART_NON_EMPTY: bool = _env_bool(
        'GGSEL_CHAT_AUTOREPLY_SMART_NON_EMPTY',
        False,
    )
    GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', '30')
    )
    GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES', '20')
    )
    GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK: bool = _env_bool(
        'GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK',
        False,
    )
    GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS', '30')
    )
    GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS: int = int(
        os.getenv('GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS', '24')
    )
    GGSEL_CHAT_TEMPLATE_RU_ALREADY: str = os.getenv(
        'GGSEL_CHAT_TEMPLATE_RU_ALREADY',
        '',
    )
    GGSEL_CHAT_TEMPLATE_RU_ADD: str = os.getenv(
        'GGSEL_CHAT_TEMPLATE_RU_ADD',
        '',
    )
    GGSEL_CHAT_TEMPLATE_EN_ALREADY: str = os.getenv(
        'GGSEL_CHAT_TEMPLATE_EN_ALREADY',
        '',
    )
    GGSEL_CHAT_TEMPLATE_EN_ADD: str = os.getenv(
        'GGSEL_CHAT_TEMPLATE_EN_ADD',
        '',
    )

    # DigiSeller API (второй профиль)
    DIGISELLER_API_KEY: str = os.getenv('DIGISELLER_API_KEY', '')
    # Явный секрет для подписи /apilogin (если DIGISELLER_API_KEY = JWT)
    DIGISELLER_API_SECRET: str = os.getenv('DIGISELLER_API_SECRET', '')
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
    DIGISELLER_CHAT_AUTOREPLY_ENABLED: bool = _env_bool(
        'DIGISELLER_CHAT_AUTOREPLY_ENABLED',
        False,
    )
    DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS: List[int] = None
    DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE', '50')
    )
    DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES', '2')
    )
    DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS', '30')
    )
    DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES: bool = _env_bool(
        'DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES',
        True,
    )
    DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT: bool = _env_bool(
        'DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
        True,
    )
    DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY: bool = _env_bool(
        'DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY',
        False,
    )
    DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', '30')
    )
    DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES', '20')
    )
    DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK: bool = _env_bool(
        'DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK',
        True,
    )
    DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS', '30')
    )
    DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS: int = int(
        os.getenv('DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS', '24')
    )
    DIGISELLER_CHAT_TEMPLATE_RU_ALREADY: str = os.getenv(
        'DIGISELLER_CHAT_TEMPLATE_RU_ALREADY',
        '',
    )
    DIGISELLER_CHAT_TEMPLATE_RU_ADD: str = os.getenv(
        'DIGISELLER_CHAT_TEMPLATE_RU_ADD',
        '',
    )
    DIGISELLER_CHAT_TEMPLATE_EN_ALREADY: str = os.getenv(
        'DIGISELLER_CHAT_TEMPLATE_EN_ALREADY',
        '',
    )
    DIGISELLER_CHAT_TEMPLATE_EN_ADD: str = os.getenv(
        'DIGISELLER_CHAT_TEMPLATE_EN_ADD',
        '',
    )
    # Профильные дефолты runtime для DigiSeller (используются только если
    # ключи не были переопределены в runtime_settings ранее).
    DIGISELLER_MIN_PRICE: Optional[float] = _env_optional_float(
        'DIGISELLER_MIN_PRICE'
    )
    DIGISELLER_MAX_PRICE: Optional[float] = _env_optional_float(
        'DIGISELLER_MAX_PRICE'
    )
    DIGISELLER_DESIRED_PRICE: Optional[float] = _env_optional_float(
        'DIGISELLER_DESIRED_PRICE'
    )
    DIGISELLER_UNDERCUT_VALUE: Optional[float] = _env_optional_float(
        'DIGISELLER_UNDERCUT_VALUE'
    )
    DIGISELLER_MODE: Optional[str] = _env_optional_str('DIGISELLER_MODE')
    DIGISELLER_FIXED_PRICE: Optional[float] = _env_optional_float(
        'DIGISELLER_FIXED_PRICE'
    )
    DIGISELLER_STEP_UP_VALUE: Optional[float] = _env_optional_float(
        'DIGISELLER_STEP_UP_VALUE'
    )
    DIGISELLER_WEAK_PRICE_CEIL_LIMIT: Optional[float] = _env_optional_float(
        'DIGISELLER_WEAK_PRICE_CEIL_LIMIT'
    )
    DIGISELLER_POSITION_FILTER_ENABLED: Optional[bool] = _env_optional_bool(
        'DIGISELLER_POSITION_FILTER_ENABLED'
    )
    DIGISELLER_WEAK_POSITION_THRESHOLD: Optional[int] = _env_optional_int(
        'DIGISELLER_WEAK_POSITION_THRESHOLD'
    )
    DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED: Optional[bool] = _env_optional_bool(
        'DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED'
    )
    DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP: Optional[float] = _env_optional_float(
        'DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP'
    )
    DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP: Optional[float] = _env_optional_float(
        'DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP'
    )
    DIGISELLER_CHECK_INTERVAL: Optional[int] = _env_optional_int(
        'DIGISELLER_CHECK_INTERVAL'
    )
    DIGISELLER_FAST_CHECK_INTERVAL_MIN: Optional[int] = _env_optional_int(
        'DIGISELLER_FAST_CHECK_INTERVAL_MIN'
    )
    DIGISELLER_FAST_CHECK_INTERVAL_MAX: Optional[int] = _env_optional_int(
        'DIGISELLER_FAST_CHECK_INTERVAL_MAX'
    )
    DIGISELLER_COOLDOWN_SECONDS: Optional[int] = _env_optional_int(
        'DIGISELLER_COOLDOWN_SECONDS'
    )
    DIGISELLER_IGNORE_DELTA: Optional[float] = _env_optional_float(
        'DIGISELLER_IGNORE_DELTA'
    )
    DIGISELLER_NOTIFY_SKIP: Optional[bool] = _env_optional_bool(
        'DIGISELLER_NOTIFY_SKIP'
    )
    DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS: Optional[int] = _env_optional_int(
        'DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS'
    )
    DIGISELLER_NOTIFY_COMPETITOR_CHANGE: Optional[bool] = _env_optional_bool(
        'DIGISELLER_NOTIFY_COMPETITOR_CHANGE'
    )
    DIGISELLER_COMPETITOR_CHANGE_DELTA: Optional[float] = _env_optional_float(
        'DIGISELLER_COMPETITOR_CHANGE_DELTA'
    )
    DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS: Optional[int] = _env_optional_int(
        'DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS'
    )
    DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE: Optional[bool] = _env_optional_bool(
        'DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE'
    )
    DIGISELLER_NOTIFY_PARSER_ISSUES: Optional[bool] = _env_optional_bool(
        'DIGISELLER_NOTIFY_PARSER_ISSUES'
    )
    DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS: Optional[int] = _env_optional_int(
        'DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS'
    )
    DIGISELLER_HARD_FLOOR_ENABLED: Optional[bool] = _env_optional_bool(
        'DIGISELLER_HARD_FLOOR_ENABLED'
    )
    DIGISELLER_MAX_DOWN_STEP: Optional[float] = _env_optional_float(
        'DIGISELLER_MAX_DOWN_STEP'
    )
    DIGISELLER_FAST_REBOUND_DELTA: Optional[float] = _env_optional_float(
        'DIGISELLER_FAST_REBOUND_DELTA'
    )
    DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN: Optional[bool] = _env_optional_bool(
        'DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN'
    )
    
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
    
    # Режим ценообразования:
    # FOLLOW / DUMPING / RAISE
    # (legacy значения FIXED/STEP_UP/FOLLOW_EXACT/FOLLOW_PLUS
    # автоматически мапятся в новые)
    MODE: str = os.getenv('MODE', 'DUMPING')
    FIXED_PRICE: float = float(os.getenv('FIXED_PRICE', '0.35'))
    STEP_UP_VALUE: float = float(os.getenv('STEP_UP_VALUE', '0.05'))
    
    # До какого уровня считаем логику "ceil(до 0.1) - undercut"
    WEAK_PRICE_CEIL_LIMIT: float = float(os.getenv('WEAK_PRICE_CEIL_LIMIT', '0.3'))
    # Фильтр по позиции в выдаче категории
    POSITION_FILTER_ENABLED: bool = _env_bool('POSITION_FILTER_ENABLED', False)
    WEAK_POSITION_THRESHOLD: int = int(os.getenv('WEAK_POSITION_THRESHOLD', '20'))
    # Эвристика для случая rank=N/A: если min цена заметно ниже следующей,
    # считаем такого конкурента слабым по позиции (например, низкая ставка).
    WEAK_UNKNOWN_RANK_ENABLED: bool = _env_bool(
        'WEAK_UNKNOWN_RANK_ENABLED',
        True,
    )
    WEAK_UNKNOWN_RANK_ABS_GAP: float = float(
        os.getenv('WEAK_UNKNOWN_RANK_ABS_GAP', '0.03')
    )
    WEAK_UNKNOWN_RANK_REL_GAP: float = float(
        os.getenv('WEAK_UNKNOWN_RANK_REL_GAP', '0.08')
    )
    
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
    UPDATE_ONLY_ON_COMPETITOR_CHANGE: bool = _env_bool(
        'UPDATE_ONLY_ON_COMPETITOR_CHANGE',
        True,
    )
    NOTIFY_PARSER_ISSUES: bool = _env_bool('NOTIFY_PARSER_ISSUES', True)
    PARSER_ISSUE_COOLDOWN_SECONDS: int = int(os.getenv('PARSER_ISSUE_COOLDOWN_SECONDS', '300'))
    # Авто-ошибки планировщика в Telegram (не влияет на серверные логи)
    NOTIFY_ERRORS: bool = _env_bool('NOTIFY_ERRORS', True)

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

        if self.GGSEL_COMPETITOR_URLS is None:
            gg_urls_str = os.getenv('GGSEL_COMPETITOR_URLS', '')
            gg_urls = [x.strip() for x in gg_urls_str.split(',') if x.strip()]
            self.GGSEL_COMPETITOR_URLS = gg_urls or list(self.COMPETITOR_URLS)

        if self.DIGISELLER_COMPETITOR_URLS is None:
            d_urls_str = os.getenv('DIGISELLER_COMPETITOR_URLS', '')
            self.DIGISELLER_COMPETITOR_URLS = [
                x.strip() for x in d_urls_str.split(',') if x.strip()
            ]

        if self.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS is None:
            raw_ids = os.getenv('GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS', '')
            parsed_ids = []
            for chunk in raw_ids.split(','):
                normalized = chunk.strip()
                if not normalized:
                    continue
                try:
                    value = int(float(normalized))
                except ValueError:
                    continue
                if value > 0:
                    parsed_ids.append(value)
            self.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = parsed_ids

        if self.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS is None:
            raw_ids = os.getenv('DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS', '')
            parsed_ids = []
            for chunk in raw_ids.split(','):
                normalized = chunk.strip()
                if not normalized:
                    continue
                try:
                    value = int(float(normalized))
                except ValueError:
                    continue
                if value > 0:
                    parsed_ids.append(value)
            self.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = parsed_ids


# Глобальный экземпляр конфигурации
config = Config()
