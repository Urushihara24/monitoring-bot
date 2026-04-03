from datetime import datetime, timedelta
from types import SimpleNamespace

from src.logic import calculate_price


def make_cfg(**kwargs):
    cfg = {
        'MIN_PRICE': 0.25,
        'MAX_PRICE': 10.0,
        'DESIRED_PRICE': 0.35,
        'UNDERCUT_VALUE': 0.0051,
        'MODE': 'FIXED',
        'FIXED_PRICE': 0.35,
        'STEP_UP_VALUE': 0.05,
        'LOW_PRICE_THRESHOLD': 0.0,
        'WEAK_PRICE_CEIL_LIMIT': 0.3,
        'COOLDOWN_SECONDS': 30,
        'IGNORE_DELTA': 0.001,
        'HARD_FLOOR_ENABLED': True,
        'MAX_DOWN_STEP': 0.03,
    }
    cfg.update(kwargs)
    return SimpleNamespace(**cfg)


def test_base_formula_update():
    cfg = make_cfg(MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.34],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.3349
    assert decision.reason.startswith('base_formula')


def test_hard_floor_fixed_mode():
    cfg = make_cfg(
        MODE='FIXED',
        MIN_PRICE=0.25,
        FIXED_PRICE=0.35,
        MAX_DOWN_STEP=0.0,
    )
    decision = calculate_price(
        competitor_prices=[0.20],
        current_price=0.40,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.35
    assert 'hard_floor_fixed' in decision.reason


def test_hard_floor_step_up_mode():
    cfg = make_cfg(
        MODE='STEP_UP',
        MIN_PRICE=0.25,
        STEP_UP_VALUE=0.05,
        MAX_DOWN_STEP=0.0,
    )
    decision = calculate_price(
        competitor_prices=[0.20],
        current_price=0.30,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.35
    assert 'hard_floor_step_up' in decision.reason


def test_low_price_does_not_trigger_weak_mode_without_position_flag():
    cfg = make_cfg(
        LOW_PRICE_THRESHOLD=0.35,
        WEAK_PRICE_CEIL_LIMIT=0.3,
        MAX_DOWN_STEP=0.0,
    )
    decision = calculate_price(
        competitor_prices=[0.27],
        current_price=0.26,
        last_update=None,
        config=cfg,
        force_weak_mode=False,
    )
    assert decision.action == 'update'
    assert decision.price == 0.2649
    assert decision.reason.startswith('base_formula')


def test_max_down_step_caps_drop():
    cfg = make_cfg(MAX_DOWN_STEP=0.02, MODE='FIXED', FIXED_PRICE=0.25)
    decision = calculate_price(
        competitor_prices=[0.10],
        current_price=0.35,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.33
    assert 'max_down_step' in decision.reason


def test_cooldown_blocks_without_rebound():
    cfg = make_cfg(COOLDOWN_SECONDS=60, MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.34],
        current_price=0.30,
        last_update=datetime.now() - timedelta(seconds=10),
        config=cfg,
        allow_fast_rebound=False,
    )
    assert decision.action == 'skip'
    assert 'cooldown_active' in decision.reason


def test_fast_rebound_bypasses_cooldown_for_upward_change():
    cfg = make_cfg(COOLDOWN_SECONDS=60, MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.50],
        current_price=0.30,
        last_update=datetime.now() - timedelta(seconds=10),
        config=cfg,
        allow_fast_rebound=True,
    )
    assert decision.action == 'update'
    assert decision.price == 0.4949
    assert 'fast_rebound' in decision.reason


def test_ignore_delta_skip():
    cfg = make_cfg(IGNORE_DELTA=0.01, MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.34],
        current_price=0.334,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'skip'
    assert 'ignore_delta' in decision.reason
