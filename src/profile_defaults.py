"""Profile-scoped runtime defaults derived from the validated Config snapshot."""

from __future__ import annotations

from typing import Dict

from .pricing_mode import normalize_pricing_mode


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


def _read_profile_default(cfg, attribute: str, value_type: str):
    """Read an already-validated Config attribute without re-reading os.environ."""
    value = getattr(cfg, attribute, None)
    if value is None:
        return None
    if value_type == 'mode':
        return normalize_pricing_mode(str(value))
    return value


def _format_runtime_value(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def build_profile_runtime_defaults(cfg, profile_id: str) -> Dict[str, str]:
    """Return profile runtime defaults as string key/value pairs.

    Environment parsing belongs to ``src.config``.  This layer only projects the
    typed DigiSeller attributes into persisted runtime defaults.
    """
    profile = (profile_id or '').strip().lower()
    if profile != 'digiseller':
        return {}

    defaults: Dict[str, str] = {}
    for key, value_type in _DIGISELLER_RUNTIME_TYPES.items():
        attribute = f'DIGISELLER_{key}'
        value = _read_profile_default(cfg, attribute, value_type)
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
    """Persist defaults only for missing runtime keys and return seeded values."""
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
