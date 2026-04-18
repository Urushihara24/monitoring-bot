"""
Единая нормализация режимов ценообразования.
"""

from __future__ import annotations

from typing import Iterable

MODE_SEQUENCE = ('FOLLOW', 'DUMPING', 'RAISE', 'SHOWCASE_CYCLE')
MODE_SET = set(MODE_SEQUENCE)

MODE_LABELS_RU = {
    'FOLLOW': 'Следование',
    'DUMPING': 'Демпинг',
    'RAISE': 'Повышение',
    'SHOWCASE_CYCLE': 'Витринный цикл GGSEL',
}

MODE_ALIASES = {
    'FOLLOW_EXACT': 'FOLLOW',
    'FOLLOW_PLUS': 'RAISE',
    'FOLLOW_MINUS': 'RAISE',
    'FOLLOW_ADD': 'RAISE',
    'FIX': 'DUMPING',
    'FIXED': 'DUMPING',
    'STEP': 'DUMPING',
    'STEP_UP': 'DUMPING',
    'СЛЕДОВАНИЕ': 'FOLLOW',
    'СЛЕДОВАТЬ': 'FOLLOW',
    'ДЕМПИНГ': 'DUMPING',
    'ПОВЫШЕНИЕ': 'RAISE',
    'ВИТРИННЫЙ ЦИКЛ': 'SHOWCASE_CYCLE',
    'ВИТРИНА': 'SHOWCASE_CYCLE',
    'SHOWCASE': 'SHOWCASE_CYCLE',
    'SHOWCASE_CYCLE': 'SHOWCASE_CYCLE',
    'ФИКС': 'DUMPING',
    'ШАГ': 'DUMPING',
}


def normalize_pricing_mode(
    mode: object,
    *,
    fallback: str = 'DUMPING',
    allowed: Iterable[str] = MODE_SEQUENCE,
) -> str:
    normalized = str(mode or '').strip().upper()
    normalized = MODE_ALIASES.get(normalized, normalized)
    allowed_set = set(allowed)
    return normalized if normalized in allowed_set else fallback


def next_pricing_mode(mode: object) -> str:
    current = normalize_pricing_mode(mode)
    idx = MODE_SEQUENCE.index(current)
    return MODE_SEQUENCE[(idx + 1) % len(MODE_SEQUENCE)]


def pricing_mode_label(mode: object) -> str:
    normalized = normalize_pricing_mode(mode)
    return MODE_LABELS_RU.get(normalized, normalized)
