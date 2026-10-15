"""Runtime scheduler facade for behaviour-preserving post-v1 extraction.

The active scheduler now inherits only the low-level compatibility host. Every
extracted orchestration method is shadowed there, so a missing modular delegate
fails closed instead of silently executing a legacy copy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from . import chat_autoreply as chat_keys
from . import pricing_cycle_coordinator as pricing_cycle_module
from .chat_autoreply_coordinator import ChatAutoreplyCoordinator
from .config import config
from .notification_policy import NotificationPolicy
from .parser_coordinator import ParserCoordinator
from .pricing_cycle_coordinator import PricingCycleCoordinator
from .rsc_parser import ParseResult
from .scheduler_runtime_host import SchedulerRuntimeHost
from .storage_repositories import repositories, repository_storage

logger = logging.getLogger(__name__)

# PricingCycleCoordinator is intentionally kept source-compatible while its
# persistence dependency moves behind focused repositories. The facade exposes
# only the legacy methods used by that coordinator and routes each one to the
# appropriate repository.
pricing_cycle_module.storage = repository_storage


class ModularScheduler(SchedulerRuntimeHost):
    """Scheduler runtime that delegates every extracted responsibility."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._parser_coordinator = ParserCoordinator(
            profile_id=self.profile_id,
            profile_name=self.profile_name,
            runtime_loader=self._runtime,
            sync_cookies_from_env=self._sync_cookies_from_env,
            reload_cookies_from_backup=self._reload_cookies_from_backup,
            runtime_storage=repositories.runtime,
        )
        self._notification_policy = NotificationPolicy(
            profile_id=self.profile_id,
            profile_name=self.profile_name,
            telegram_bot=self.telegram_bot,
            runtime_loader=self._runtime,
            runtime_storage=repositories.runtime,
        )
        self._chat_autoreply_coordinator = ChatAutoreplyCoordinator(self)
        self._pricing_cycle_coordinator = PricingCycleCoordinator(self)

    def _runtime(self):
        default_urls = self._resolve_runtime_default_urls()
        return repositories.runtime.get_runtime_config(
            config,
            profile_id=self.profile_id,
            default_urls=default_urls,
        )

    def _resolve_runtime_default_urls(self) -> Optional[list[str]]:
        if not self._is_product_scoped_profile():
            if self.default_competitor_urls is None:
                return None
            return repositories.runtime.normalize_competitor_urls(
                self.default_competitor_urls or []
            )

        tracked = repositories.runtime.list_tracked_products(
            profile_id=self.base_profile_id,
            default_product_id=0,
            default_urls=[],
        )
        for item in tracked:
            tracked_product_id = int(item.get('product_id') or 0)
            if tracked_product_id != self.product_id:
                continue
            return repositories.runtime.normalize_competitor_urls(
                item.get('competitor_urls') or []
            )
        return []

    def _is_tracked_product_active(self) -> bool:
        if not self._is_product_scoped_profile():
            return True
        tracked = repositories.runtime.list_tracked_products(
            profile_id=self.base_profile_id,
            default_product_id=0,
            default_urls=[],
        )
        return any(
            int(item.get('product_id') or 0) == self.product_id
            for item in tracked
        )

    def _is_pair_enabled(self) -> bool:
        raw = repositories.runtime.get_runtime_setting(
            'PAIR_ENABLED',
            profile_id=self.profile_id,
            inherit_parent=False,
        )
        if raw is None:
            return True
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')

    def _state(self):
        return repositories.pricing.get_state(profile_id=self.profile_id)

    def _chat_meta_get(self, key: str) -> Optional[str]:
        return repositories.chat.get(key, profile_id=self.profile_id)

    def _chat_meta_set(self, key: str, value: str):
        repositories.chat.set(
            key,
            value,
            source='chat_autoreply',
            profile_id=self.profile_id,
        )

    def _chat_meta_inc(self, key: str, delta: int = 1):
        repositories.chat.increment(
            key,
            delta=delta,
            source='chat_autoreply',
            profile_id=self.profile_id,
        )

    def _is_autoreply_sent(self, order_id: int) -> bool:
        raw = repositories.chat.get(
            self._autoreply_key(order_id),
            profile_id=self.profile_id,
        )
        return bool((raw or '').strip())

    def _mark_autoreply_sent(self, order_id: int):
        repositories.chat.set(
            self._autoreply_key(order_id),
            datetime.now().isoformat(),
            source='chat_autoreply',
            profile_id=self.profile_id,
        )

    def _cleanup_autoreply_marks_if_due(self):
        every_hours = max(
            1,
            int(self._chat_cfg('CLEANUP_EVERY_HOURS', 24)),
        )
        ttl_days = max(
            1,
            int(self._chat_cfg('SENT_TTL_DAYS', 30)),
        )
        now = datetime.now()
        last_cleanup = self._parse_iso_datetime(
            self._chat_meta_get(chat_keys.KEY_LAST_CLEANUP_AT)
        )
        if last_cleanup and (now - last_cleanup) < timedelta(hours=every_hours):
            return

        rows = repositories.chat.list_with_last_change(
            profile_id=self.profile_id,
            key_prefix=chat_keys.SENT_PREFIX,
            limit=20000,
        )
        threshold = now - timedelta(days=ttl_days)
        deleted = 0
        for row in rows:
            key = str(row.get('key') or '')
            value = str(row.get('value') or '')
            sent_at = self._parse_iso_datetime(value)
            if sent_at is None:
                sent_at = self._parse_iso_datetime(row.get('last_change'))
            if sent_at is None or sent_at >= threshold:
                continue
            removed = repositories.chat.delete(
                key,
                source='chat_autoreply_gc',
                profile_id=self.profile_id,
            )
            if removed:
                deleted += 1

        self._chat_meta_set(
            chat_keys.KEY_LAST_CLEANUP_AT,
            now.isoformat(),
        )
        if deleted > 0:
            logger.info(
                '[%s] Очистка autoreply-markers: удалено %s (ttl_days=%s)',
                self.profile_name,
                deleted,
                ttl_days,
            )

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
