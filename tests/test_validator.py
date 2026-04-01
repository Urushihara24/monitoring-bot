"""
Тесты validator.py
"""

from types import SimpleNamespace

from src.validator import validate_runtime_config


def _cfg(**kwargs):
    base = {
        'MIN_PRICE': 0.25,
        'MAX_PRICE': 10.0,
        'DESIRED_PRICE': 0.35,
        'UNDERCUT_VALUE': 0.0051,
        'MODE': 'FIXED',
        'FIXED_PRICE': 0.35,
        'STEP_UP_VALUE': 0.05,
        'LOW_PRICE_THRESHOLD': 0.0,
        'WEAK_PRICE_CEIL_LIMIT': 0.3,
        'POSITION_FILTER_ENABLED': False,
        'WEAK_POSITION_THRESHOLD': 20,
        'COOLDOWN_SECONDS': 30,
        'IGNORE_DELTA': 0.001,
        'CHECK_INTERVAL': 30,
        'NOTIFY_SKIP': False,
        'NOTIFY_SKIP_COOLDOWN_SECONDS': 300,
        'NOTIFY_COMPETITOR_CHANGE': True,
        'COMPETITOR_CHANGE_DELTA': 0.0001,
        'COMPETITOR_CHANGE_COOLDOWN_SECONDS': 60,
        'COMPETITOR_URLS': ['https://example.com'],
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_validate_runtime_config_ok():
    ok, errors = validate_runtime_config(_cfg())
    assert ok is True
    assert errors == []


def test_validate_runtime_config_invalid_mode():
    ok, errors = validate_runtime_config(_cfg(MODE='BAD'))
    assert ok is False
    assert any('MODE' in e for e in errors)


def test_validate_runtime_config_min_max():
    ok, errors = validate_runtime_config(_cfg(MIN_PRICE=2, MAX_PRICE=1))
    assert ok is False
    assert any('MIN_PRICE' in e for e in errors)
