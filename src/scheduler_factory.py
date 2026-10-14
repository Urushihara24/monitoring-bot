"""Scheduler construction with a fail-safe dry-run mode.

The production scheduler remains unchanged. When ``DRY_RUN=true`` a subclass
intercepts marketplace write boundaries while keeping the normal parsing and
pricing decision path intact.
"""

from __future__ import annotations

import logging
from typing import Any

from .scheduler import Scheduler as BaseScheduler
from .write_safety import dry_run_enabled

logger = logging.getLogger(__name__)


class DryRunScheduler(BaseScheduler):
    """Scheduler that executes decisions but blocks marketplace writes.

    Price updates are simulated only inside the current cycle so the parent
    scheduler can exercise its post-update verification path. The next cycle
    reads the real marketplace price again. Chat auto-replies are suppressed
    entirely because they are also external marketplace writes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._dry_run_price: float | None = None

    async def run_cycle(self, *, include_chat_autoreply: bool = True):
        self._dry_run_price = None
        try:
            return await super().run_cycle(
                include_chat_autoreply=include_chat_autoreply,
            )
        finally:
            # Never let a simulated price leak into the next polling cycle.
            self._dry_run_price = None

    def _read_current_price(
        self,
        runtime=None,
        *,
        allow_low_precision_fallback: bool = True,
    ) -> float | None:
        if self._dry_run_price is not None:
            return self._dry_run_price
        return super()._read_current_price(
            runtime=runtime,
            allow_low_precision_fallback=allow_low_precision_fallback,
        )

    async def _update_price(self, new_price: float, decision) -> bool:
        simulated_price = round(float(new_price), 4)
        self._dry_run_price = simulated_price
        reason = str(getattr(decision, 'reason', '') or '')
        if not reason.startswith('dry_run:'):
            decision.reason = f'dry_run:{reason}'
        logger.warning(
            '[%s] DRY_RUN: seller price write blocked: %s -> %s',
            self.profile_name,
            getattr(decision, 'old_price', None),
            simulated_price,
        )
        return True

    async def _run_chat_autoreply(self):
        logger.debug(
            '[%s] DRY_RUN: marketplace chat auto-reply writes are disabled',
            self.profile_name,
        )
        return None


def create_scheduler(*args: Any, **kwargs: Any) -> BaseScheduler:
    """Create the production or write-safe scheduler for the current mode."""
    scheduler_cls = DryRunScheduler if dry_run_enabled() else BaseScheduler
    if scheduler_cls is DryRunScheduler:
        logger.warning(
            'DRY_RUN is enabled: seller price writes and marketplace chat '
            'auto-replies are blocked'
        )
    return scheduler_cls(*args, **kwargs)


# ``src.main`` imports this alias after startup preflight has loaded .env.
# Missing DRY_RUN intentionally preserves the historical production behaviour.
RuntimeScheduler = DryRunScheduler if dry_run_enabled() else BaseScheduler
