from types import SimpleNamespace

from src.validator import validate_runtime_config


def make_cfg(**kwargs):
    cfg = {
        'MIN_PRICE': 0.25,
        'MAX_PRICE': 10.0,
        'UNDERCUT_VALUE': 0.0051,
        'MODE': 'FIXED',
        'FOLLOW_PLUS_VALUE': 0.0049,
        'CHECK_INTERVAL': 30,
        'FAST_CHECK_INTERVAL_MIN': 20,
        'FAST_CHECK_INTERVAL_MAX': 60,
        'COOLDOWN_SECONDS': 30,
        'IGNORE_DELTA': 0.001,
        'MAX_DOWN_STEP': 0.03,
        'FAST_REBOUND_DELTA': 0.01,
        'NOTIFY_SKIP_COOLDOWN_SECONDS': 300,
        'COMPETITOR_CHANGE_DELTA': 0.0001,
        'COMPETITOR_CHANGE_COOLDOWN_SECONDS': 60,
        'PARSER_ISSUE_COOLDOWN_SECONDS': 300,
        'WEAK_POSITION_THRESHOLD': 20,
        'COMPETITOR_URLS': ['https://example.com'],
    }
    cfg.update(kwargs)
    return SimpleNamespace(**cfg)


def test_validate_runtime_config_ok():
    ok, errors = validate_runtime_config(make_cfg())
    assert ok
    assert errors == []


def test_validate_runtime_config_bad_interval_range():
    ok, errors = validate_runtime_config(
        make_cfg(FAST_CHECK_INTERVAL_MIN=70, FAST_CHECK_INTERVAL_MAX=60)
    )
    assert not ok
    assert any('FAST_CHECK_INTERVAL_MAX' in e for e in errors)


def test_validate_runtime_config_bad_max_down_step():
    ok, errors = validate_runtime_config(make_cfg(MAX_DOWN_STEP=-1))
    assert not ok
    assert any('MAX_DOWN_STEP' in e for e in errors)


def test_validate_runtime_config_allows_empty_competitor_urls():
    ok, errors = validate_runtime_config(make_cfg(COMPETITOR_URLS=[]))
    assert ok
    assert errors == []


def test_validate_runtime_config_accepts_follow_modes():
    ok_exact, errors_exact = validate_runtime_config(make_cfg(MODE='FOLLOW_EXACT'))
    ok_plus, errors_plus = validate_runtime_config(make_cfg(MODE='FOLLOW_PLUS'))
    assert ok_exact and errors_exact == []
    assert ok_plus and errors_plus == []
