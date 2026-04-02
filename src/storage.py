"""
Хранилище состояния (SQLite) с поддержкой профилей платформ.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

DEFAULT_PROFILE = 'ggsel'


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

            # Создаём базовые записи профилей.
            self._ensure_profile_state(conn, 'ggsel')
            self._ensure_profile_state(conn, 'digiseller')
            conn.commit()

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
                'last_price': row['last_price'],
                'last_update': self._parse_dt(row['last_update']),
                'last_cycle': self._parse_dt(row['last_cycle']),
                'last_competitor_price': row['last_competitor_price'],
                'last_competitor_min': row['last_competitor_min'],
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

    def get_last_update(self, profile_id: str = DEFAULT_PROFILE) -> Optional[datetime]:
        return self.get_state(profile_id).get('last_update')

    def get_last_price(self, profile_id: str = DEFAULT_PROFILE) -> Optional[float]:
        return self.get_state(profile_id).get('last_price')

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
        old_value = self.get_runtime_setting(key, profile_id=profile)
        if old_value == value:
            return
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                '''
                INSERT INTO runtime_settings (profile_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id, key)
                DO UPDATE SET value = excluded.value
                ''',
                (profile, key, value),
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
                (profile, key, old_value, value, user_id, source),
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
            return default_urls or []
        return [x.strip() for x in raw.split(',') if x.strip()]

    def set_competitor_urls(
        self,
        urls: list,
        user_id: Optional[int] = None,
        source: str = 'system',
        profile_id: str = DEFAULT_PROFILE,
    ):
        value = ','.join(urls)
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
            'LOW_PRICE_THRESHOLD': self._get_float(
                'LOW_PRICE_THRESHOLD',
                base_config.LOW_PRICE_THRESHOLD,
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
            'SELENIUM_USE_REAL_PROFILE': self._get_bool(
                'SELENIUM_USE_REAL_PROFILE',
                base_config.SELENIUM_USE_REAL_PROFILE,
                profile,
            ),
            'SELENIUM_CHROME_USER_DATA_DIR': self._get_str(
                'SELENIUM_CHROME_USER_DATA_DIR',
                base_config.SELENIUM_CHROME_USER_DATA_DIR,
                profile,
            ),
            'SELENIUM_CHROME_PROFILE_DIR': self._get_str(
                'SELENIUM_CHROME_PROFILE_DIR',
                base_config.SELENIUM_CHROME_PROFILE_DIR,
                profile,
            ),
            'SELENIUM_HEADLESS': self._get_bool(
                'SELENIUM_HEADLESS',
                base_config.SELENIUM_HEADLESS,
                profile,
            ),
            'RSC_USE_PLAYWRIGHT': self._get_bool(
                'RSC_USE_PLAYWRIGHT',
                base_config.RSC_USE_PLAYWRIGHT,
                profile,
            ),
            'RSC_USE_SELENIUM_FALLBACK': self._get_bool(
                'RSC_USE_SELENIUM_FALLBACK',
                base_config.RSC_USE_SELENIUM_FALLBACK,
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
            return float(value)
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

    def get_all_runtime_settings(
        self,
        profile_id: str = DEFAULT_PROFILE,
    ) -> Dict[str, str]:
        profile = self._normalize_profile(profile_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                '''
                SELECT key, value FROM runtime_settings
                WHERE profile_id = ?
                ORDER BY key
                ''',
                (profile,),
            ).fetchall()
            return {row['key']: row['value'] for row in rows}

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
