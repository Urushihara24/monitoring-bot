"""Entry point for ``python -m src``."""

from __future__ import annotations

import sys

from .preflight import validate_startup_environment
from .write_safety import dry_run_enabled


def _print_write_safety_banner() -> None:
    if dry_run_enabled():
        print(
            'Startup safety: DRY_RUN=true — marketplace writes are blocked.',
            file=sys.stderr,
        )
        return
    print(
        'Startup safety: WRITES ARMED — DRY_RUN is false or unset.',
        file=sys.stderr,
    )


def _install_runtime_overrides(app_main):
    """Install staged modular runtime facades after startup preflight."""
    from .modular_telegram_bot import ModularTelegramBot

    app_main.TelegramBot = ModularTelegramBot
    return app_main


def _bootstrap() -> None:
    try:
        validate_startup_environment()
    except ValueError as exc:
        print(f'Configuration error:\n{exc}', file=sys.stderr)
        raise SystemExit(2) from exc

    _print_write_safety_banner()

    # Import only after preflight so invalid .env values do not fail inside
    # src.config with an opaque import-time ValueError.
    from . import main as app_main

    _install_runtime_overrides(app_main).run()


if __name__ == '__main__':
    _bootstrap()
