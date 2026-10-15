"""Notification throttling and alert policy for scheduler runtimes."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .rsc_parser import ParseResult
from .storage import storage

logger = logging.getLogger(__name__)


class NotificationPolicy:
    """Own scheduler notification decisions without touching pricing logic."""

    def __init__(
        self,
        *,
        profile_id: str,
        profile_name: str,
        telegram_bot: Any,
        runtime_loader,
        runtime_storage: Any = storage,
    ) -> None:
        self.profile_id = profile_id
        self.profile_name = profile_name
        self.telegram_bot = telegram_bot
        self._runtime_loader = runtime_loader
        self._storage = runtime_storage

    def _tag(self, message: str) -> str:
        return f'[{self.profile_name}] {message}'

    async def notify_error_throttled(
        self,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
        runtime=None,
    ) -> None:
        current_runtime = runtime or self._runtime_loader()
        if not getattr(current_runtime, 'NOTIFY_ERRORS', True):
            muted_key = f'notify_errors_muted:{key}'
            if self._storage.should_send_alert(
                key=muted_key,
                cooldown_seconds=max(60, cooldown_seconds),
                profile_id=self.profile_id,
            ):
                logger.info(
                    '[%s] Telegram-уведомление об ошибке отключено '
                    '(NOTIFY_ERRORS=false): key=%s, message=%s',
                    self.profile_name,
                    key,
                    message,
                )
            return

        if self._storage.should_send_alert(
            key=key,
            cooldown_seconds=cooldown_seconds,
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_error(self._tag(message))
        else:
            logger.debug(
                '[%s] Уведомление подавлено throttling: key=%s',
                self.profile_name,
                key,
            )

    def log_warning_throttled(
        self,
        *,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
    ) -> None:
        log_key = f'log_warning:{key}'
        if self._storage.should_send_alert(
            key=log_key,
            cooldown_seconds=cooldown_seconds,
            profile_id=self.profile_id,
        ):
            logger.warning('[%s] %s', self.profile_name, message)
        else:
            logger.debug(
                '[%s] Лог предупреждения подавлен throttling: key=%s',
                self.profile_name,
                log_key,
            )

    async def notify_skip_throttled(
        self,
        runtime,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
    ) -> None:
        if not getattr(runtime, 'NOTIFY_SKIP', False):
            return
        if self._storage.should_send_alert(
            key='skip_notification',
            cooldown_seconds=getattr(
                runtime,
                'NOTIFY_SKIP_COOLDOWN_SECONDS',
                300,
            ),
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_skip(
                current_price=current_price,
                target_price=target_price,
                competitor_price=competitor_price,
                reason=reason,
                profile_name=self.profile_name,
            )
        else:
            logger.info('[%s] Skip-уведомление подавлено', self.profile_name)

    async def notify_competitor_change_if_needed(
        self,
        runtime,
        old_price: Optional[float],
        new_price: float,
        rank: Optional[int],
        url: Optional[str],
    ) -> None:
        if not getattr(runtime, 'NOTIFY_COMPETITOR_CHANGE', True):
            return
        if old_price is None:
            return
        delta = abs(new_price - old_price)
        if delta < getattr(runtime, 'COMPETITOR_CHANGE_DELTA', 0.0001):
            return
        if self._storage.should_send_alert(
            key='competitor_price_change',
            cooldown_seconds=getattr(
                runtime,
                'COMPETITOR_CHANGE_COOLDOWN_SECONDS',
                60,
            ),
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_competitor_price_changed(
                old_price=old_price,
                new_price=new_price,
                delta=delta,
                rank=rank,
                url=url,
                profile_name=self.profile_name,
            )

    async def notify_parser_issue_if_needed(
        self,
        runtime,
        url: str,
        result: ParseResult,
        *,
        fail_streak: int = 1,
    ) -> None:
        if not getattr(runtime, 'NOTIFY_PARSER_ISSUES', True):
            return

        reason = (
            result.block_reason
            or (f'http_{result.status_code}' if result.status_code else None)
            or 'parse_failed'
        )
        min_streak = 1
        if self.profile_id == 'digiseller':
            if reason in {'http_403', 'http_429', 'captcha', 'cloudflare'}:
                min_streak = 3
            else:
                min_streak = 2

        if fail_streak < min_streak:
            logger.info(
                '[%s] Parser-уведомление подавлено: fail_streak=%s < %s '
                '(reason=%s)',
                self.profile_name,
                fail_streak,
                min_streak,
                reason,
            )
            return

        key = f'parser_issue:{reason}'
        if not self._storage.should_send_alert(
            key=key,
            cooldown_seconds=getattr(
                runtime,
                'PARSER_ISSUE_COOLDOWN_SECONDS',
                300,
            ),
            profile_id=self.profile_id,
        ):
            return

        await self.telegram_bot.notify_parser_issue(
            url=url,
            method=result.method,
            reason=reason,
            error=result.error or 'unknown',
            status_code=result.status_code,
            profile_name=self.profile_name,
        )
