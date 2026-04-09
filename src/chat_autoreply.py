"""
Константы и хелперы для DigiSeller chat autoreply.
"""

from __future__ import annotations

import re

SENT_PREFIX = 'CHAT_AUTOREPLY_SENT:'
KEY_LAST_RUN_AT = 'CHAT_AUTOREPLY_LAST_RUN_AT'
KEY_LAST_SENT_AT = 'CHAT_AUTOREPLY_LAST_SENT_AT'
KEY_LAST_ERROR = 'CHAT_AUTOREPLY_LAST_ERROR'
KEY_SENT_COUNT = 'CHAT_AUTOREPLY_SENT_COUNT'
KEY_DUPLICATE_COUNT = 'CHAT_AUTOREPLY_DUPLICATE_COUNT'
KEY_LAST_CLEANUP_AT = 'CHAT_AUTOREPLY_LAST_CLEANUP_AT'
RULES_PREFIX = 'CHAT_AUTOREPLY_RULES:'
ID_RULE_PREFIX = 'id'


def sent_key(order_id: int) -> str:
    return f'{SENT_PREFIX}{int(order_id)}'


def rules_key(product_id: int) -> str:
    return f'{RULES_PREFIX}{int(product_id)}'


def normalize_rule_part(value: object) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text)
    return text


def option_rule_key(option_name: object, selected_value: object) -> str:
    option = normalize_rule_part(option_name)
    selected = normalize_rule_part(selected_value)
    return f'{option}::{selected}'


def parse_numeric_id(value: object) -> int:
    """Извлекает стабильный numeric-id из разных форматов."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float):
        try:
            as_int = int(value)
        except Exception:
            return 0
        return as_int if as_int > 0 else 0

    raw = str(value).strip()
    if not raw:
        return 0
    if raw.isdigit():
        parsed = int(raw)
        return parsed if parsed > 0 else 0

    # option_select_3066422 / variant:152937 / option-32496
    match = re.search(r'(?:[_:\-]|^)(\d+)$', raw)
    if not match:
        return 0
    try:
        parsed = int(match.group(1))
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def option_variant_rule_key(option_id: object, variant_id: object) -> str:
    option = parse_numeric_id(option_id)
    variant = parse_numeric_id(variant_id)
    if option <= 0 or variant <= 0:
        return ''
    return f'{ID_RULE_PREFIX}:{option}:{variant}'


def parse_option_variant_rule_key(rule_key: object) -> tuple[int, int] | None:
    raw = str(rule_key or '').strip().lower()
    match = re.fullmatch(rf'{ID_RULE_PREFIX}:(\d+):(\d+)', raw)
    if not match:
        return None
    try:
        option = int(match.group(1))
        variant = int(match.group(2))
    except Exception:
        return None
    if option <= 0 or variant <= 0:
        return None
    return (option, variant)


def is_option_variant_rule_key(rule_key: object) -> bool:
    return parse_option_variant_rule_key(rule_key) is not None
