"""
Хранилище состояния (SQLite) с поддержкой профилей платформ.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PROFILE = 'ggsel'
PRICE_PRECISION = Decimal('0.0001')
STATE_PRICE_FIELDS = {
    'last_price',
    'last_target_price',
    'last_target_competitor_min',
    'last_competitor_price',
    'last_competitor_min',
}
RUNTIME_PRICE_KEYS = {
    'MIN_PRICE',
    'MAX_PRICE',
    'DESIRED_PRICE',
    'UNDERCUT_VALUE',
    'FIXED_PRICE',
    'STEP_UP_VALUE',
    'WEAK_PRICE_CEIL_LIMIT',
    'IGNORE_DELTA',
    'COMPETITOR_CHANGE_DELTA',
    'MAX_DOWN_STEP',
    'FAST_REBOUND_DELTA',
}


class Storage:
    """SQLite хранилище состояния и runtime-настроек."""

    def __init__(self, db_path: str = 'data/state.db'):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Инициализация БД и миграции."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS profile_state (
                    profile_id TEXT PRIMARY KEY,
                    last_price REAL,
                    last_update TIMESTAMP,
                    last_cycle TIMESTAMP,
                    last_target_price REAL,
                    last_target_competitor_min REAL,
                    last_competitor_price REAL,
                    last_competitor_min REAL,
                    last_competitor_rank INTEGER,
                    last_competitor_url TEXT,
                    last_competitor_parse_at TIMESTAMP,
                    last_competitor_method TEXT,
                    last_competitor_error TEXT,
                    last_competitor_block_reason TEXT,
                    last_competitor_status_code INTEGER,
                    auto_mode INTEGER DEFAULT 1,
                    update_count INTEGER DEFAULT 0,
                    skip_count INTEGER DEFAULT 0
                )
                '''
            )

            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    old_price REAL,
                    new_price REAL,
                    competitor_price REAL,
                    reason TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )

            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS runtime_settings (
                    profile_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (profile_id, key)
                )
                '''
            )

            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS settings_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    user_id INTEGER,
                    source TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )

            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS alert_state (
                    profile_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    last_sent TIMESTAMP,
                    PRIMARY KEY (profile_id, key)
                )
                '''
            )

            # Миграция legacy таблицы state -> profile_state[ggsel].
            self._migrate_legacy_state(conn)
            self._migrate_profile_state_columns(conn)
            self._migrate_price_history_table(conn)
            self._migrate_runtime_settings_table(conn)
            self._migrate_settings_history_table(conn)
            self._migrate_alert_state_table(conn)
            self._backfill_target_state(conn)
            self._normalize_profile_state_prices(conn)

            # Создаём базовые записи профилей.
            self._ensure_profile_state(conn, 'ggsel')
            self._ensure_profile_state(conn, 'digiseller')
            self._normalize_runtime_price_settings(conn)
            conn.commit()

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
        return {row[1] for row in rows}

    def _migrate_profile_state_columns(self, conn: sqlite3.Connection):
        """Добавляет новые колонки в profile_state без потери данных."""
        rows = conn.execute('PRAGMA table_info(profile_state)').fetchall()
        existing = {row[1] for row in rows}
        required = {
            'last_target_price': 'REAL',
            'last_target_competitor_min': 'REAL',
        }
        for column, type_def in required.items():
            if column in existing:
                continue
            conn.execute(
                f'ALTER TABLE profile_state ADD COLUMN {column} {type_def}'
            )

    def _backfill_target_state(self, conn: sqlite3.Connection):
        """
        Заполняет target-поля из текущего состояния, если они пустые.
        Нужно для мягкого апгрейда без "лишнего первого reconcile".
        """
        conn.execute(
            '''
            UPDATE profile_state
            SET last_target_price = last_price
            WHERE last_target_price IS NULL
              AND last_price IS NOT NULL
            '''
        )
        conn.execute(
            '''
            UPDATE profile_state
            SET last_target_competitor_min = last_competitor_min
            WHERE last_target_competitor_min IS NULL
              AND last_competitor_min IS NOT NULL
            '''
        )

    def _normalize_profile_state_prices(self, conn: sqlite3.Connection):
        """Нормализует price-поля profile_state до 4 знаков."""
        for column in STATE_PRICE_FIELDS:
            conn.execute(
                f'''
                UPDATE profile_state
                SET {column} = ROUND({column}, 4)
                WHERE {column} IS NOT NULL
                '''
            )

    def _normalize_runtime_price_settings(self, conn: sqlite3.Connection):
        """Нормализует runtime price-настройки до фиксированного формата 0.0000."""
        placeholders = ', '.join('?' for _ in RUNTIME_PRICE_KEYS)
        rows = conn.execute(
            f'''
            SELECT profile_id, key, value
            FROM runtime_settings
            WHERE key IN ({placeholders})
            ''',
            tuple(RUNTIME_PRICE_KEYS),
        ).fetchall()
        for profile_id, key, value in rows:
            normalized = self._normalize_price(value)
            if normalized is None:
                continue
            formatted = f'{normalized:.4f}'
            if str(value) == formatted:
                continue
            conn.execute(
                '''
                UPDATE runtime_settings
                SET value = ?
                WHERE profile_id = ? AND key = ?
                ''',
                (formatted, profile_id, key),
            )

    def _migrate_runtime_settings_table(self, conn: sqlite3.Connection):
        """
        Миграция legacy runtime_settings(key,value) -> profile runtime_settings.
        """
        columns = self._table_columns(conn, 'runtime_settings')
        if 'profile_id' in columns:
            return

        conn.execute('ALTER TABLE runtime_settings RENAME TO runtime_settings_legacy')
        conn.execute(
            '''
            CREATE TABLE runtime_settings (
                profile_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (profile_id, key)
            )
            '''
        )
        legacy_columns = self._table_columns(conn, 'runtime_settings_legacy')
        if {'key', 'value'}.issubset(legacy_columns):
            conn.execute(
                '''
                INSERT OR REPLACE INTO runtime_settings (profile_id, key, value)
                SELECT ?, key, value
                FROM runtime_settings_legacy
                ''',
                (DEFAULT_PROFILE,),
            )
        conn.execute('DROP TABLE runtime_settings_legacy')

    def _migrate_price_history_table(self, conn: sqlite3.Connection):
        """
        Миграция legacy price_history без profile_id в профильный формат.
        """
        columns = self._table_columns(conn, 'price_history')
        if 'profile_id' in columns:
            return

        conn.execute('ALTER TABLE price_history RENAME TO price_history_legacy')
        conn.execute(
            '''
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                old_price REAL,
                new_price REAL,
                competitor_price REAL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        legacy_columns = self._table_columns(conn, 'price_history_legacy')
        required = {'old_price', 'new_price', 'competitor_price', 'reason'}
        if required.issubset(legacy_columns):
            conn.execute(
                '''
                INSERT INTO price_history (
                    profile_id,
                    old_price,
                    new_price,
                    competitor_price,
                    reason,
                    timestamp
                )
                SELECT
                    ?,
                    old_price,
                    new_price,
                    competitor_price,
                    reason,
                    timestamp
                FROM price_history_legacy
                ''',
                (DEFAULT_PROFILE,),
            )
        conn.execute('DROP TABLE price_history_legacy')

    def _migrate_settings_history_table(self, conn: sqlite3.Connection):
        """
        Миграция legacy settings_history без profile_id в профильный формат.
        """
        columns = self._table_columns(conn, 'settings_history')
        if 'profile_id' in columns:
            return

        conn.execute('ALTER TABLE settings_history RENAME TO settings_history_legacy')
        conn.execute(
            '''
            CREATE TABLE settings_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                user_id INTEGER,
                source TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        legacy_columns = self._table_columns(conn, 'settings_history_legacy')
        required = {'key', 'old_value', 'new_value'}
        if required.issubset(legacy_columns):
            conn.execute(
                '''
                INSERT INTO settings_history (
                    profile_id,
                    key,
                    old_value,
                    new_value,
                    user_id,
                    source,
                    timestamp
                )
                SELECT
                    ?,
                    key,
                    old_value,
                    new_value,
                    user_id,
                    source,
                    timestamp
                FROM settings_history_legacy
                ''',
                (DEFAULT_PROFILE,),
            )
        conn.execute('DROP TABLE settings_history_legacy')

    def _migrate_alert_state_table(self, conn: sqlite3.Connection):
        """
        Миграция legacy alert_state(key,last_sent) -> профильный формат.
        """
        columns = self._table_columns(conn, 'alert_state')
        if 'profile_id' in columns:
            return

        conn.execute('ALTER TABLE alert_state RENAME TO alert_state_legacy')
        conn.execute(
            '''
            CREATE TABLE alert_state (
                profile_id TEXT NOT NULL,
                key TEXT NOT NULL,
                last_sent TIMESTAMP,
                PRIMARY KEY (profile_id, key)
            )
            '''
        )
        legacy_columns = self._table_columns(conn, 'alert_state_legacy')
        if {'key', 'last_sent'}.issubset(legacy_columns):
            conn.execute(
                '''
                INSERT OR REPLACE INTO alert_state (profile_id, key, last_sent)
                SELECT ?, key, last_sent
                FROM alert_state_legacy
                ''',
                (DEFAULT_PROFILE,),
            )
        conn.execute('DROP TABLE alert_state_legacy')

    def _migrate_legacy_state(self, conn: sqlite3.Connection):
        """Перенос legacy state(id=1) в profile_state[ggsel]."""
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if 'state' not in tables:
            return

        row = conn.execute(
            '''
            SELECT last_price, last_update, last_cycle, last_competitor_price,
                   last_competitor_min, last_competitor_rank, auto_mode,
                   update_count, skip_count
            FROM state WHERE id = 1
            '''
        ).fetchone()
        if not row:
            return

        exists = conn.execute(
            'SELECT 1 FROM profile_state WHERE profile_id = ?',
            (DEFAULT_PROFILE,),
        ).fetchone()
        if exists:
            return

        conn.execute(
            '''
            INSERT INTO profile_state (
                profile_id,
                last_price,
                last_update,
                last_cycle,
                last_competitor_price,
                last_competitor_min,
                last_competitor_rank,
                auto_mode,
                update_count,
                skip_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (DEFAULT_PROFILE, *row),
        )

    def _ensure_profile_state(self, conn: sqlite3.Connection, profile_id: str):
        conn.execute(
            '''
            INSERT OR IGNORE INTO profile_state (
                profile_id,
                auto_mode,
                update_count,
                skip_count
            )
            VALUES (?, 1, 0, 0)
            ''',
            (profile_id,),
        )

    def _normalize_profile(self, profile_id: Optional[str]) -> str:
        return (profile_id or DEFAULT_PROFILE).strip().lower()

    def _parse_dt(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    def _normalize_price(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            normalized = Decimal(str(value).replace(',', '.')).quantize(
                PRICE_PRECISION,
                rounding=ROUND_HALF_UP,
            )
            return float(normalized)
        except Exception:
            return None

    def _normalize_competitor_url(self, raw_url: str) -> str:
        raw = (raw_url or '').strip()
        if not raw:
            return ''
        try:
            parsed = urlsplit(raw)
            if parsed.scheme and parsed.netloc:
                path = parsed.path or ''
                if path and path != '/':
                    path = path.rstrip('/')
                return urlunsplit(
                    (
                        parsed.scheme.lower(),
                        parsed.netloc.lower(),
                        path,
                        parsed.query,
                        '',
                    )
                )
        except Exception:
            pass
        if raw.endswith('/') and raw != '/':
            return raw.rstrip('/')
        return raw

    def _normalize_competitor_urls(self, urls: list) -> list:
        result: list[str] = []
        seen: set[str] = set()
        for item in urls or []:
            normalized = self._normalize_competitor_url(str(item))
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def normalize_competitor_urls(self, urls: list) -> list:
        """Публичный helper нормализации/дедупликации URL конкурентов."""
        return self._normalize_competitor_urls(urls)

    # ================================
    # Profile state
    # ================================
    def get_state(self, profile_id: str = DEFAULT_PROFILE) -> dict:
        """Получение текущего состояния профиля."""
        profile = self._normalize_profile(profile_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_profile_state(conn, profile)
            row = conn.execute(
                'SELECT * FROM profile_state WHERE profile_id = ?',
                (profile,),
            ).fetchone()
            if not row:
                return self._default_state()
            return {
                'last_price': self._normalize_price(row['last_price']),
                'last_update': self._parse_dt(row['last_update']),
                'last_cycle': self._parse_dt(row['last_cycle']),
                'last_target_price': self._normalize_price(row['last_target_price']),
                'last_target_competitor_min': self._normalize_price(
                    row['last_target_competitor_min']
                ),
                'last_competitor_price': self._normalize_price(
                    row['last_competitor_price']
                ),
                'last_competitor_min': self._normalize_price(
                    row['last_competitor_min']
                ),
                'last_competitor_rank': row['last_competitor_rank'],
                'last_competitor_url': row['last_competitor_url'],
                'last_competitor_parse_at': self._parse_dt(
                    row['last_competitor_parse_at']
                ),
                'last_competitor_method': row['last_competitor_method'],
                'last_competitor_error': row['last_competitor_error'],
                'last_competitor_block_reason': row['last_competitor_block_reason'],
                'last_competitor_status_code': row['last_competitor_status_code'],
                'auto_mode': bool(row['auto_mode'])
                if row['auto_mode'] is not None else True,
                'update_count': row['update_count'] or 0,
                'skip_count': row['skip_count'] or 0,
            }

    def _default_state(self) -> dict:
        return {
            'last_price': None,
            'last_update': None,
            'last_cycle': None,
            'last_target_price': None,
            'last_target_competitor_min': None,
            'last_competitor_price': None,
            'last_competitor_min': None,
            'last_competitor_rank': None,
            'last_competitor_url': None,
            'last_competitor_parse_at': None,
            'last_competitor_method': None,
            'last_competitor_error': None,
            'last_competitor_block_reason': None,
            'last_competitor_status_code': None,
            'auto_mode': True,
            'update_count': 0,
            'skip_count': 0,
        }

    def update_state(self, profile_id: str = DEFAULT_PROFILE, **kwargs):
        """Обновление состояния профиля."""
        profile = self._normalize_profile(profile_id)
        allowed_fields = {
            'last_price',
            'last_update',
            'last_cycle',
            'last_target_price',
            'last_target_competitor_min',
            'last_competitor_price',
            'last_competitor_min',
            'last_competitor_rank',
            'last_competitor_url',
            'last_competitor_parse_at',
            'last_competitor_method',
            'last_competitor_error',
            'last_competitor_block_reason',
            'last_competitor_status_code',
            'auto_mode',
            'update_count',
            'skip_count',
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return

        for dt_key in (
            'last_update',
            'last_cycle',
            'last_competitor_parse_at',
        ):
            if dt_key in updates and isinstance(updates[dt_key], datetime):
                updates[dt_key] = updates[dt_key].isoformat()
        for price_key in STATE_PRICE_FIELDS:
            if price_key in updates:
                updates[price_key] = self._normalize_price(updates[price_key])
        if 'auto_mode' in updates:
            updates['auto_mode'] = 1 if updates['auto_mode'] else 0

        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values())
        with sqlite3.connect(str(self.db_path)) as conn:
            self._ensure_profile_state(conn, profile)
            conn.execute(
                f'UPDATE profile_state SET {set_clause} WHERE profile_id = ?',
                values + [profile],
            )
            conn.commit()

    def increment_update_count(self, profile_id: str = DEFAULT_PROFILE):
        profile = self._normalize_profile(profile_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            self._ensure_profile_state(conn, profile)
            conn.execute(
                '''
                UPDATE profile_state
                SET update_count = update_count + 1
                WHERE profile_id = ?
                ''',
                (profile,),
            )
            conn.commit()

    def increment_skip_count(self, profile_id: str = DEFAULT_PROFILE):
        profile = self._normalize_profile(profile_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            self._ensure_profile_state(conn, profile)
            conn.execute(
                '''
                UPDATE profile_state
                SET skip_count = skip_count + 1
                WHERE profile_id = ?
                ''',
                (profile,),
            )
            conn.commit()

    def add_price_history(
        self,
        old_price: float,
        new_price: float,
        competitor_price: float,
        reason: str,
        profile_id: str = DEFAULT_PROFILE,
    ):
        profile = self._normalize_profile(profile_id)
        old_price = self._normalize_price(old_price)
        new_price = self._normalize_price(new_price)
        competitor_price = self._normalize_price(competitor_price)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                '''
                INSERT INTO price_history (
                    profile_id,
                    old_price,
                    new_price,
                    competitor_price,
                    reason
                )
                VALUES (?, ?, ?, ?, ?)
                ''',
                (profile, old_price, new_price, competitor_price, reason),
            )
            conn.commit()

    # ================================
    # Runtime settings
    # ================================
    def get_runtime_setting(
        self,
        key: str,
        default: Optional[str] = None,
        profile_id: str = DEFAULT_PROFILE,
    ) -> Optional[str]:
        profile = self._normalize_profile(profile_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                '''
                SELECT value FROM runtime_settings
                WHERE profile_id = ? AND key = ?
                ''',
                (profile, key),
            ).fetchone()
            if not row:
                return default
            return row['value']

    def set_runtime_setting(
        self,
        key: str,
        value: str,
        user_id: Optional[int] = None,
        source: str = 'system',
        profile_id: str = DEFAULT_PROFILE,
    ):
        profile = self._normalize_profile(profile_id)
        normalized_value = str(value)
        if key in RUNTIME_PRICE_KEYS:
            price_value = self._normalize_price(normalized_value)
            if price_value is not None:
                normalized_value = f'{price_value:.4f}'

        old_value = self.get_runtime_setting(key, profile_id=profile)
        if old_value == normalized_value:
            return
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                '''
                INSERT INTO runtime_settings (profile_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id, key)
                DO UPDATE SET value = excluded.value
                ''',
                (profile, key, normalized_value),
            )
            conn.execute(
                '''
                INSERT INTO settings_history (
                    profile_id,
                    key,
                    old_value,
                    new_value,
                    user_id,
                    source
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    profile,
                    key,
                    old_value,
                    normalized_value,
                    user_id,
                    source,
                ),
            )
            conn.commit()

    def get_competitor_urls(
        self,
        default_urls: list,
        profile_id: str = DEFAULT_PROFILE,
    ) -> list:
        raw = self.get_runtime_setting(
            'competitor_urls',
            profile_id=profile_id,
        )
        if raw is None or not raw.strip():
            return self._normalize_competitor_urls(default_urls or [])
        return self._normalize_competitor_urls(raw.split(','))

    def set_competitor_urls(
        self,
        urls: list,
        user_id: Optional[int] = None,
        source: str = 'system',
        profile_id: str = DEFAULT_PROFILE,
    ):
        normalized = self._normalize_competitor_urls(urls or [])
        value = ','.join(normalized)
        self.set_runtime_setting(
            'competitor_urls',
            value,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def get_runtime_config(
        self,
        base_config,
        profile_id: str = DEFAULT_PROFILE,
        default_urls: Optional[list] = None,
    ) -> SimpleNamespace:
        profile = self._normalize_profile(profile_id)
        runtime = {
            'MIN_PRICE': self._get_float('MIN_PRICE', base_config.MIN_PRICE, profile),
            'MAX_PRICE': self._get_float('MAX_PRICE', base_config.MAX_PRICE, profile),
            'DESIRED_PRICE': self._get_float(
                'DESIRED_PRICE',
                base_config.DESIRED_PRICE,
                profile,
            ),
            'UNDERCUT_VALUE': self._get_float(
                'UNDERCUT_VALUE',
                base_config.UNDERCUT_VALUE,
                profile,
            ),
            'MODE': self._get_str('MODE', base_config.MODE, profile),
            'FIXED_PRICE': self._get_float(
                'FIXED_PRICE',
                base_config.FIXED_PRICE,
                profile,
            ),
            'STEP_UP_VALUE': self._get_float(
                'STEP_UP_VALUE',
                base_config.STEP_UP_VALUE,
                profile,
            ),
            'WEAK_PRICE_CEIL_LIMIT': self._get_float(
                'WEAK_PRICE_CEIL_LIMIT',
                base_config.WEAK_PRICE_CEIL_LIMIT,
                profile,
            ),
            'POSITION_FILTER_ENABLED': self._get_bool(
                'POSITION_FILTER_ENABLED',
                base_config.POSITION_FILTER_ENABLED,
                profile,
            ),
            'WEAK_POSITION_THRESHOLD': self._get_int(
                'WEAK_POSITION_THRESHOLD',
                base_config.WEAK_POSITION_THRESHOLD,
                profile,
            ),
            'COOLDOWN_SECONDS': self._get_int(
                'COOLDOWN_SECONDS',
                base_config.COOLDOWN_SECONDS,
                profile,
            ),
            'IGNORE_DELTA': self._get_float(
                'IGNORE_DELTA',
                base_config.IGNORE_DELTA,
                profile,
            ),
            'CHECK_INTERVAL': self._get_int(
                'CHECK_INTERVAL',
                base_config.CHECK_INTERVAL,
                profile,
            ),
            'FAST_CHECK_INTERVAL_MIN': self._get_int(
                'FAST_CHECK_INTERVAL_MIN',
                base_config.FAST_CHECK_INTERVAL_MIN,
                profile,
            ),
            'FAST_CHECK_INTERVAL_MAX': self._get_int(
                'FAST_CHECK_INTERVAL_MAX',
                base_config.FAST_CHECK_INTERVAL_MAX,
                profile,
            ),
            'COMPETITOR_COOKIES': self._get_str(
                'COMPETITOR_COOKIES',
                base_config.COMPETITOR_COOKIES,
                profile,
            ),
            'NOTIFY_SKIP': self._get_bool(
                'NOTIFY_SKIP',
                base_config.NOTIFY_SKIP,
                profile,
            ),
            'NOTIFY_SKIP_COOLDOWN_SECONDS': self._get_int(
                'NOTIFY_SKIP_COOLDOWN_SECONDS',
                base_config.NOTIFY_SKIP_COOLDOWN_SECONDS,
                profile,
            ),
            'NOTIFY_COMPETITOR_CHANGE': self._get_bool(
                'NOTIFY_COMPETITOR_CHANGE',
                base_config.NOTIFY_COMPETITOR_CHANGE,
                profile,
            ),
            'COMPETITOR_CHANGE_DELTA': self._get_float(
                'COMPETITOR_CHANGE_DELTA',
                base_config.COMPETITOR_CHANGE_DELTA,
                profile,
            ),
            'COMPETITOR_CHANGE_COOLDOWN_SECONDS': self._get_int(
                'COMPETITOR_CHANGE_COOLDOWN_SECONDS',
                base_config.COMPETITOR_CHANGE_COOLDOWN_SECONDS,
                profile,
            ),
            'UPDATE_ONLY_ON_COMPETITOR_CHANGE': self._get_bool(
                'UPDATE_ONLY_ON_COMPETITOR_CHANGE',
                base_config.UPDATE_ONLY_ON_COMPETITOR_CHANGE,
                profile,
            ),
            'NOTIFY_PARSER_ISSUES': self._get_bool(
                'NOTIFY_PARSER_ISSUES',
                base_config.NOTIFY_PARSER_ISSUES,
                profile,
            ),
            'PARSER_ISSUE_COOLDOWN_SECONDS': self._get_int(
                'PARSER_ISSUE_COOLDOWN_SECONDS',
                base_config.PARSER_ISSUE_COOLDOWN_SECONDS,
                profile,
            ),
            'HARD_FLOOR_ENABLED': self._get_bool(
                'HARD_FLOOR_ENABLED',
                base_config.HARD_FLOOR_ENABLED,
                profile,
            ),
            'MAX_DOWN_STEP': self._get_float(
                'MAX_DOWN_STEP',
                base_config.MAX_DOWN_STEP,
                profile,
            ),
            'FAST_REBOUND_DELTA': self._get_float(
                'FAST_REBOUND_DELTA',
                base_config.FAST_REBOUND_DELTA,
                profile,
            ),
            'FAST_REBOUND_BYPASS_COOLDOWN': self._get_bool(
                'FAST_REBOUND_BYPASS_COOLDOWN',
                base_config.FAST_REBOUND_BYPASS_COOLDOWN,
                profile,
            ),
        }
        runtime['COMPETITOR_URLS'] = self.get_competitor_urls(
            default_urls=default_urls or base_config.COMPETITOR_URLS,
            profile_id=profile,
        )
        return SimpleNamespace(**runtime)

    def _get_str(self, key: str, default: str, profile_id: str) -> str:
        value = self.get_runtime_setting(key, profile_id=profile_id)
        return default if value is None else value

    def _get_float(self, key: str, default: float, profile_id: str) -> float:
        value = self.get_runtime_setting(key, profile_id=profile_id)
        if value is None:
            return default
        try:
            parsed = float(value)
            if key in RUNTIME_PRICE_KEYS:
                normalized = self._normalize_price(parsed)
                return default if normalized is None else normalized
            return parsed
        except Exception:
            return default

    def _get_int(self, key: str, default: int, profile_id: str) -> int:
        value = self.get_runtime_setting(key, profile_id=profile_id)
        if value is None:
            return default
        try:
            return int(value)
        except Exception:
            return default

    def _get_bool(self, key: str, default: bool, profile_id: str) -> bool:
        value = self.get_runtime_setting(key, profile_id=profile_id)
        if value is None:
            return default
        return value.strip().lower() in ('1', 'true', 'yes', 'on')

    def get_settings_history(
        self,
        limit: int = 20,
        profile_id: str = DEFAULT_PROFILE,
    ) -> List[dict]:
        profile = self._normalize_profile(profile_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                '''
                SELECT key, old_value, new_value, user_id, source, timestamp
                FROM settings_history
                WHERE profile_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (profile, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    # ================================
    # Alert throttling
    # ================================
    def should_send_alert(
        self,
        key: str,
        cooldown_seconds: int,
        profile_id: str = DEFAULT_PROFILE,
    ) -> bool:
        profile = self._normalize_profile(profile_id)
        now = datetime.now()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                '''
                SELECT last_sent FROM alert_state
                WHERE profile_id = ? AND key = ?
                ''',
                (profile, key),
            ).fetchone()

            if row and row['last_sent']:
                try:
                    last_sent = datetime.fromisoformat(row['last_sent'])
                    if (now - last_sent).total_seconds() < cooldown_seconds:
                        return False
                except Exception:
                    pass

            conn.execute(
                '''
                INSERT INTO alert_state (profile_id, key, last_sent)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id, key)
                DO UPDATE SET last_sent = excluded.last_sent
                ''',
                (profile, key, now.isoformat()),
            )
            conn.commit()
            return True


# Глобальный экземпляр
storage = Storage()
