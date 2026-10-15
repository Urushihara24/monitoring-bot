"""Modular Telegram runtime facade.

This first Telegram decomposition slice keeps command/routing and settings
behaviour in the compatibility ``TelegramBot`` while moving status and
diagnostics rendering behind a pure view layer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update

from .storage import storage
from .telegram_bot import TelegramBot
from .telegram_rendering import (
    DiagnosticsView,
    StatusView,
    render_diagnostics,
    render_status,
)
from .validator import validate_runtime_config

logger = logging.getLogger(__name__)


class ModularTelegramBot(TelegramBot):
    """Active Telegram runtime with extracted status/diagnostics rendering."""

    async def send_status(
        self,
        chat_id: int,
        update: Update,
        profile_id: Optional[str] = None,
    ):
        if not update.message:
            return
        profile = profile_id or self._active_profile(chat_id)
        if profile not in self.available_profiles:
            profile = self._active_profile(chat_id)
        profile_id = profile
        profile_name = self._profile_name(profile_id)
        runtime_base = self._runtime(profile_id)
        product_id = self._resolve_active_product_id(
            profile_id,
            runtime=runtime_base,
        )
        state = self._state_for_product(profile_id, product_id)
        runtime = self._runtime_for_product(profile_id, product_id)
        runtime_source = self._product_runtime_source(profile_id, product_id)
        pair_enabled = self._is_pair_enabled(profile_id, product_id)
        auto_enabled = self._auto_enabled_for_active_pair(
            profile_id,
            state=state,
            runtime=runtime,
        )
        tracked_lines = self._format_tracked_products(profile_id, runtime=runtime)
        tracked_count = len(tracked_lines) if tracked_lines != ['нет'] else 0
        has_active_pair = self._has_active_product_pair(
            profile_id,
            runtime=runtime,
        )
        active_product_slot, active_product_total = self._active_product_slot(
            profile_id,
            runtime=runtime,
        )
        active_product_slot_text = (
            f'{active_product_slot}/{active_product_total}'
            if active_product_total else 'N/A'
        )

        monitor_enabled = bool(runtime.COMPETITOR_URLS)
        monitor_mode = (
            f'АКТИВЕН ({len(runtime.COMPETITOR_URLS)} URL)'
            if monitor_enabled
            else 'ВЫКЛ (нет URL)'
        )
        last_update = state.get('last_update')
        update_str = (
            last_update.strftime('%Y-%m-%d %H:%M')
            if last_update else 'Никогда'
        )

        parse_at = state.get('last_competitor_parse_at')
        parse_at_str = (
            parse_at.strftime('%Y-%m-%d %H:%M:%S')
            if parse_at else 'Никогда'
        )
        competitor_url = state.get('last_competitor_url') or 'N/A'
        parse_method = state.get('last_competitor_method') or 'N/A'

        target_price = state.get('last_target_price')
        if target_price is None:
            target_price = state.get('last_price')
        display_price: Optional[float] = None
        client = self._api_client(profile_id)
        # Preserve historical status semantics: live-price lookup uses the
        # profile's selected product id after state/runtime resolution.
        product_id = self._product_id(profile_id)
        get_display_price = (
            getattr(client, 'get_display_price', None) if client else None
        )
        get_my_price = getattr(client, 'get_my_price', None) if client else None
        if profile_id == 'ggsel':
            display_price = target_price
            get_public_price = (
                getattr(client, 'get_public_price', None) if client else None
            )
            if callable(get_public_price) and product_id > 0:
                try:
                    public_price = await asyncio.to_thread(
                        get_public_price,
                        product_id,
                    )
                    if public_price is not None:
                        display_price = float(public_price)
                except Exception as exc:
                    logger.warning(
                        '[%s] Не удалось получить публичную цену для статуса: %s',
                        profile_name,
                        exc,
                    )
            if display_price is None:
                if callable(get_my_price) and product_id > 0:
                    try:
                        api_price = await asyncio.to_thread(
                            get_my_price,
                            product_id,
                        )
                        if api_price is not None:
                            display_price = float(api_price)
                    except Exception as exc:
                        logger.warning(
                            '[%s] Не удалось получить API-цену для статуса: %s',
                            profile_name,
                            exc,
                        )
        else:
            if callable(get_display_price) and product_id > 0:
                try:
                    resolved_price = await asyncio.to_thread(
                        get_display_price,
                        product_id,
                    )
                    if resolved_price is not None:
                        display_price = float(resolved_price)
                except Exception as exc:
                    logger.warning(
                        '[%s] Не удалось получить display-цену для статуса: %s',
                        profile_name,
                        exc,
                    )
            if (
                display_price is None
                and profile_id != 'digiseller'
                and callable(get_my_price)
                and product_id > 0
            ):
                try:
                    api_price = await asyncio.to_thread(
                        get_my_price,
                        product_id,
                    )
                    if api_price is not None:
                        display_price = float(api_price)
                except Exception as exc:
                    logger.warning(
                        '[%s] Не удалось получить live-цену для статуса: %s',
                        profile_name,
                        exc,
                    )
            if display_price is None:
                display_price = target_price

        competitor_price = state.get('last_competitor_min')
        target_price_str = (
            f'{target_price:.4f}' if target_price is not None else 'N/A'
        )
        display_price_str = (
            f'{display_price:.4f}' if display_price is not None else 'N/A'
        )
        competitor_price_str = (
            f'{competitor_price:.4f}'
            if competitor_price is not None else 'N/A'
        )
        if profile_id == 'ggsel':
            display_price_label = '💰 Моя цена'
            target_price_label = '🎯 Цена по стратегии'
        else:
            display_price_label = '💰 Моя цена'
            target_price_label = '🎯 Выставлено ботом'
        pair_active_label = (
            'Да'
            if pair_enabled and has_active_pair
            else 'Нет'
            if has_active_pair
            else '—'
        )
        chat_block = ''
        chat_meta = self._chat_autoreply_meta(profile_id)
        if chat_meta:
            if chat_meta['enabled']:
                chat_block = (
                    '\n'
                    '💬 Авто-инструкции: ВКЛ\n'
                    '🧷 Только по правилам: '
                    f'{"Да" if chat_meta["require_rules"] else "Нет"}\n'
                    '🧭 Режим отправки: '
                    f'{self._chat_policy_label(chat_meta["policy"])}\n'
                    f'📨 Отправлено: {chat_meta["sent_count"]}\n'
                    f'🕓 Последняя отправка: {chat_meta["last_sent"]}'
                )
            else:
                chat_block = '\n💬 Авто-инструкции: ВЫКЛ'

        text = render_status(
            StatusView(
                profile_name=profile_name,
                product_label=self._product_label(profile_id, product_id),
                active_product_slot=active_product_slot_text,
                runtime_source=runtime_source,
                tracked_count=tracked_count,
                display_price_label=display_price_label,
                display_price=display_price_str,
                target_price_label=target_price_label,
                target_price=target_price_str,
                competitor_price=competitor_price_str,
                competitor_url=competitor_url,
                parse_method=parse_method,
                parse_at=parse_at_str,
                monitor_mode=monitor_mode,
                pair_active_label=pair_active_label,
                chat_block=chat_block,
                auto_enabled=auto_enabled,
                mode_label=self._mode_label(runtime.MODE),
                update_at=update_str,
                check_interval=runtime.CHECK_INTERVAL,
            )
        )
        await update.message.reply_text(
            text,
            reply_markup=self.get_main_keyboard(profile_id),
        )

    async def send_diagnostics(
        self,
        chat_id: int,
        update: Update,
        profile_id: Optional[str] = None,
    ):
        if not update.message:
            return
        profile = profile_id or self._active_profile(chat_id)
        if profile not in self.available_profiles:
            profile = self._active_profile(chat_id)
        profile_id = profile
        profile_name = self._profile_name(profile_id)
        runtime_parent = self._runtime(profile_id)
        product_id = self._resolve_active_product_id(
            profile_id,
            runtime=runtime_parent,
        )
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        state = self._state_for_product(profile_id, product_id)
        runtime = self._runtime_for_product(profile_id, product_id)
        is_valid, errors = validate_runtime_config(runtime)

        api_ok = False
        product_price = None
        product_ok = False
        refresh_line = None
        client = self._api_client(profile_id)
        if client:
            try:
                api_ok = await asyncio.to_thread(client.check_api_access)
                if api_ok and product_id:
                    product = await asyncio.to_thread(
                        client.get_product,
                        product_id,
                    )
                    product_ok = product is not None
                    product_price = product.price if product else None
            except Exception as exc:
                logger.error('Ошибка API в диагностике: %s', exc)
            try:
                if hasattr(client, 'can_refresh_access_token'):
                    can_refresh = await asyncio.to_thread(
                        client.can_refresh_access_token,
                    )
                    refresh_line = (
                        'Token refresh: '
                        f'{"OK" if can_refresh else "FAIL"}'
                    )
            except Exception as exc:
                logger.error('Ошибка проверки refresh capability: %s', exc)

        perms_line = None
        if client and hasattr(client, 'get_token_perms_status'):
            try:
                perms_ok, perms_desc = await asyncio.to_thread(
                    client.get_token_perms_status,
                )
                perms_line = (
                    f'Token perms: {"OK" if perms_ok else "FAIL"} '
                    f'({perms_desc})'
                )
            except Exception as exc:
                logger.error('Ошибка token/perms в диагностике: %s', exc)

        chat_perms_line = None
        if client and hasattr(client, 'get_chat_perms_status'):
            try:
                chat_ok, chat_desc = await asyncio.to_thread(
                    client.get_chat_perms_status,
                    8,
                    False,
                )
                chat_perms_line = (
                    f'Chat perms: {"OK" if chat_ok else "FAIL"} '
                    f'({chat_desc})'
                )
            except Exception as exc:
                logger.error('Ошибка chat/perms в диагностике: %s', exc)

        now = datetime.now()
        last_cycle = state.get('last_cycle')
        age = int((now - last_cycle).total_seconds()) if last_cycle else 0
        extra_lines: list[str] = []
        if perms_line:
            extra_lines.append(perms_line)
        if chat_perms_line:
            extra_lines.append(chat_perms_line)
        if refresh_line:
            extra_lines.append(refresh_line)

        auto_change = storage.get_last_setting_change(
            'auto_mode',
            profile_id=runtime_profile_id,
        )
        if auto_change:
            auto_actor = auto_change.get('user_id')
            auto_actor_text = (
                str(auto_actor) if auto_actor is not None else 'system'
            )
            extra_lines.append(
                'Auto changed: '
                f'{auto_change.get("timestamp")} by {auto_actor_text} '
                f'({auto_change.get("source")}) '
                f'{auto_change.get("old_value")}→{auto_change.get("new_value")}'
            )

        monitor_change = storage.get_last_setting_change(
            'competitor_urls',
            profile_id=runtime_profile_id,
        )
        if monitor_change is None and runtime_profile_id != profile_id:
            monitor_change = storage.get_last_setting_change(
                'competitor_urls',
                profile_id=profile_id,
            )
        if monitor_change:
            monitor_actor = monitor_change.get('user_id')
            monitor_actor_text = (
                str(monitor_actor) if monitor_actor is not None else 'system'
            )
            extra_lines.append(
                'Monitoring changed: '
                f'{monitor_change.get("timestamp")} by {monitor_actor_text} '
                f'({monitor_change.get("source")})'
            )

        chat_meta = self._chat_autoreply_meta(profile_id)
        if chat_meta:
            extra_lines.append(
                'Chat autoreply: '
                f'{"ON" if chat_meta["enabled"] else "OFF"} '
                f'(sent={chat_meta["sent_count"]})'
            )
            extra_lines.append(
                'Chat dedupe: '
                f'{"ON" if chat_meta["dedupe"] else "OFF"} '
                f'(duplicates={chat_meta["duplicate_count"]}, '
                f'lookback={chat_meta["lookback"]})'
            )
            extra_lines.append(
                f'Chat interval: {chat_meta["interval_seconds"]}s'
            )
            extra_lines.append(f'Chat last run: {chat_meta["last_run"]}')
            extra_lines.append(f'Chat last sent: {chat_meta["last_sent"]}')
            extra_lines.append(
                f'Chat last cleanup: {chat_meta["last_cleanup"]}'
            )
            if chat_meta['last_error'] != 'N/A':
                extra_lines.append(
                    f'Chat last error: {chat_meta["last_error"]}'
                )

        text = render_diagnostics(
            DiagnosticsView(
                profile_name=profile_name,
                api_ok=api_ok,
                product_ok=product_ok,
                product_price=self._fmt_price(product_price),
                config_valid=is_valid,
                heartbeat_seconds=age,
                auto_enabled=state.get('auto_mode', True),
                competitor_count=len(runtime.COMPETITOR_URLS),
                last_parser_error=(
                    state.get('last_competitor_error') or 'N/A'
                ),
                last_block_reason=(
                    state.get('last_competitor_block_reason') or 'N/A'
                ),
                extra_lines=tuple(extra_lines),
                errors=tuple(errors),
            )
        )
        await update.message.reply_text(
            text,
            reply_markup=self.get_main_keyboard(profile_id),
        )
