"""
Профильные runtime-дефолты из config/.env.
"""

from __future__ import annotations

import os
from typing import Dict


_DIGISELLER_RUNTIME_TYPES = {
    'MIN_PRICE': 'float',
    'MAX_PRICE': 'float',
    'DESIRED_PRICE': 'float',
    'UNDERCUT_VALUE': 'float',
    'RAISE_VALUE': 'float',
    'SHOWCASE_ROUND_STEP': 'float',
    'REBOUND_TO_DESIRED_ON_MIN': 'bool',
    'MODE': 'mode',
    'FIXED_PRICE': 'float',
    'STEP_UP_VALUE': 'float',
    'WEAK_PRICE_CEIL_LIMIT': 'float',
    'POSITION_FILTER_ENABLED': 'bool',
    'WEAK_POSITION_THRESHOLD': 'int',
    'WEAK_UNKNOWN_RANK_ENABLED': 'bool',
    'WEAK_UNKNOWN_RANK_ABS_GAP': 'float',
    'WEAK_UNKNOWN_RANK_REL_GAP': 'float',
    'COOLDOWN_SECONDS': 'int',
    'IGNORE_DELTA': 'float',
    'CHECK_INTERVAL': 'int',
    'FAST_CHECK_INTERVAL_MIN': 'int',
    'FAST_CHECK_INTERVAL_MAX': 'int',
    'NOTIFY_SKIP': 'bool',
    'NOTIFY_SKIP_COOLDOWN_SECONDS': 'int',
    'NOTIFY_COMPETITOR_CHANGE': 'bool',
    'COMPETITOR_CHANGE_DELTA': 'float',
    'COMPETITOR_CHANGE_COOLDOWN_SECONDS': 'int',
    'UPDATE_ONLY_ON_COMPETITOR_CHANGE': 'bool',
    'NOTIFY_PARSER_ISSUES': 'bool',
    'PARSER_ISSUE_COOLDOWN_SECONDS': 'int',
    'HARD_FLOOR_ENABLED': 'bool',
    'MAX_DOWN_STEP': 'float',
    'FAST_REBOUND_DELTA': 'float',
    'FAST_REBOUND_BYPASS_COOLDOWN': 'bool',
}


def _coerce_raw_value(raw: str, value_type: str):
    normalized = (raw or '').strip()
    if not normalized:
        return None
    try:
        if value_type == 'bool':
            return normalized.lower() in {'1', 'true', 'yes', 'on'}
        if value_type == 'int':
            return int(float(normalized))
        if value_type == 'float':
            return float(normalized)
        if value_type == 'mode':
            mode = normalized.upper()
            aliases = {
                'FIX': 'DUMPING',
                'FIXED': 'DUMPING',
                'STEP': 'DUMPING',
                'STEP_UP': 'DUMPING',
                'FOLLOW': 'FOLLOW',
                'FOLLOW_EXACT': 'FOLLOW',
                'FOLLOW_MINUS': 'RAISE',
                'FOLLOW_ADD': 'RAISE',
                'FOLLOW_PLUS': 'RAISE',
                'RAISE': 'RAISE',
                'ФИКС': 'DUMPING',
                'ШАГ': 'DUMPING',
                'СЛЕДОВАНИЕ': 'FOLLOW',
                'СЛЕДОВАТЬ': 'FOLLOW',
                'ПОВЫШЕНИЕ': 'RAISE',
            }
            return aliases.get(mode, mode)
        return normalized
    except ValueError:
        return None


def _read_profile_default(cfg, env_name: str, value_type: str):
    value = getattr(cfg, env_name, None)
    if value is None:
        raw = os.getenv(env_name)
        if raw is None:
            return None
        return _coerce_raw_value(raw, value_type)
    if value_type == 'mode':
        return _coerce_raw_value(str(value), value_type)
    return value


def _format_runtime_value(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def build_profile_runtime_defaults(cfg, profile_id: str) -> Dict[str, str]:
    """
    Возвращает профильные runtime-дефолты в виде строки key->value.
    Сейчас профильные override поддерживаются для DigiSeller.
    """
    profile = (profile_id or '').strip().lower()
    if profile != 'digiseller':
        return {}

    defaults: Dict[str, str] = {}
    for key, value_type in _DIGISELLER_RUNTIME_TYPES.items():
        env_name = f'DIGISELLER_{key}'
        value = _read_profile_default(cfg, env_name, value_type)
        if value is None:
            continue
        defaults[key] = _format_runtime_value(value)
    return defaults


def seed_profile_runtime_defaults(
    storage_obj,
    profile_id: str,
    defaults: Dict[str, str],
    *,
    source: str = 'env_profile_default',
) -> Dict[str, str]:
    """
    Записывает defaults только для отсутствующих runtime-ключей.
    Возвращает ключи, которые реально были засеяны.
    """
    seeded: Dict[str, str] = {}
    profile = (profile_id or '').strip().lower()
    for key, value in defaults.items():
        existing = storage_obj.get_runtime_setting(key, profile_id=profile)
        if existing is not None:
            continue
        storage_obj.set_runtime_setting(
            key,
            value,
            source=source,
            profile_id=profile,
        )
        seeded[key] = value
    return seeded
