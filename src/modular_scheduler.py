"""Runtime scheduler facade for behaviour-preserving post-v1 extraction.

``Scheduler`` remains the compatibility base while responsibilities move into
small components. Runtime construction should prefer ``ModularScheduler`` so
new boundaries become active without one large rewrite of the legacy module.
"""

from __future__ import annotations

from typing import Any, Optional

from .chat_autoreply_coordinator import ChatAutoreplyCoordinator
from .notification_policy import NotificationPolicy
from .parser_coordinator import ParserCoordinator
from .pricing_cycle_coordinator import PricingCycleCoordinator
from .rsc_parser import ParseResult
from .scheduler import Scheduler


class ModularScheduler(Scheduler):
    """Scheduler runtime that delegates extracted responsibilities."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._parser_coordinator = ParserCoordinator(
            profile_id=self.profile_id,
            profile_name=self.profile_name,
            runtime_loader=self._runtime,
            sync_cookies_from_env=self._sync_cookies_from_env,
            reload_cookies_from_backup=self._reload_cookies_from_backup,
        )
        self._notification_policy = NotificationPolicy(
            profile_id=self.profile_id,
            profile_name=self.profile_name,
            telegram_bot=self.telegram_bot,
            runtime_loader=self._runtime,
        )
        self._chat_autoreply_coordinator = ChatAutoreplyCoordinator(self)
        self._pricing_cycle_coordinator = PricingCycleCoordinator(self)

    async def run_cycle(self, *, include_chat_autoreply: bool = True):
        return await self._pricing_cycle_coordinator.run(
            include_chat_autoreply=include_chat_autoreply,
        )

    async def _parse_competitor_price(
        self,
        url: str,
        runtime,
        timeout: int = 15,
    ) -> ParseResult:
        return await self._parser_coordinator.parse_competitor_price(
            url,
            runtime=runtime,
            timeout=timeout,
        )

    async def _notify_error_throttled(
        self,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
        runtime=None,
    ):
        return await self._notification_policy.notify_error_throttled(
            key=key,
            message=message,
            cooldown_seconds=cooldown_seconds,
            runtime=runtime,
        )

    def _log_warning_throttled(
        self,
        *,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
    ) -> None:
        return self._notification_policy.log_warning_throttled(
            key=key,
            message=message,
            cooldown_seconds=cooldown_seconds,
        )

    async def _notify_skip_throttled(
        self,
        runtime,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
    ):
        return await self._notification_policy.notify_skip_throttled(
            runtime=runtime,
            current_price=current_price,
            target_price=target_price,
            competitor_price=competitor_price,
            reason=reason,
        )

    async def _notify_competitor_change_if_needed(
        self,
        runtime,
        old_price: Optional[float],
        new_price: float,
        rank: Optional[int],
        url: Optional[str],
    ):
        return await self._notification_policy.notify_competitor_change_if_needed(
            runtime=runtime,
            old_price=old_price,
            new_price=new_price,
            rank=rank,
            url=url,
        )

    async def _notify_parser_issue_if_needed(
        self,
        runtime,
        url: str,
        result: ParseResult,
        *,
        fail_streak: int = 1,
    ):
        return await self._notification_policy.notify_parser_issue_if_needed(
            runtime=runtime,
            url=url,
            result=result,
            fail_streak=fail_streak,
        )

    async def _run_chat_autoreply(self):
        return await self._chat_autoreply_coordinator.run()
