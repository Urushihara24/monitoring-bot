"""
Хранилище состояния (SQLite)
"""

import sqlite3
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
from types import SimpleNamespace


class Storage:
    """SQLite хранилище для состояния бота"""
    
    def __init__(self, db_path: str = 'data/state.db'):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_price REAL,
                    last_update TIMESTAMP,
                    last_cycle TIMESTAMP,
                    last_competitor_price REAL,
                    last_competitor_min REAL,
                    last_competitor_rank INTEGER,
                    auto_mode INTEGER DEFAULT 1,
                    update_count INTEGER DEFAULT 0,
                    skip_count INTEGER DEFAULT 0
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    old_price REAL,
                    new_price REAL,
                    competitor_price REAL,
                    reason TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS runtime_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    user_id INTEGER,
                    source TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS alert_state (
                    key TEXT PRIMARY KEY,
                    last_sent TIMESTAMP
                )
            ''')
            
            # Инициализируем запись состояния если нет
            conn.execute('''
                INSERT OR IGNORE INTO state (id, update_count, skip_count)
                VALUES (1, 0, 0)
            ''')

            # Миграция старой схемы (если колонок ещё нет)
            self._ensure_column(conn, 'state', 'last_cycle', 'TIMESTAMP')
            self._ensure_column(conn, 'state', 'last_competitor_rank', 'INTEGER')
            self._ensure_column(conn, 'state', 'auto_mode', 'INTEGER DEFAULT 1')
            
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, column_type: str):
        """Добавляет колонку в таблицу, если она отсутствует"""
        columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        if column not in columns:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {column_type}')
    
    def get_state(self) -> dict:
        """Получение текущего состояния"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('SELECT * FROM state WHERE id = 1')
            row = cursor.fetchone()
            
            if row:
                return {
                    'last_price': row['last_price'],
                    'last_update': datetime.fromisoformat(row['last_update']) if row['last_update'] else None,
                    'last_cycle': datetime.fromisoformat(row['last_cycle']) if row['last_cycle'] else None,
                    'last_competitor_price': row['last_competitor_price'],
                    'last_competitor_min': row['last_competitor_min'],
                    'last_competitor_rank': row['last_competitor_rank'],
                    'auto_mode': bool(row['auto_mode']) if row['auto_mode'] is not None else True,
                    'update_count': row['update_count'],
                    'skip_count': row['skip_count'],
                }
            
            return {
                'last_price': None,
                'last_update': None,
                'last_cycle': None,
                'last_competitor_price': None,
                'last_competitor_min': None,
                'last_competitor_rank': None,
                'auto_mode': True,
                'update_count': 0,
                'skip_count': 0,
            }
    
    def update_state(self, **kwargs):
        """Обновление состояния"""
        allowed_fields = {'last_price', 'last_update', 'last_cycle', 'last_competitor_price',
                         'last_competitor_rank',
                         'last_competitor_min', 'auto_mode', 'update_count', 'skip_count'}
        
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return
        
        # Преобразуем datetime в строку
        if 'last_update' in updates and updates['last_update']:
            updates['last_update'] = updates['last_update'].isoformat()
        if 'last_cycle' in updates and updates['last_cycle']:
            updates['last_cycle'] = updates['last_cycle'].isoformat()
        if 'auto_mode' in updates:
            updates['auto_mode'] = 1 if updates['auto_mode'] else 0
        
        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values())
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(f'UPDATE state SET {set_clause} WHERE id = 1', values)
            conn.commit()
    
    def increment_update_count(self):
        """Увеличение счётчика обновлений"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('UPDATE state SET update_count = update_count + 1 WHERE id = 1')
            conn.commit()
    
    def increment_skip_count(self):
        """Увеличение счётчика пропусков"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('UPDATE state SET skip_count = skip_count + 1 WHERE id = 1')
            conn.commit()
    
    def add_price_history(self, old_price: float, new_price: float, 
                         competitor_price: float, reason: str):
        """Добавление записи в историю цен"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
                INSERT INTO price_history (old_price, new_price, competitor_price, reason)
                VALUES (?, ?, ?, ?)
            ''', (old_price, new_price, competitor_price, reason))
            conn.commit()
    
    def get_last_update(self) -> Optional[datetime]:
        """Получение времени последнего обновления"""
        state = self.get_state()
        return state.get('last_update')
    
    def get_last_price(self) -> Optional[float]:
        """Получение последней цены"""
        state = self.get_state()
        return state.get('last_price')

    # ================================
    # Runtime settings
    # ================================
    def get_runtime_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Получить runtime-настройку по ключу"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT value FROM runtime_settings WHERE key = ?',
                (key,),
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
    ):
        """Установить runtime-настройку"""
        old_value = self.get_runtime_setting(key)
        if old_value == value:
            return

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                '''
                INSERT INTO runtime_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                ''',
                (key, value),
            )
            conn.execute(
                '''
                INSERT INTO settings_history (key, old_value, new_value, user_id, source)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (key, old_value, value, user_id, source),
            )
            conn.commit()

    def get_competitor_urls(self, default_urls: list) -> list:
        """Получить список URL конкурентов из runtime, либо fallback к config"""
        raw = self.get_runtime_setting('competitor_urls')
        if raw is None or not raw.strip():
            return default_urls or []
        return [x.strip() for x in raw.split(',') if x.strip()]

    def set_competitor_urls(self, urls: list, user_id: Optional[int] = None, source: str = 'system'):
        """Сохранить список URL конкурентов в runtime"""
        value = ','.join(urls)
        self.set_runtime_setting('competitor_urls', value, user_id=user_id, source=source)

    def get_runtime_config(self, base_config) -> SimpleNamespace:
        """
        Собирает runtime-конфиг:
        default из base_config + overrides из runtime_settings
        """
        runtime = {
            'MIN_PRICE': self._get_float('MIN_PRICE', base_config.MIN_PRICE),
            'MAX_PRICE': self._get_float('MAX_PRICE', base_config.MAX_PRICE),
            'DESIRED_PRICE': self._get_float('DESIRED_PRICE', base_config.DESIRED_PRICE),
            'UNDERCUT_VALUE': self._get_float('UNDERCUT_VALUE', base_config.UNDERCUT_VALUE),
            'MODE': self._get_str('MODE', base_config.MODE),
            'FIXED_PRICE': self._get_float('FIXED_PRICE', base_config.FIXED_PRICE),
            'STEP_UP_VALUE': self._get_float('STEP_UP_VALUE', base_config.STEP_UP_VALUE),
            'LOW_PRICE_THRESHOLD': self._get_float('LOW_PRICE_THRESHOLD', base_config.LOW_PRICE_THRESHOLD),
            'WEAK_PRICE_CEIL_LIMIT': self._get_float('WEAK_PRICE_CEIL_LIMIT', base_config.WEAK_PRICE_CEIL_LIMIT),
            'POSITION_FILTER_ENABLED': self._get_bool('POSITION_FILTER_ENABLED', base_config.POSITION_FILTER_ENABLED),
            'WEAK_POSITION_THRESHOLD': self._get_int('WEAK_POSITION_THRESHOLD', base_config.WEAK_POSITION_THRESHOLD),
            'COOLDOWN_SECONDS': self._get_int('COOLDOWN_SECONDS', base_config.COOLDOWN_SECONDS),
            'IGNORE_DELTA': self._get_float('IGNORE_DELTA', base_config.IGNORE_DELTA),
            'CHECK_INTERVAL': self._get_int('CHECK_INTERVAL', base_config.CHECK_INTERVAL),
        }
        runtime['COMPETITOR_URLS'] = self.get_competitor_urls(base_config.COMPETITOR_URLS)
        return SimpleNamespace(**runtime)

    def _get_str(self, key: str, default: str) -> str:
        value = self.get_runtime_setting(key)
        return default if value is None else value

    def _get_float(self, key: str, default: float) -> float:
        value = self.get_runtime_setting(key)
        if value is None:
            return default
        try:
            return float(value)
        except Exception:
            return default

    def _get_int(self, key: str, default: int) -> int:
        value = self.get_runtime_setting(key)
        if value is None:
            return default
        try:
            return int(value)
        except Exception:
            return default

    def _get_bool(self, key: str, default: bool) -> bool:
        value = self.get_runtime_setting(key)
        if value is None:
            return default
        return value.strip().lower() in ('1', 'true', 'yes', 'on')

    def get_all_runtime_settings(self) -> Dict[str, str]:
        """Получить все runtime-настройки"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT key, value FROM runtime_settings ORDER BY key').fetchall()
            return {row['key']: row['value'] for row in rows}

    def get_settings_history(self, limit: int = 20) -> List[dict]:
        """Получить историю изменения runtime-настроек"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                '''
                SELECT key, old_value, new_value, user_id, source, timestamp
                FROM settings_history
                ORDER BY id DESC
                LIMIT ?
                ''',
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def should_send_alert(self, key: str, cooldown_seconds: int) -> bool:
        """
        True, если можно отправить alert по ключу.
        Если отправка разрешена — фиксирует время отправки.
        """
        now = datetime.now()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT last_sent FROM alert_state WHERE key = ?',
                (key,),
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
                INSERT INTO alert_state (key, last_sent)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET last_sent = excluded.last_sent
                ''',
                (key, now.isoformat()),
            )
            conn.commit()
            return True


# Глобальный экземпляр
storage = Storage()
