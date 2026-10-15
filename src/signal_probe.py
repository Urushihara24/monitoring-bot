"""Credential-free process used by container lifecycle verification.

The probe exercises the same signal-registration and shutdown primitives as
``src.main`` without starting Telegram, marketplace clients or schedulers.
It exists only for CI/runtime lifecycle verification and performs no external
network calls or marketplace writes.
"""

from __future__ import annotations

import asyncio
import logging

from . import main as app_main

logger = logging.getLogger(__name__)


async def probe() -> None:
    """Wait for SIGTERM/SIGINT and verify the real application shutdown path."""
    app_main.shutdown_event = asyncio.Event()
    app_main.api_clients.clear()
    app_main.schedulers.clear()
    app_main.scheduler_manager = None
    app_main.telegram_bot = None

    app_main.setup_signal_handlers()
    logger.info('SIGTERM_PROBE_READY')
    print('SIGTERM_PROBE_READY', flush=True)

    await app_main.shutdown_event.wait()
    # ``setup_signal_handlers`` schedules ``app_main.shutdown``. Yield once so
    # its final logging can complete before the probe process exits.
    await asyncio.sleep(0)
    logger.info('SIGTERM_PROBE_STOPPED')
    print('SIGTERM_PROBE_STOPPED', flush=True)


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    asyncio.run(probe())


if __name__ == '__main__':
    run()
