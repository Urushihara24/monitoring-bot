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
    assert decision.reason.startswith('dumping_showcase')


def test_hard_floor_min_for_legacy_fixed_mode():
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
    assert decision.price == 0.25
    assert 'hard_floor_min' in decision.reason


def test_hard_floor_min_for_legacy_step_up_mode():
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
    assert decision.price == 0.25
    assert 'hard_floor_min' in decision.reason


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
    assert decision.reason.startswith('dumping_showcase')


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


def test_follow_sets_same_price_as_competitor_with_4dp():
    cfg = make_cfg(MODE='FOLLOW', MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.3560],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.3560
    assert decision.reason.startswith('follow')


def test_follow_ignores_min_max_caps():
    cfg = make_cfg(
        MODE='FOLLOW',
        MIN_PRICE=0.25,
        MAX_PRICE=0.40,
        MAX_DOWN_STEP=0.0,
        HARD_FLOOR_ENABLED=True,
    )
    decision_high = calculate_price(
        competitor_prices=[1.2345],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision_high.action == 'update'
    assert decision_high.price == 1.2345
    assert 'max_capped' not in decision_high.reason

    decision_low = calculate_price(
        competitor_prices=[0.1234],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision_low.action == 'update'
    assert decision_low.price == 0.1234
    assert 'hard_floor_min' not in decision_low.reason


def test_raise_uses_showcase_rounding_then_plus_value():
    cfg = make_cfg(MODE='RAISE', MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.3505],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.3549
    assert decision.reason.startswith('raise_showcase')


def test_dumping_uses_showcase_rounding_then_minus_value():
    cfg = make_cfg(MODE='DUMPING', MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.3505],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.3449
    assert decision.reason.startswith('dumping_showcase')


def test_dumping_ignores_min_max_caps_for_modern_mode():
    cfg = make_cfg(
        MODE='DUMPING',
        MIN_PRICE=0.25,
        MAX_PRICE=0.40,
        MAX_DOWN_STEP=0.03,
        HARD_FLOOR_ENABLED=True,
    )
    decision_high = calculate_price(
        competitor_prices=[1.205],
        current_price=1.0,
        last_update=None,
        config=cfg,
    )
    assert decision_high.action == 'update'
    assert decision_high.price == 1.2049
    assert 'max_capped' not in decision_high.reason

    decision_low = calculate_price(
        competitor_prices=[0.10],
        current_price=0.30,
        last_update=None,
        config=cfg,
    )
    assert decision_low.action == 'update'
    assert decision_low.price == 0.0949
    assert 'hard_floor_min' not in decision_low.reason


def test_raise_on_showcase_036_range():
    cfg = make_cfg(MODE='RAISE', MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[0.3599],
        current_price=0.31,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 0.3649


def test_raise_ignores_max_cap_for_modern_mode():
    cfg = make_cfg(MODE='RAISE', MAX_PRICE=0.40, MAX_DOWN_STEP=0.0)
    decision = calculate_price(
        competitor_prices=[1.2005],
        current_price=1.0,
        last_update=None,
        config=cfg,
    )
    assert decision.action == 'update'
    assert decision.price == 1.2049
    assert 'max_capped' not in decision.reason


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
