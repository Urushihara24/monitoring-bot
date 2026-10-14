"""Typed configuration loader for the auto-pricing service."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Optional

from dotenv import load_dotenv

from .config_env import normalize_typed_environment

load_dotenv()

_ID_KEYS = (
    'GGSEL_SELLER_ID',
    'GGSEL_PRODUCT_ID',
    'DIGISELLER_SELLER_ID',
    'DIGISELLER_PRODUCT_ID',
)


class ConfigError(ValueError):
    """Raised when explicitly configured environment values are invalid."""


def _prepare_environment(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return one validated, canonical environment snapshot."""
    source = os.environ if env is None else env
    values = {str(key): str(value) for key, value in source.items()}

    # Seller/product IDs are optional at bootstrap but must always be numeric.
    for key in _ID_KEYS:
        if not values.get(key, '').strip():
            values[key] = '0'

    errors = normalize_typed_environment(values)
    if errors:
        details = '\n'.join(f'- {error}' for error in errors)
        raise ConfigError(f'Invalid configuration:\n{details}')
    return values


def _string(values: Mapping[str, str], name: str, default: str = '') -> str:
    raw = values.get(name)
    return default if raw is None else str(raw).strip()


def _optional_string(
    values: Mapping[str, str],
    name: str,
) -> Optional[str]:
    raw = values.get(name)
    if raw is None:
        return None
    normalized = str(raw).strip()
    return normalized or None


def _integer(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    return default if raw is None or not str(raw).strip() else int(str(raw))


def _optional_integer(
    values: Mapping[str, str],
    name: str,
) -> Optional[int]:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return None
    return int(str(raw))


def _number(values: Mapping[str, str], name: str, default: float) -> float:
    raw = values.get(name)
    return default if raw is None or not str(raw).strip() else float(str(raw))


def _optional_number(
    values: Mapping[str, str],
    name: str,
) -> Optional[float]:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return None
    return float(str(raw))


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() == 'true'


def _optional_boolean(
    values: Mapping[str, str],
    name: str,
) -> Optional[bool]:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower() == 'true'


def _csv_strings(values: Mapping[str, str], name: str) -> list[str]:
    raw = values.get(name, '')
    return [item.strip() for item in str(raw).split(',') if item.strip()]


def _csv_integers(values: Mapping[str, str], name: str) -> list[int]:
    raw = values.get(name, '')
    return [int(item.strip()) for item in str(raw).split(',') if item.strip()]


class Config:
    """Validated configuration snapshot.

    Construction is explicit and side-effect free apart from reading the supplied
    environment mapping.  No field is evaluated at class-definition time.
    """

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        values = _prepare_environment(env)

        # Runtime / Telegram.
        self.ENV_FILE_PATH = _string(values, 'ENV_FILE_PATH', '.env')
        self.TELEGRAM_BOT_TOKEN = _string(values, 'TELEGRAM_BOT_TOKEN')
        self.TELEGRAM_ADMIN_IDS = _csv_integers(values, 'TELEGRAM_ADMIN_IDS')

        # GGSEL API/profile.
        self.GGSEL_API_KEY = _string(values, 'GGSEL_API_KEY')
        self.GGSEL_API_SECRET = _string(values, 'GGSEL_API_SECRET')
        self.GGSEL_ACCESS_TOKEN = _string(values, 'GGSEL_ACCESS_TOKEN')
        self.GGSEL_SELLER_ID = _integer(values, 'GGSEL_SELLER_ID', 0)
        self.GGSEL_PRODUCT_ID = _integer(values, 'GGSEL_PRODUCT_ID', 0)
        self.GGSEL_BASE_URL = _string(
            values,
            'GGSEL_BASE_URL',
            'https://back-office.ggsel.com/api_sellers/api',
        )
        self.GGSEL_LANG = _string(values, 'GGSEL_LANG', 'ru-RU')
        self.GGSEL_REQUIRE_API_ON_START = _boolean(
            values, 'GGSEL_REQUIRE_API_ON_START', False
        )
        self.GGSEL_ENABLED = _boolean(values, 'GGSEL_ENABLED', True)
        self.GGSEL_CHAT_AUTOREPLY_ENABLED = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_ENABLED', False
        )
        self.GGSEL_CHAT_AUTOREPLY_PAGE_SIZE = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_PAGE_SIZE', 50
        )
        self.GGSEL_CHAT_AUTOREPLY_MAX_PAGES = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_MAX_PAGES', 2
        )
        self.GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS', 30
        )
        self.GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES', True
        )
        self.GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT', True
        )
        self.GGSEL_CHAT_AUTOREPLY_SMART_NON_EMPTY = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_SMART_NON_EMPTY', False
        )
        self.GGSEL_CHAT_AUTOREPLY_REQUIRE_RULES = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_REQUIRE_RULES', True
        )
        self.GGSEL_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT', True
        )
        self.GGSEL_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK', False
        )
        self.GGSEL_CHAT_AUTOREPLY_POLICY = _string(
            values, 'GGSEL_CHAT_AUTOREPLY_POLICY', 'ON_ORDER'
        )
        self.GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', 30
        )
        self.GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES', 20
        )
        self.GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK = _boolean(
            values, 'GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK', False
        )
        self.GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS', 30
        )
        self.GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS = _integer(
            values, 'GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS', 24
        )
        self.GGSEL_CHAT_TEMPLATE_RU_ALREADY = _string(
            values, 'GGSEL_CHAT_TEMPLATE_RU_ALREADY'
        )
        self.GGSEL_CHAT_TEMPLATE_RU_ADD = _string(
            values, 'GGSEL_CHAT_TEMPLATE_RU_ADD'
        )
        self.GGSEL_CHAT_TEMPLATE_EN_ALREADY = _string(
            values, 'GGSEL_CHAT_TEMPLATE_EN_ALREADY'
        )
        self.GGSEL_CHAT_TEMPLATE_EN_ADD = _string(
            values, 'GGSEL_CHAT_TEMPLATE_EN_ADD'
        )

        # DigiSeller API/profile.
        self.DIGISELLER_API_KEY = _string(values, 'DIGISELLER_API_KEY')
        self.DIGISELLER_API_SECRET = _string(values, 'DIGISELLER_API_SECRET')
        self.DIGISELLER_ACCESS_TOKEN = _string(values, 'DIGISELLER_ACCESS_TOKEN')
        self.DIGISELLER_SELLER_ID = _integer(values, 'DIGISELLER_SELLER_ID', 0)
        self.DIGISELLER_PRODUCT_ID = _integer(values, 'DIGISELLER_PRODUCT_ID', 0)
        self.DIGISELLER_BASE_URL = _string(
            values,
            'DIGISELLER_BASE_URL',
            'https://api.digiseller.com/api',
        )
        self.DIGISELLER_LANG = _string(values, 'DIGISELLER_LANG', 'ru-RU')
        self.DIGISELLER_REQUIRE_API_ON_START = _boolean(
            values, 'DIGISELLER_REQUIRE_API_ON_START', False
        )
        self.DIGISELLER_ENABLED = _boolean(values, 'DIGISELLER_ENABLED', False)
        self.DIGISELLER_CHAT_AUTOREPLY_ENABLED = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_ENABLED', False
        )
        self.DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE', 50
        )
        self.DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES', 2
        )
        self.DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS', 30
        )
        self.DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES', True
        )
        self.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT', True
        )
        self.DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY', False
        )
        self.DIGISELLER_CHAT_AUTOREPLY_REQUIRE_RULES = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_REQUIRE_RULES', True
        )
        self.DIGISELLER_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT', True
        )
        self.DIGISELLER_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK', False
        )
        self.DIGISELLER_CHAT_AUTOREPLY_POLICY = _string(
            values, 'DIGISELLER_CHAT_AUTOREPLY_POLICY', 'ON_ORDER'
        )
        self.DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', 30
        )
        self.DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES', 20
        )
        self.DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK = _boolean(
            values, 'DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK', True
        )
        self.DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS', 30
        )
        self.DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS = _integer(
            values, 'DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS', 24
        )
        self.DIGISELLER_CHAT_TEMPLATE_RU_ALREADY = _string(
            values, 'DIGISELLER_CHAT_TEMPLATE_RU_ALREADY'
        )
        self.DIGISELLER_CHAT_TEMPLATE_RU_ADD = _string(
            values, 'DIGISELLER_CHAT_TEMPLATE_RU_ADD'
        )
        self.DIGISELLER_CHAT_TEMPLATE_EN_ALREADY = _string(
            values, 'DIGISELLER_CHAT_TEMPLATE_EN_ALREADY'
        )
        self.DIGISELLER_CHAT_TEMPLATE_EN_ADD = _string(
            values, 'DIGISELLER_CHAT_TEMPLATE_EN_ADD'
        )

        # Optional DigiSeller profile runtime defaults.
        self.DIGISELLER_MIN_PRICE = _optional_number(values, 'DIGISELLER_MIN_PRICE')
        self.DIGISELLER_MAX_PRICE = _optional_number(values, 'DIGISELLER_MAX_PRICE')
        self.DIGISELLER_DESIRED_PRICE = _optional_number(
            values, 'DIGISELLER_DESIRED_PRICE'
        )
        self.DIGISELLER_UNDERCUT_VALUE = _optional_number(
            values, 'DIGISELLER_UNDERCUT_VALUE'
        )
        self.DIGISELLER_RAISE_VALUE = _optional_number(
            values, 'DIGISELLER_RAISE_VALUE'
        )
        self.DIGISELLER_SHOWCASE_ROUND_STEP = _optional_number(
            values, 'DIGISELLER_SHOWCASE_ROUND_STEP'
        )
        self.DIGISELLER_REBOUND_TO_DESIRED_ON_MIN = _optional_boolean(
            values, 'DIGISELLER_REBOUND_TO_DESIRED_ON_MIN'
        )
        self.DIGISELLER_MODE = _optional_string(values, 'DIGISELLER_MODE')
        self.DIGISELLER_FIXED_PRICE = _optional_number(
            values, 'DIGISELLER_FIXED_PRICE'
        )
        self.DIGISELLER_STEP_UP_VALUE = _optional_number(
            values, 'DIGISELLER_STEP_UP_VALUE'
        )
        self.DIGISELLER_WEAK_PRICE_CEIL_LIMIT = _optional_number(
            values, 'DIGISELLER_WEAK_PRICE_CEIL_LIMIT'
        )
        self.DIGISELLER_POSITION_FILTER_ENABLED = _optional_boolean(
            values, 'DIGISELLER_POSITION_FILTER_ENABLED'
        )
        self.DIGISELLER_WEAK_POSITION_THRESHOLD = _optional_integer(
            values, 'DIGISELLER_WEAK_POSITION_THRESHOLD'
        )
        self.DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED = _optional_boolean(
            values, 'DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED'
        )
        self.DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP = _optional_number(
            values, 'DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP'
        )
        self.DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP = _optional_number(
            values, 'DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP'
        )
        self.DIGISELLER_CHECK_INTERVAL = _optional_integer(
            values, 'DIGISELLER_CHECK_INTERVAL'
        )
        self.DIGISELLER_FAST_CHECK_INTERVAL_MIN = _optional_integer(
            values, 'DIGISELLER_FAST_CHECK_INTERVAL_MIN'
        )
        self.DIGISELLER_FAST_CHECK_INTERVAL_MAX = _optional_integer(
            values, 'DIGISELLER_FAST_CHECK_INTERVAL_MAX'
        )
        self.DIGISELLER_COOLDOWN_SECONDS = _optional_integer(
            values, 'DIGISELLER_COOLDOWN_SECONDS'
        )
        self.DIGISELLER_IGNORE_DELTA = _optional_number(
            values, 'DIGISELLER_IGNORE_DELTA'
        )
        self.DIGISELLER_NOTIFY_SKIP = _optional_boolean(
            values, 'DIGISELLER_NOTIFY_SKIP'
        )
        self.DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS = _optional_integer(
            values, 'DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS'
        )
        self.DIGISELLER_NOTIFY_COMPETITOR_CHANGE = _optional_boolean(
            values, 'DIGISELLER_NOTIFY_COMPETITOR_CHANGE'
        )
        self.DIGISELLER_COMPETITOR_CHANGE_DELTA = _optional_number(
            values, 'DIGISELLER_COMPETITOR_CHANGE_DELTA'
        )
        self.DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS = _optional_integer(
            values, 'DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS'
        )
        self.DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE = _optional_boolean(
            values, 'DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE'
        )
        self.DIGISELLER_NOTIFY_PARSER_ISSUES = _optional_boolean(
            values, 'DIGISELLER_NOTIFY_PARSER_ISSUES'
        )
        self.DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS = _optional_integer(
            values, 'DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS'
        )
        self.DIGISELLER_HARD_FLOOR_ENABLED = _optional_boolean(
            values, 'DIGISELLER_HARD_FLOOR_ENABLED'
        )
        self.DIGISELLER_MAX_DOWN_STEP = _optional_number(
            values, 'DIGISELLER_MAX_DOWN_STEP'
        )
        self.DIGISELLER_FAST_REBOUND_DELTA = _optional_number(
            values, 'DIGISELLER_FAST_REBOUND_DELTA'
        )
        self.DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN = _optional_boolean(
            values, 'DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN'
        )

        # Competitor/parser settings.
        self.COMPETITOR_URLS = _csv_strings(values, 'COMPETITOR_URLS')
        ggsel_urls = _csv_strings(values, 'GGSEL_COMPETITOR_URLS')
        self.GGSEL_COMPETITOR_URLS = ggsel_urls or list(self.COMPETITOR_URLS)
        self.DIGISELLER_COMPETITOR_URLS = _csv_strings(
            values, 'DIGISELLER_COMPETITOR_URLS'
        )
        self.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS = _csv_integers(
            values, 'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS'
        )
        self.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS = _csv_integers(
            values, 'DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS'
        )
        self.COMPETITOR_COOKIES = _string(values, 'COMPETITOR_COOKIES')
        self.COMPETITOR_COOKIES_BACKUP_PATH = _string(
            values,
            'COMPETITOR_COOKIES_BACKUP_PATH',
            'data/cookies_backup.json',
        )
        self.RSC_MAX_RETRIES = _integer(values, 'RSC_MAX_RETRIES', 2)

        # Shared pricing defaults.
        self.MIN_PRICE = _number(values, 'MIN_PRICE', 0.25)
        self.MAX_PRICE = _number(values, 'MAX_PRICE', 10.0)
        self.DESIRED_PRICE = _number(values, 'DESIRED_PRICE', 0.35)
        self.UNDERCUT_VALUE = _number(values, 'UNDERCUT_VALUE', 0.0051)
        self.RAISE_VALUE = _number(values, 'RAISE_VALUE', 0.0049)
        self.SHOWCASE_ROUND_STEP = _number(values, 'SHOWCASE_ROUND_STEP', 0.01)
        self.REBOUND_TO_DESIRED_ON_MIN = _boolean(
            values, 'REBOUND_TO_DESIRED_ON_MIN', False
        )
        self.MODE = _string(values, 'MODE', 'DUMPING')
        self.FIXED_PRICE = _number(values, 'FIXED_PRICE', 0.35)
        self.STEP_UP_VALUE = _number(values, 'STEP_UP_VALUE', 0.05)
        self.WEAK_PRICE_CEIL_LIMIT = _number(
            values, 'WEAK_PRICE_CEIL_LIMIT', 0.3
        )
        self.POSITION_FILTER_ENABLED = _boolean(
            values, 'POSITION_FILTER_ENABLED', False
        )
        self.WEAK_POSITION_THRESHOLD = _integer(
            values, 'WEAK_POSITION_THRESHOLD', 20
        )
        self.WEAK_UNKNOWN_RANK_ENABLED = _boolean(
            values, 'WEAK_UNKNOWN_RANK_ENABLED', True
        )
        self.WEAK_UNKNOWN_RANK_ABS_GAP = _number(
            values, 'WEAK_UNKNOWN_RANK_ABS_GAP', 0.03
        )
        self.WEAK_UNKNOWN_RANK_REL_GAP = _number(
            values, 'WEAK_UNKNOWN_RANK_REL_GAP', 0.08
        )
        self.COOLDOWN_SECONDS = _integer(values, 'COOLDOWN_SECONDS', 30)
        self.IGNORE_DELTA = _number(values, 'IGNORE_DELTA', 0.001)
        self.CHECK_INTERVAL = _integer(values, 'CHECK_INTERVAL', 30)
        self.FAST_CHECK_INTERVAL_MIN = _integer(
            values, 'FAST_CHECK_INTERVAL_MIN', 20
        )
        self.FAST_CHECK_INTERVAL_MAX = _integer(
            values, 'FAST_CHECK_INTERVAL_MAX', 60
        )

        # Notifications / loss protection.
        self.NOTIFY_SKIP = _boolean(values, 'NOTIFY_SKIP', False)
        self.NOTIFY_SKIP_COOLDOWN_SECONDS = _integer(
            values, 'NOTIFY_SKIP_COOLDOWN_SECONDS', 300
        )
        self.NOTIFY_COMPETITOR_CHANGE = _boolean(
            values, 'NOTIFY_COMPETITOR_CHANGE', True
        )
        self.COMPETITOR_CHANGE_DELTA = _number(
            values, 'COMPETITOR_CHANGE_DELTA', 0.0001
        )
        self.COMPETITOR_CHANGE_COOLDOWN_SECONDS = _integer(
            values, 'COMPETITOR_CHANGE_COOLDOWN_SECONDS', 60
        )
        self.UPDATE_ONLY_ON_COMPETITOR_CHANGE = _boolean(
            values, 'UPDATE_ONLY_ON_COMPETITOR_CHANGE', True
        )
        self.NOTIFY_PARSER_ISSUES = _boolean(
            values, 'NOTIFY_PARSER_ISSUES', True
        )
        self.PARSER_ISSUE_COOLDOWN_SECONDS = _integer(
            values, 'PARSER_ISSUE_COOLDOWN_SECONDS', 300
        )
        self.NOTIFY_ERRORS = _boolean(values, 'NOTIFY_ERRORS', True)
        self.HARD_FLOOR_ENABLED = _boolean(values, 'HARD_FLOOR_ENABLED', True)
        self.MAX_DOWN_STEP = _number(values, 'MAX_DOWN_STEP', 0.03)
        self.FAST_REBOUND_DELTA = _number(values, 'FAST_REBOUND_DELTA', 0.01)
        self.FAST_REBOUND_BYPASS_COOLDOWN = _boolean(
            values, 'FAST_REBOUND_BYPASS_COOLDOWN', True
        )

        # Logging.
        self.LOG_LEVEL = _string(values, 'LOG_LEVEL', 'INFO')
        self.LOG_MAX_BYTES = _integer(
            values, 'LOG_MAX_BYTES', 10 * 1024 * 1024
        )
        self.LOG_BACKUP_COUNT = _integer(values, 'LOG_BACKUP_COUNT', 5)


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build one fail-closed typed configuration snapshot."""
    return Config(env)


config = load_config()
