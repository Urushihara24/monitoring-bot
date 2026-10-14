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


def _bootstrap() -> None:
    try:
        validate_startup_environment()
    except ValueError as exc:
        print(f'Configuration error:\n{exc}', file=sys.stderr)
        raise SystemExit(2) from exc

    _print_write_safety_banner()

    # Import only after preflight so invalid .env values do not fail inside
    # src.config with an opaque import-time ValueError.
    from .main import run

    run()


if __name__ == '__main__':
    _bootstrap()
