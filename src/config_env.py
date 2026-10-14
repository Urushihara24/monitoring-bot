"""Typed, fail-closed environment normalization for startup configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, MutableMapping

from .pricing_mode import MODE_ALIASES, MODE_SET

EnvKind = Literal['bool', 'int', 'float', 'csv_int', 'mode', 'choice']

_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


@dataclass(frozen=True)
class EnvRule:
    kind: EnvKind
    optional: bool = False
    minimum: Decimal | None = None
    choices: frozenset[str] | None = None


def _rules() -> dict[str, EnvRule]:
    bool_rule = EnvRule('bool')
    optional_bool = EnvRule('bool', optional=True)
    nonnegative_int = EnvRule('int', minimum=Decimal('0'))
    positive_int = EnvRule('int', minimum=Decimal('1'))
    optional_nonnegative_int = EnvRule(
        'int', optional=True, minimum=Decimal('0')
    )
    optional_positive_int = EnvRule(
        'int', optional=True, minimum=Decimal('1')
    )
    nonnegative_float = EnvRule('float', minimum=Decimal('0'))
    optional_nonnegative_float = EnvRule(
        'float', optional=True, minimum=Decimal('0')
    )

    rules: dict[str, EnvRule] = {
        'DRY_RUN': bool_rule,
        'GGSEL_SELLER_ID': nonnegative_int,
        'GGSEL_PRODUCT_ID': nonnegative_int,
        'DIGISELLER_SELLER_ID': nonnegative_int,
        'DIGISELLER_PRODUCT_ID': nonnegative_int,
        'TELEGRAM_ADMIN_IDS': EnvRule('csv_int', optional=True, minimum=Decimal('1')),
        'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS': EnvRule(
            'csv_int', optional=True, minimum=Decimal('1')
        ),
        'DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS': EnvRule(
            'csv_int', optional=True, minimum=Decimal('1')
        ),
        'MODE': EnvRule('mode'),
        'DIGISELLER_MODE': EnvRule('mode', optional=True),
        'GGSEL_CHAT_AUTOREPLY_POLICY': EnvRule(
            'choice',
            choices=frozenset({'ON_ORDER', 'FIRST_BUYER_MESSAGE', 'CODE_ONLY'}),
        ),
        'DIGISELLER_CHAT_AUTOREPLY_POLICY': EnvRule(
            'choice',
            choices=frozenset({'ON_ORDER', 'FIRST_BUYER_MESSAGE', 'CODE_ONLY'}),
        ),
        'LOG_LEVEL': EnvRule(
            'choice',
            choices=frozenset({'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'}),
        ),
    }

    for name in (
        'GGSEL_REQUIRE_API_ON_START',
        'GGSEL_ENABLED',
        'GGSEL_CHAT_AUTOREPLY_ENABLED',
        'GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES',
        'GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
        'GGSEL_CHAT_AUTOREPLY_SMART_NON_EMPTY',
        'GGSEL_CHAT_AUTOREPLY_REQUIRE_RULES',
        'GGSEL_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT',
        'GGSEL_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK',
        'GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK',
        'DIGISELLER_REQUIRE_API_ON_START',
        'DIGISELLER_ENABLED',
        'DIGISELLER_CHAT_AUTOREPLY_ENABLED',
        'DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES',
        'DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
        'DIGISELLER_CHAT_AUTOREPLY_SMART_NON_EMPTY',
        'DIGISELLER_CHAT_AUTOREPLY_REQUIRE_RULES',
        'DIGISELLER_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT',
        'DIGISELLER_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK',
        'DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK',
        'REBOUND_TO_DESIRED_ON_MIN',
        'POSITION_FILTER_ENABLED',
        'WEAK_UNKNOWN_RANK_ENABLED',
        'NOTIFY_SKIP',
        'NOTIFY_COMPETITOR_CHANGE',
        'UPDATE_ONLY_ON_COMPETITOR_CHANGE',
        'NOTIFY_PARSER_ISSUES',
        'NOTIFY_ERRORS',
        'HARD_FLOOR_ENABLED',
        'FAST_REBOUND_BYPASS_COOLDOWN',
    ):
        rules[name] = bool_rule

    for name in (
        'DIGISELLER_REBOUND_TO_DESIRED_ON_MIN',
        'DIGISELLER_POSITION_FILTER_ENABLED',
        'DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED',
        'DIGISELLER_NOTIFY_SKIP',
        'DIGISELLER_NOTIFY_COMPETITOR_CHANGE',
        'DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE',
        'DIGISELLER_NOTIFY_PARSER_ISSUES',
        'DIGISELLER_HARD_FLOOR_ENABLED',
        'DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN',
    ):
        rules[name] = optional_bool

    for name in (
        'GGSEL_CHAT_AUTOREPLY_PAGE_SIZE',
        'GGSEL_CHAT_AUTOREPLY_MAX_PAGES',
        'GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS',
        'GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES',
        'GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES',
        'GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS',
        'GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS',
        'DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE',
        'DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES',
        'DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS',
        'DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES',
        'DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES',
        'DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS',
        'DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS',
        'RSC_MAX_RETRIES',
        'WEAK_POSITION_THRESHOLD',
        'CHECK_INTERVAL',
        'FAST_CHECK_INTERVAL_MIN',
        'FAST_CHECK_INTERVAL_MAX',
        'LOG_MAX_BYTES',
    ):
        rules[name] = positive_int

    for name in (
        'COOLDOWN_SECONDS',
        'NOTIFY_SKIP_COOLDOWN_SECONDS',
        'COMPETITOR_CHANGE_COOLDOWN_SECONDS',
        'PARSER_ISSUE_COOLDOWN_SECONDS',
        'LOG_BACKUP_COUNT',
    ):
        rules[name] = nonnegative_int

    for name in (
        'DIGISELLER_WEAK_POSITION_THRESHOLD',
        'DIGISELLER_CHECK_INTERVAL',
        'DIGISELLER_FAST_CHECK_INTERVAL_MIN',
        'DIGISELLER_FAST_CHECK_INTERVAL_MAX',
    ):
        rules[name] = optional_positive_int

    for name in (
        'DIGISELLER_COOLDOWN_SECONDS',
        'DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS',
        'DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS',
        'DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS',
    ):
        rules[name] = optional_nonnegative_int

    for name in (
        'MIN_PRICE',
        'MAX_PRICE',
        'DESIRED_PRICE',
        'UNDERCUT_VALUE',
        'RAISE_VALUE',
        'SHOWCASE_ROUND_STEP',
        'FIXED_PRICE',
        'STEP_UP_VALUE',
        'WEAK_PRICE_CEIL_LIMIT',
        'WEAK_UNKNOWN_RANK_ABS_GAP',
        'WEAK_UNKNOWN_RANK_REL_GAP',
        'IGNORE_DELTA',
        'COMPETITOR_CHANGE_DELTA',
        'MAX_DOWN_STEP',
        'FAST_REBOUND_DELTA',
    ):
        rules[name] = nonnegative_float

    for name in (
        'DIGISELLER_MIN_PRICE',
        'DIGISELLER_MAX_PRICE',
        'DIGISELLER_DESIRED_PRICE',
        'DIGISELLER_UNDERCUT_VALUE',
        'DIGISELLER_RAISE_VALUE',
        'DIGISELLER_SHOWCASE_ROUND_STEP',
        'DIGISELLER_FIXED_PRICE',
        'DIGISELLER_STEP_UP_VALUE',
        'DIGISELLER_WEAK_PRICE_CEIL_LIMIT',
        'DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP',
        'DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP',
        'DIGISELLER_IGNORE_DELTA',
        'DIGISELLER_COMPETITOR_CHANGE_DELTA',
        'DIGISELLER_MAX_DOWN_STEP',
        'DIGISELLER_FAST_REBOUND_DELTA',
    ):
        rules[name] = optional_nonnegative_float

    return rules


ENV_RULES = _rules()


def _parse_decimal(name: str, raw: str) -> tuple[Decimal | None, str | None]:
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None, f'{name} must be numeric, got {raw!r}'
    if not value.is_finite() or not math.isfinite(float(value)):
        return None, f'{name} must be finite, got {raw!r}'
    return value, None


def _normalize_rule(
    name: str,
    raw: str,
    rule: EnvRule,
) -> tuple[str | None, str | None]:
    value = raw.strip()
    if not value:
        if rule.optional:
            return None, None
        return None, f'{name} must not be empty'

    if rule.kind == 'bool':
        normalized = value.lower()
        if normalized in _TRUE_VALUES:
            return 'true', None
        if normalized in _FALSE_VALUES:
            return 'false', None
        return None, (
            f'{name} must be one of true/false, 1/0, yes/no, on/off; '
            f'got {raw!r}'
        )

    if rule.kind == 'int':
        parsed, error = _parse_decimal(name, value)
        if error:
            return None, error
        assert parsed is not None
        if parsed != parsed.to_integral_value():
            return None, f'{name} must be an integer, got {raw!r}'
        if rule.minimum is not None and parsed < rule.minimum:
            return None, f'{name} must be >= {rule.minimum}, got {raw!r}'
        return str(int(parsed)), None

    if rule.kind == 'float':
        parsed, error = _parse_decimal(name, value)
        if error:
            return None, error
        assert parsed is not None
        if rule.minimum is not None and parsed < rule.minimum:
            return None, f'{name} must be >= {rule.minimum}, got {raw!r}'
        return value, None

    if rule.kind == 'csv_int':
        normalized_items: list[str] = []
        for item in value.split(','):
            chunk = item.strip()
            if not chunk:
                continue
            parsed, error = _parse_decimal(name, chunk)
            if error:
                return None, error
            assert parsed is not None
            if parsed != parsed.to_integral_value():
                return None, f'{name} entries must be integers, got {chunk!r}'
            if rule.minimum is not None and parsed < rule.minimum:
                return None, (
                    f'{name} entries must be >= {rule.minimum}, got {chunk!r}'
                )
            normalized_items.append(str(int(parsed)))
        return ','.join(normalized_items), None

    if rule.kind == 'mode':
        normalized = value.upper()
        normalized = MODE_ALIASES.get(normalized, normalized)
        if normalized not in MODE_SET:
            allowed = ', '.join(sorted(MODE_SET))
            return None, f'{name} must resolve to one of {allowed}; got {raw!r}'
        return normalized, None

    if rule.kind == 'choice':
        normalized = value.upper()
        choices = rule.choices or frozenset()
        if normalized not in choices:
            allowed = ', '.join(sorted(choices))
            return None, f'{name} must be one of {allowed}; got {raw!r}'
        return normalized, None

    return None, f'{name} has unsupported environment rule {rule.kind!r}'


def normalize_typed_environment(
    env: MutableMapping[str, str],
) -> list[str]:
    """Validate and canonicalize known typed environment values in place."""
    errors: list[str] = []

    for name, rule in ENV_RULES.items():
        raw = env.get(name)
        if raw is None:
            continue
        if not str(raw).strip() and rule.optional:
            continue

        normalized, error = _normalize_rule(name, str(raw), rule)
        if error:
            errors.append(error)
            continue
        if normalized is not None:
            env[name] = normalized

    return errors
