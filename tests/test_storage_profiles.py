from datetime import datetime, timedelta
import sqlite3

from src.storage import Storage


def test_profile_state_isolation(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    storage.update_state(profile_id='ggsel', last_price=0.31, update_count=5)
    storage.update_state(profile_id='digiseller', last_price=0.41, update_count=2)

    gg = storage.get_state(profile_id='ggsel')
    dg = storage.get_state(profile_id='digiseller')

    assert gg['last_price'] == 0.31
    assert dg['last_price'] == 0.41
    assert gg['update_count'] == 5
    assert dg['update_count'] == 2


def test_runtime_setting_isolation(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    storage.set_runtime_setting('CHECK_INTERVAL', '20', profile_id='ggsel')
    storage.set_runtime_setting('CHECK_INTERVAL', '55', profile_id='digiseller')

    assert storage.get_runtime_setting('CHECK_INTERVAL', profile_id='ggsel') == '20'
    assert (
        storage.get_runtime_setting('CHECK_INTERVAL', profile_id='digiseller')
        == '55'
    )


def test_runtime_settings_list_and_delete_by_prefix(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:1',
        '2026-04-01T10:00:00',
        profile_id='digiseller',
    )
    storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:2',
        '2026-04-02T10:00:00',
        profile_id='digiseller',
    )
    storage.set_runtime_setting(
        'OTHER_KEY',
        'value',
        profile_id='digiseller',
    )

    rows = storage.list_runtime_settings(
        profile_id='digiseller',
        key_prefix='CHAT_AUTOREPLY_SENT:',
    )
    keys = [row['key'] for row in rows]
    assert keys == ['CHAT_AUTOREPLY_SENT:1', 'CHAT_AUTOREPLY_SENT:2']

    deleted = storage.delete_runtime_setting(
        'CHAT_AUTOREPLY_SENT:1',
        profile_id='digiseller',
        source='test_cleanup',
    )
    assert deleted is True
    assert (
        storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SENT:1',
            profile_id='digiseller',
        ) is None
    )
    assert (
        storage.get_runtime_setting('OTHER_KEY', profile_id='digiseller')
        == 'value'
    )


def test_runtime_settings_with_last_change_returns_timestamp(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:42',
        '2026-04-02T10:00:00',
        profile_id='digiseller',
    )

    rows = storage.list_runtime_settings_with_last_change(
        profile_id='digiseller',
        key_prefix='CHAT_AUTOREPLY_SENT:',
    )
    assert len(rows) == 1
    assert rows[0]['key'] == 'CHAT_AUTOREPLY_SENT:42'
    assert rows[0]['last_change'] is not None


def test_runtime_settings_with_last_change_keeps_profile_isolation(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:42',
        '2026-04-02T10:00:00',
        profile_id='ggsel',
    )
    storage.set_runtime_setting(
        'CHAT_AUTOREPLY_SENT:42',
        '2026-04-03T10:00:00',
        profile_id='digiseller',
    )

    rows = storage.list_runtime_settings_with_last_change(
        profile_id='digiseller',
        key_prefix='CHAT_AUTOREPLY_SENT:',
    )
    assert len(rows) == 1
    assert rows[0]['key'] == 'CHAT_AUTOREPLY_SENT:42'
    assert rows[0]['value'] == '2026-04-03T10:00:00'
    assert rows[0]['last_change'] is not None


def test_competitor_urls_profile_specific(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.set_competitor_urls(
        ['https://a.example'],
        profile_id='ggsel',
    )
    storage.set_competitor_urls(
        ['https://b.example', 'https://c.example'],
        profile_id='digiseller',
    )

    assert storage.get_competitor_urls([], profile_id='ggsel') == ['https://a.example']
    assert storage.get_competitor_urls([], profile_id='digiseller') == [
        'https://b.example',
        'https://c.example',
    ]


def test_competitor_urls_profile_specific_are_deduplicated(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.set_competitor_urls(
        [
            'https://a.example/item-1/',
            'https://a.example/item-1',
            'https://a.example/item-1#x',
        ],
        profile_id='ggsel',
    )
    storage.set_competitor_urls(
        [
            'https://b.example/item-2/',
            'https://b.example/item-2',
        ],
        profile_id='digiseller',
    )

    assert storage.get_competitor_urls([], profile_id='ggsel') == [
        'https://a.example/item-1'
    ]
    assert storage.get_competitor_urls([], profile_id='digiseller') == [
        'https://b.example/item-2'
    ]


def test_alert_throttle_per_profile(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    assert storage.should_send_alert('x', cooldown_seconds=60, profile_id='ggsel')
    assert not storage.should_send_alert('x', cooldown_seconds=60, profile_id='ggsel')

    # Другой профиль не должен быть задушен.
    assert storage.should_send_alert('x', cooldown_seconds=60, profile_id='digiseller')


def test_parser_state_fields_are_persisted(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    now = datetime.now()
    storage.update_state(
        profile_id='ggsel',
        last_competitor_url='https://example.com',
        last_competitor_parse_at=now,
        last_competitor_method='stealth_requests',
        last_competitor_error='blocked',
        last_competitor_block_reason='captcha',
        last_competitor_status_code=403,
    )
    state = storage.get_state(profile_id='ggsel')

    assert state['last_competitor_url'] == 'https://example.com'
    assert state['last_competitor_method'] == 'stealth_requests'
    assert state['last_competitor_error'] == 'blocked'
    assert state['last_competitor_block_reason'] == 'captcha'
    assert state['last_competitor_status_code'] == 403
    assert state['last_competitor_parse_at'] is not None


def test_target_state_fields_are_persisted(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.update_state(
        profile_id='ggsel',
        last_target_price=0.2649,
        last_target_competitor_min=0.27,
    )
    state = storage.get_state(profile_id='ggsel')

    assert state['last_target_price'] == 0.2649
    assert state['last_target_competitor_min'] == 0.27


def test_target_state_backfilled_from_existing_values(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.update_state(
        profile_id='ggsel',
        last_price=0.2649,
        last_competitor_min=0.27,
        last_target_price=None,
        last_target_competitor_min=None,
    )

    # Переинициализация должна выполнить backfill target-полей.
    storage_reloaded = Storage(db_path=str(db))
    state = storage_reloaded.get_state(profile_id='ggsel')

    assert state['last_target_price'] == 0.2649
    assert state['last_target_competitor_min'] == 0.27


def test_update_state_normalizes_price_fields_to_4dp(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.update_state(
        profile_id='ggsel',
        last_price=0.26491,
        last_target_price='0.26494',
        last_target_competitor_min='0.27006',
        last_competitor_min=0.27008,
    )
    state = storage.get_state(profile_id='ggsel')

    assert state['last_price'] == 0.2649
    assert state['last_target_price'] == 0.2649
    assert state['last_target_competitor_min'] == 0.2701
    assert state['last_competitor_min'] == 0.2701


def test_runtime_price_settings_are_normalized_to_4dp(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    storage.set_runtime_setting(
        'UNDERCUT_VALUE',
        '0.00514',
        profile_id='ggsel',
    )

    raw = storage.get_runtime_setting('UNDERCUT_VALUE', profile_id='ggsel')
    runtime = storage.get_runtime_config(type('Cfg', (), {
        'MIN_PRICE': 0.1,
        'MAX_PRICE': 10.0,
        'DESIRED_PRICE': 1.0,
        'UNDERCUT_VALUE': 0.0051,
        'MODE': 'FIXED',
        'FIXED_PRICE': 1.0,
        'STEP_UP_VALUE': 0.01,
        'WEAK_PRICE_CEIL_LIMIT': 0.3,
        'POSITION_FILTER_ENABLED': False,
        'WEAK_POSITION_THRESHOLD': 20,
        'COOLDOWN_SECONDS': 10,
        'IGNORE_DELTA': 0.001,
        'CHECK_INTERVAL': 60,
        'FAST_CHECK_INTERVAL_MIN': 20,
        'FAST_CHECK_INTERVAL_MAX': 60,
        'COMPETITOR_COOKIES': '',
        'NOTIFY_SKIP': False,
        'NOTIFY_SKIP_COOLDOWN_SECONDS': 300,
        'NOTIFY_COMPETITOR_CHANGE': True,
        'COMPETITOR_CHANGE_DELTA': 0.0001,
        'COMPETITOR_CHANGE_COOLDOWN_SECONDS': 60,
        'UPDATE_ONLY_ON_COMPETITOR_CHANGE': True,
        'NOTIFY_PARSER_ISSUES': True,
        'PARSER_ISSUE_COOLDOWN_SECONDS': 300,
        'HARD_FLOOR_ENABLED': True,
        'MAX_DOWN_STEP': 0.05,
        'FAST_REBOUND_DELTA': 0.01,
        'FAST_REBOUND_BYPASS_COOLDOWN': True,
        'COMPETITOR_URLS': [],
    }), profile_id='ggsel', default_urls=[])

    assert raw == '0.0051'
    assert runtime.UNDERCUT_VALUE == 0.0051


def test_runtime_config_keeps_empty_profile_default_urls(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    cfg = type('Cfg', (), {
        'MIN_PRICE': 0.1,
        'MAX_PRICE': 10.0,
        'DESIRED_PRICE': 1.0,
        'UNDERCUT_VALUE': 0.0051,
        'MODE': 'FIXED',
        'FIXED_PRICE': 1.0,
        'STEP_UP_VALUE': 0.01,
        'WEAK_PRICE_CEIL_LIMIT': 0.3,
        'POSITION_FILTER_ENABLED': False,
        'WEAK_POSITION_THRESHOLD': 20,
        'COOLDOWN_SECONDS': 10,
        'IGNORE_DELTA': 0.001,
        'CHECK_INTERVAL': 60,
        'FAST_CHECK_INTERVAL_MIN': 20,
        'FAST_CHECK_INTERVAL_MAX': 60,
        'COMPETITOR_COOKIES': '',
        'NOTIFY_SKIP': False,
        'NOTIFY_SKIP_COOLDOWN_SECONDS': 300,
        'NOTIFY_COMPETITOR_CHANGE': True,
        'COMPETITOR_CHANGE_DELTA': 0.0001,
        'COMPETITOR_CHANGE_COOLDOWN_SECONDS': 60,
        'UPDATE_ONLY_ON_COMPETITOR_CHANGE': True,
        'NOTIFY_PARSER_ISSUES': True,
        'PARSER_ISSUE_COOLDOWN_SECONDS': 300,
        'HARD_FLOOR_ENABLED': True,
        'MAX_DOWN_STEP': 0.05,
        'FAST_REBOUND_DELTA': 0.01,
        'FAST_REBOUND_BYPASS_COOLDOWN': True,
        'COMPETITOR_URLS': ['https://global.example/item'],
    })

    runtime = storage.get_runtime_config(
        cfg,
        profile_id='digiseller',
        default_urls=[],
    )

    assert runtime.COMPETITOR_URLS == []


def test_runtime_price_settings_backfilled_to_4dp_on_reload(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.set_runtime_setting('DESIRED_PRICE', '0.35', profile_id='ggsel')

    reloaded = Storage(db_path=str(db))
    raw = reloaded.get_runtime_setting('DESIRED_PRICE', profile_id='ggsel')

    assert raw == '0.3500'


def test_migrates_legacy_runtime_settings_without_profile_id(tmp_path):
    db = tmp_path / 'legacy_runtime.db'
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            '''
            CREATE TABLE runtime_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            '''
        )
        conn.execute(
            "INSERT INTO runtime_settings (key, value) VALUES (?, ?)",
            ('CHECK_INTERVAL', '30'),
        )
        conn.commit()

    storage = Storage(db_path=str(db))

    value = storage.get_runtime_setting('CHECK_INTERVAL', profile_id='ggsel')
    assert value == '30'


def test_migrates_legacy_history_and_alert_tables(tmp_path):
    db = tmp_path / 'legacy_misc.db'
    recent = datetime.now() - timedelta(minutes=10)
    recent_str = recent.strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            '''
            CREATE TABLE settings_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                user_id INTEGER,
                source TEXT,
                timestamp TIMESTAMP
            )
            '''
        )
        conn.execute(
            '''
            INSERT INTO settings_history (
                key, old_value, new_value, user_id, source, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                'MODE',
                'FIXED',
                'STEP_UP',
                1,
                'test',
                recent_str,
            ),
        )
        conn.execute(
            '''
            CREATE TABLE alert_state (
                key TEXT PRIMARY KEY,
                last_sent TIMESTAMP
            )
            '''
        )
        conn.execute(
            "INSERT INTO alert_state (key, last_sent) VALUES (?, ?)",
            ('x', recent_str),
        )
        conn.commit()

    storage = Storage(db_path=str(db))

    rows = storage.get_settings_history(limit=10, profile_id='ggsel')
    assert rows
    assert rows[0]['key'] == 'MODE'
    # После миграции legacy алерт должен блокировать повторную отправку.
    assert storage.should_send_alert('x', cooldown_seconds=3600, profile_id='ggsel') is False


def test_migrates_legacy_price_history_without_profile_id(tmp_path):
    db = tmp_path / 'legacy_price_history.db'
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            '''
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                old_price REAL,
                new_price REAL,
                competitor_price REAL,
                reason TEXT,
                timestamp TIMESTAMP
            )
            '''
        )
        conn.execute(
            '''
            INSERT INTO price_history (
                old_price, new_price, competitor_price, reason, timestamp
            )
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                0.26,
                0.2649,
                0.27,
                'base_formula',
                '2026-04-03 12:00:00',
            ),
        )
        conn.commit()

    Storage(db_path=str(db))
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            '''
            SELECT profile_id, old_price, new_price
            FROM price_history
            ORDER BY id DESC
            LIMIT 1
            '''
        ).fetchone()

    assert row is not None
    assert row[0] == 'ggsel'
    assert row[1] == 0.26
    assert row[2] == 0.2649
