"""Runtime host for the decomposed scheduler.

The historical :class:`src.scheduler.Scheduler` remains importable as a frozen
compatibility/reference implementation, but active runtimes must not silently
fall back to orchestration bodies that have already moved to dedicated
components. This host shadows every extracted orchestration method with an
explicit failure. ``ModularScheduler`` supplies the real delegates.
"""

from __future__ import annotations

from typing import Any

from .scheduler import Scheduler as LegacyScheduler


class ExtractedSchedulerMethodError(RuntimeError):
    """Raised if an active scheduler host misses an extracted delegate."""


class SchedulerRuntimeHost(LegacyScheduler):
    """Low-level scheduler host with legacy orchestration fallbacks disabled."""

    @staticmethod
    def _extracted(method: str) -> None:
        raise ExtractedSchedulerMethodError(
            f'{method} was extracted from the legacy Scheduler; '
            'use ModularScheduler/runtime delegates instead'
        )

    async def run_cycle(self, *, include_chat_autoreply: bool = True):
        self._extracted('run_cycle')

    async def _parse_competitor_price(self, url: str, runtime, timeout: int = 15):
        self._extracted('_parse_competitor_price')

    async def _notify_error_throttled(
        self,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
        runtime=None,
    ):
        self._extracted('_notify_error_throttled')

    def _log_warning_throttled(
        self,
        *,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
    ) -> None:
        self._extracted('_log_warning_throttled')

    async def _notify_skip_throttled(
        self,
        runtime,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
    ):
        self._extracted('_notify_skip_throttled')

    async def _notify_competitor_change_if_needed(
        self,
        runtime,
        old_price,
        new_price: float,
        rank,
        url,
    ):
        self._extracted('_notify_competitor_change_if_needed')

    async def _notify_parser_issue_if_needed(
        self,
        runtime,
        url: str,
        result: Any,
        *,
        fail_streak: int = 1,
    ):
        self._extracted('_notify_parser_issue_if_needed')

    async def _run_chat_autoreply(self):
        self._extracted('_run_chat_autoreply')
