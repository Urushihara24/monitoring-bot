"""Entry point for ``python -m src``."""

from __future__ import annotations

import sys

from .preflight import validate_startup_environment


def _bootstrap() -> None:
    try:
        validate_startup_environment()
    except ValueError as exc:
        print(f'Configuration error:\n{exc}', file=sys.stderr)
        raise SystemExit(2) from exc

    # Import only after preflight so invalid .env values do not fail inside
    # src.config with an opaque import-time ValueError.
    from .main import run

    run()


if __name__ == '__main__':
    _bootstrap()
