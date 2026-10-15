"""Telegram runtime facade with extracted settings flows."""

from __future__ import annotations

from typing import Any

from .modular_telegram_views_bot import ModularTelegramViewsBot
from .telegram_settings_flow import TelegramSettingsFlow


class ModularTelegramSettingsBot(ModularTelegramViewsBot):
    """Active Telegram runtime that delegates settings mutations."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._settings_flow = TelegramSettingsFlow(self)

    async def set_auto_enabled(self, update, *, enabled: bool):
        return await self._settings_flow.set_auto_enabled(
            update,
            enabled=enabled,
        )

    async def set_chat_autoreply_enabled(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ):
        return await self._settings_flow.set_chat_autoreply_enabled(
            chat_id,
            user_id,
            update,
            enabled=enabled,
        )

    async def set_chat_autoreply_only_empty_chat(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ):
        return await self._settings_flow.set_chat_autoreply_only_empty_chat(
            chat_id,
            user_id,
            update,
            enabled=enabled,
        )

    async def set_chat_autoreply_smart_non_empty(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ):
        return await self._settings_flow.set_chat_autoreply_smart_non_empty(
            chat_id,
            user_id,
            update,
            enabled=enabled,
        )

    async def cycle_chat_autoreply_policy(
        self,
        chat_id: int,
        user_id: int,
        update,
    ):
        return await self._settings_flow.cycle_chat_autoreply_policy(
            chat_id,
            user_id,
            update,
        )

    async def toggle_mode(self, chat_id: int, user_id: int, update):
        return await self._settings_flow.toggle_mode(
            chat_id,
            user_id,
            update,
        )

    async def cycle_rounding_step(
        self,
        chat_id: int,
        user_id: int,
        update,
    ):
        return await self._settings_flow.cycle_rounding_step(
            chat_id,
            user_id,
            update,
        )

    async def set_rebound_to_desired(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ):
        return await self._settings_flow.set_rebound_to_desired(
            chat_id,
            user_id,
            update,
            enabled=enabled,
        )

    async def handle_pending_action(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        update,
    ):
        handled = await self._settings_flow.handle_numeric_pending(
            chat_id,
            user_id,
            text,
            update,
        )
        if handled:
            return None
        return await super().handle_pending_action(
            chat_id,
            user_id,
            text,
            update,
        )

    async def _handle_price_guard_callback_query(
        self,
        update,
        query,
        data: str,
    ) -> None:
        return await self._settings_flow.handle_price_guard_callback(
            update,
            query,
            data,
        )

    def _chat_rules_save(
        self,
        *,
        profile_id: str,
        product_id: int,
        rules: dict[str, dict[str, Any]],
        user_id: int | None,
    ):
        return self._settings_flow.save_chat_rules(
            profile_id=profile_id,
            product_id=product_id,
            rules=rules,
            user_id=user_id,
        )
