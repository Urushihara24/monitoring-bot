"""Startup preflight checks that run before importing the full application."""

from __future__ import annotations

import os
from collections.abc import MutableMapping

from dotenv import load_dotenv


ID_ENV_KEYS = (
    'GGSEL_SELLER_ID',
    'GGSEL_PRODUCT_ID',
    'DIGISELLER_SELLER_ID',
    'DIGISELLER_PRODUCT_ID',
)

_BOOLEAN_ENV_KEYS = ('DRY_RUN',)
_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


def normalize_id_environment(
    env: MutableMapping[str, str],
) -> list[str]:
    """Normalize optional IDs and return human-readable validation errors.

    Empty seller/product IDs are safe defaults and become ``0``. Non-integer or
    negative values are rejected before ``src.config`` evaluates ``int(...)``
    at import time.
    """
    errors: list[str] = []

    for key in ID_ENV_KEYS:
        raw_value = env.get(key)
        if raw_value is None or not str(raw_value).strip():
            env[key] = '0'
            continue

        normalized = str(raw_value).strip()
        try:
            parsed = int(normalized)
        except ValueError:
            errors.append(f'{key} must be an integer, got {raw_value!r}')
            continue

        if parsed < 0:
            errors.append(f'{key} must be >= 0, got {parsed}')
            continue

        env[key] = str(parsed)

    return errors


def normalize_boolean_environment(
    env: MutableMapping[str, str],
) -> list[str]:
    """Validate safety-sensitive booleans and canonicalize their values."""
    errors: list[str] = []
    for key in _BOOLEAN_ENV_KEYS:
        raw_value = env.get(key)
        if raw_value is None or not str(raw_value).strip():
            continue
        normalized = str(raw_value).strip().lower()
        if normalized in _TRUE_VALUES:
            env[key] = 'true'
            continue
        if normalized in _FALSE_VALUES:
            env[key] = 'false'
            continue
        errors.append(
            f'{key} must be one of true/false, 1/0, yes/no, on/off; '
            f'got {raw_value!r}'
        )
    return errors


def validate_startup_environment() -> None:
    """Load .env and fail with a concise error before application imports."""
    load_dotenv()
    errors = normalize_id_environment(os.environ)
    errors.extend(normalize_boolean_environment(os.environ))
    if errors:
        details = '\n'.join(f'- {error}' for error in errors)
        raise ValueError(f'Invalid startup configuration:\n{details}')
