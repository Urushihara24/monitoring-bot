"""
Валидация runtime-конфига
"""

from typing import List, Tuple


def validate_runtime_config(cfg) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if cfg.MIN_PRICE <= 0:
        errors.append('MIN_PRICE должен быть > 0')
    if cfg.MAX_PRICE <= 0:
        errors.append('MAX_PRICE должен быть > 0')
    if cfg.MIN_PRICE > cfg.MAX_PRICE:
        errors.append('MIN_PRICE не может быть больше MAX_PRICE')
    if cfg.UNDERCUT_VALUE <= 0:
        errors.append('UNDERCUT_VALUE должен быть > 0')
    if cfg.MODE not in ('FIXED', 'STEP_UP'):
        errors.append('MODE должен быть FIXED или STEP_UP')
    if cfg.CHECK_INTERVAL < 5:
        errors.append('CHECK_INTERVAL должен быть >= 5 секунд')
    if cfg.FAST_CHECK_INTERVAL_MIN < 5:
        errors.append('FAST_CHECK_INTERVAL_MIN должен быть >= 5 секунд')
    if cfg.FAST_CHECK_INTERVAL_MAX < cfg.FAST_CHECK_INTERVAL_MIN:
        errors.append(
            'FAST_CHECK_INTERVAL_MAX должен быть >= FAST_CHECK_INTERVAL_MIN'
        )
    if cfg.COOLDOWN_SECONDS < 0:
        errors.append('COOLDOWN_SECONDS не может быть отрицательным')
    if cfg.IGNORE_DELTA < 0:
        errors.append('IGNORE_DELTA не может быть отрицательным')
    if cfg.MAX_DOWN_STEP < 0:
        errors.append('MAX_DOWN_STEP не может быть отрицательным')
    if cfg.FAST_REBOUND_DELTA < 0:
        errors.append('FAST_REBOUND_DELTA не может быть отрицательным')
    if cfg.NOTIFY_SKIP_COOLDOWN_SECONDS < 0:
        errors.append('NOTIFY_SKIP_COOLDOWN_SECONDS не может быть отрицательным')
    if cfg.COMPETITOR_CHANGE_DELTA < 0:
        errors.append('COMPETITOR_CHANGE_DELTA не может быть отрицательным')
    if cfg.COMPETITOR_CHANGE_COOLDOWN_SECONDS < 0:
        errors.append('COMPETITOR_CHANGE_COOLDOWN_SECONDS не может быть отрицательным')
    if cfg.PARSER_ISSUE_COOLDOWN_SECONDS < 0:
        errors.append('PARSER_ISSUE_COOLDOWN_SECONDS не может быть отрицательным')
    if cfg.WEAK_POSITION_THRESHOLD < 1:
        errors.append('WEAK_POSITION_THRESHOLD должен быть >= 1')
    return len(errors) == 0, errors
