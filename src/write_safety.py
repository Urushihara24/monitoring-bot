"""Small, dependency-light helpers for marketplace write safety."""

from __future__ import annotations

import os
from collections.abc import Mapping

_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


def dry_run_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether external marketplace writes must be disabled.

    Missing ``DRY_RUN`` preserves historical behaviour for existing
    deployments. Invalid explicit values fail closed.
    """
    source = os.environ if env is None else env
    raw = source.get('DRY_RUN')
    if raw is None or not str(raw).strip():
        return False

    normalized = str(raw).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        'DRY_RUN must be one of: true/false, 1/0, yes/no, on/off'
    )
