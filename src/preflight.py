"""Startup preflight checks that run before importing the full application."""

from __future__ import annotations

import os
from collections.abc import MutableMapping

from dotenv import load_dotenv

from .config_env import normalize_typed_environment


ID_ENV_KEYS = (
    'GGSEL_SELLER_ID',
    'GGSEL_PRODUCT_ID',
    'DIGISELLER_SELLER_ID',
    'DIGISELLER_PRODUCT_ID',
)


def normalize_id_environment(
    env: MutableMapping[str, str],
) -> list[str]:
    """Backward-compatible ID preflight wrapper.

    Missing/blank seller and product IDs are normalized to ``0`` before the
    typed environment schema validates them.
    """
    for key in ID_ENV_KEYS:
        raw_value = env.get(key)
        if raw_value is None or not str(raw_value).strip():
            env[key] = '0'

    errors = normalize_typed_environment(env)
    return [error for error in errors if any(key in error for key in ID_ENV_KEYS)]


def normalize_boolean_environment(
    env: MutableMapping[str, str],
) -> list[str]:
    """Backward-compatible safety-boolean wrapper for existing callers/tests."""
    errors = normalize_typed_environment(env)
    return [error for error in errors if error.startswith('DRY_RUN ')]


def validate_startup_environment() -> None:
    """Load .env, validate typed values and fail before application imports."""
    load_dotenv()

    # Optional IDs intentionally default to 0, but every explicitly configured
    # typed value is validated by the shared schema below.
    for key in ID_ENV_KEYS:
        raw_value = os.environ.get(key)
        if raw_value is None or not raw_value.strip():
            os.environ[key] = '0'

    errors = normalize_typed_environment(os.environ)
    if errors:
        details = '\n'.join(f'- {error}' for error in errors)
        raise ValueError(f'Invalid startup configuration:\n{details}')
