"""
Тесты для storage.py
"""

from src.storage import Storage
from src.config import Config


def test_default_auto_mode_true(tmp_path):
    db_path = tmp_path / 'state.db'
    storage = Storage(str(db_path))
    state = storage.get_state()
    assert state['auto_mode'] is True


def test_auto_mode_persistence(tmp_path):
    db_path = tmp_path / 'state.db'
    storage = Storage(str(db_path))
    storage.update_state(auto_mode=False)
    state = storage.get_state()
    assert state['auto_mode'] is False


def test_runtime_competitor_urls(tmp_path):
    db_path = tmp_path / 'state.db'
    storage = Storage(str(db_path))
    storage.set_competitor_urls(['https://a', 'https://b'])
    urls = storage.get_competitor_urls([])
    assert urls == ['https://a', 'https://b']


def test_runtime_config_override(tmp_path):
    db_path = tmp_path / 'state.db'
    storage = Storage(str(db_path))
    base = Config()
    storage.set_runtime_setting('MIN_PRICE', '0.42')
    storage.set_runtime_setting('MODE', 'STEP_UP')
    storage.set_runtime_setting('POSITION_FILTER_ENABLED', 'true')
    runtime = storage.get_runtime_config(base)
    assert runtime.MIN_PRICE == 0.42
    assert runtime.MODE == 'STEP_UP'
    assert runtime.POSITION_FILTER_ENABLED is True


def test_settings_history_written(tmp_path):
    db_path = tmp_path / 'state.db'
    storage = Storage(str(db_path))
    storage.set_runtime_setting('MIN_PRICE', '0.50', user_id=123, source='telegram')
    history = storage.get_settings_history(limit=1)
    assert len(history) == 1
    row = history[0]
    assert row['key'] == 'MIN_PRICE'
    assert row['new_value'] == '0.50'
    assert row['user_id'] == 123
    assert row['source'] == 'telegram'


def test_alert_throttling(tmp_path):
    db_path = tmp_path / 'state.db'
    storage = Storage(str(db_path))
    assert storage.should_send_alert('test_key', cooldown_seconds=60) is True
    assert storage.should_send_alert('test_key', cooldown_seconds=60) is False
