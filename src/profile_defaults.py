"""
Профильные runtime-дефолты из config/.env.
"""

from __future__ import annotations

from typing import Dict


def build_profile_runtime_defaults(cfg, profile_id: str) -> Dict[str, str]:
    """
    Возвращает профильные runtime-дефолты в виде строки key->value.
    Сейчас профильные override поддерживаются для DigiSeller.
    """
    profile = (profile_id or '').strip().lower()
    if profile != 'digiseller':
        return {}

    defaults: Dict[str, str] = {}
    mapping = {
        'MIN_PRICE': cfg.DIGISELLER_MIN_PRICE,
        'MAX_PRICE': cfg.DIGISELLER_MAX_PRICE,
        'DESIRED_PRICE': cfg.DIGISELLER_DESIRED_PRICE,
        'UNDERCUT_VALUE': cfg.DIGISELLER_UNDERCUT_VALUE,
        'MODE': cfg.DIGISELLER_MODE,
        'FIXED_PRICE': cfg.DIGISELLER_FIXED_PRICE,
        'STEP_UP_VALUE': cfg.DIGISELLER_STEP_UP_VALUE,
        'CHECK_INTERVAL': cfg.DIGISELLER_CHECK_INTERVAL,
        'COOLDOWN_SECONDS': cfg.DIGISELLER_COOLDOWN_SECONDS,
    }
    for key, value in mapping.items():
        if value is None:
            continue
        if key == 'MODE':
            defaults[key] = str(value).strip().upper()
        else:
            defaults[key] = str(value)
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
