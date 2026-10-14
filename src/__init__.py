"""Auto-Pricing Bot for GGSEL and DigiSeller.

Package exports are intentionally lazy. ``python -m src`` must be able to run
startup preflight before importing configuration, network clients, Telegram or
scheduler modules. A dependency-light log redaction layer is installed early so
helper scripts and application modules cannot emit known credentials verbatim.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .log_safety import install_log_redaction

install_log_redaction()

_EXPORTS: dict[str, tuple[str, str]] = {
    'config': ('.config', 'config'),
    'storage': ('.storage', 'storage'),
    'rsc_parser': ('.rsc_parser', 'rsc_parser'),
    'RSCParser': ('.rsc_parser', 'RSCParser'),
    'GGSELClient': ('.api_client', 'GGSELClient'),
    'calculate_price': ('.logic', 'calculate_price'),
    'PriceDecision': ('.logic', 'PriceDecision'),
    'TelegramBot': ('.telegram_bot', 'TelegramBot'),
    'Scheduler': ('.scheduler', 'Scheduler'),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Resolve legacy top-level exports only when callers request them."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
