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
