"""Telegram runtime facade with extracted keyboard/view construction."""

from __future__ import annotations

from typing import Any, Optional

from telegram import InlineKeyboardMarkup

from .modular_telegram_bot import ModularTelegramBot
from .telegram_bot import (
    BTN_AUTO_OFF,
    BTN_AUTO_ON,
    BTN_BACK,
    BTN_CHAT_AUTOREPLY_OFF,
    BTN_CHAT_AUTOREPLY_ON,
    BTN_CHAT_EMPTY_ONLY_OFF,
    BTN_CHAT_EMPTY_ONLY_ON,
    BTN_CHAT_POLICY,
    BTN_CHAT_RULES,
    BTN_CHAT_SMART_NON_EMPTY_OFF,
    BTN_CHAT_SMART_NON_EMPTY_ON,
    BTN_MAX,
    BTN_MIN,
    BTN_MODE,
    BTN_PRICE,
    BTN_PRICE_GUARD,
    BTN_PRODUCT_NEXT,
    BTN_PRODUCT_PREV,
    BTN_PRODUCT_REMOVE,
    BTN_PRODUCTS,
    BTN_PROFILE,
    BTN_RAISE,
    BTN_SETTINGS,
    BTN_STATUS,
    BTN_UNDERCUT,
)
from .telegram_views import (
    ProductButtonView,
    RuleButtonView,
    build_chat_rules_keyboard,
    build_main_keyboard,
    build_price_guard_keyboard,
    build_products_keyboard,
    build_profile_keyboard,
    build_settings_keyboard,
)


class ModularTelegramViewsBot(ModularTelegramBot):
    """Active Telegram runtime with extracted keyboard markup builders."""

    def get_main_keyboard(self, profile_id: Optional[str] = None):
        return build_main_keyboard(
            status=BTN_STATUS,
            products=BTN_PRODUCTS,
            previous_product=BTN_PRODUCT_PREV,
            next_product=BTN_PRODUCT_NEXT,
            profile=BTN_PROFILE,
            settings=BTN_SETTINGS,
        )

    def get_settings_keyboard(
        self,
        profile_id: Optional[str] = None,
    ):
        profile = profile_id or self.default_profile
        runtime = self._runtime(profile)
        active_product_id = self._resolve_active_product_id(
            profile,
            runtime=runtime,
        )
        state = self._state_for_product(profile, active_product_id)
        auto_enabled = self._auto_enabled_for_active_pair(
            profile,
            state=state,
            runtime=runtime,
        )
        chat_supported = self._chat_autoreply_supported(profile)
        chat_enabled = False
        empty_only_enabled = True
        smart_non_empty_enabled = False
        if chat_supported:
            chat_enabled = self._chat_autoreply_enabled(profile)
            empty_only_enabled = self._chat_autoreply_only_empty_chat(profile)
            smart_non_empty_enabled = self._chat_autoreply_smart_non_empty(profile)

        return build_settings_keyboard(
            auto_on=BTN_AUTO_ON,
            auto_off=BTN_AUTO_OFF,
            auto_enabled=auto_enabled,
            price=BTN_PRICE,
            mode=BTN_MODE,
            price_guard=BTN_PRICE_GUARD,
            product_remove=BTN_PRODUCT_REMOVE,
            back=BTN_BACK,
            chat_supported=chat_supported,
            chat_on=BTN_CHAT_AUTOREPLY_ON,
            chat_off=BTN_CHAT_AUTOREPLY_OFF,
            chat_enabled=chat_enabled,
            empty_only_on=BTN_CHAT_EMPTY_ONLY_ON,
            empty_only_off=BTN_CHAT_EMPTY_ONLY_OFF,
            empty_only_enabled=empty_only_enabled,
            smart_non_empty_on=BTN_CHAT_SMART_NON_EMPTY_ON,
            smart_non_empty_off=BTN_CHAT_SMART_NON_EMPTY_OFF,
            smart_non_empty_enabled=smart_non_empty_enabled,
            chat_policy=BTN_CHAT_POLICY,
            chat_rules=BTN_CHAT_RULES,
        )

    def get_profile_keyboard(self):
        return build_profile_keyboard(
            [self._profile_button(pid) for pid in self.available_profiles],
            back=BTN_BACK,
        )

    def _price_guard_inline_keyboard(
        self,
        *,
        profile_id: str,
    ) -> InlineKeyboardMarkup:
        runtime_parent = self._runtime(profile_id)
        product_id = self._resolve_active_product_id(
            profile_id,
            runtime=runtime_parent,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        round_step = getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
        rebound_enabled = bool(
            getattr(runtime, 'REBOUND_TO_DESIRED_ON_MIN', False)
        )
        rounding_label = f'🔘 Округление: {self._rounding_label(round_step)}'
        return build_price_guard_keyboard(
            min_label=BTN_MIN,
            max_label=BTN_MAX,
            undercut_label=BTN_UNDERCUT,
            raise_label=BTN_RAISE,
            rounding_label=rounding_label,
            rebound_enabled=rebound_enabled,
        )

    def _chat_rules_inline_keyboard(
        self,
        *,
        items: list[dict[str, str]],
        rules: dict[str, dict[str, Any]],
    ) -> InlineKeyboardMarkup:
        entries: list[RuleButtonView] = []
        for idx, item in enumerate(items, start=1):
            entry = rules.get(item['key']) or {}
            label = self._trim_rule_button_text(
                item.get('value') or item.get('label') or ''
            )
            entries.append(
                RuleButtonView(
                    index=idx,
                    label=label,
                    enabled=bool(entry.get('enabled', False)),
                )
            )
        return build_chat_rules_keyboard(entries)

    def _products_inline_keyboard(
        self,
        profile_id: str,
        *,
        runtime: Optional[Any] = None,
        confirm: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        tracked = self._tracked_products(profile_id, runtime=runtime)
        active_product_id = self._product_id(profile_id)
        entries: list[ProductButtonView] = []
        for item in tracked:
            product_id = int(item.get('product_id') or 0)
            if product_id <= 0:
                continue
            entries.append(
                ProductButtonView(
                    product_id=product_id,
                    label=self._product_label(profile_id, product_id),
                    active=product_id == active_product_id,
                )
            )
        return build_products_keyboard(entries, confirm=confirm)
