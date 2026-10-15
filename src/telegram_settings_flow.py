"""Settings-flow coordinator for the modular Telegram runtime.

This component owns strategy/auto-price/chat-policy mutations initiated from
Telegram settings. Product CRUD remains a separate concern. The coordinator
uses the existing bot host for UI/context helpers while centralizing storage
writes and validation away from the monolithic TelegramBot class.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .storage import storage

logger = logging.getLogger(__name__)

NUMERIC_SETTING_ACTIONS = frozenset(
    {
        'DESIRED_PRICE',
        'UNDERCUT_VALUE',
        'RAISE_VALUE',
        'MIN_PRICE',
        'MAX_PRICE',
        'SHOWCASE_ROUND_STEP',
    }
)
CHAT_POLICY_SEQUENCE = (
    'ON_ORDER',
    'FIRST_BUYER_MESSAGE',
    'CODE_ONLY',
)


class TelegramSettingsFlow:
    """Coordinate settings mutations through the existing Telegram host."""

    def __init__(self, host: Any, *, runtime_storage: Any = storage) -> None:
        self._host = host
        self._storage = runtime_storage

    def __getattr__(self, name: str) -> Any:
        return getattr(self._host, name)

    async def set_auto_enabled(self, update, *, enabled: bool) -> None:
        if not update.message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        if not self._has_active_product_pair(profile_id, runtime=runtime):
            await self._reply_no_active_pair(update, profile_id)
            return
        product_id = self._product_id(profile_id)
        runtime_product = self._runtime_for_product(profile_id, product_id)
        if enabled and not list(
            getattr(runtime_product, 'COMPETITOR_URLS', []) or []
        ):
            await update.message.reply_text(
                (
                    '❌ У активного товара не задан URL конкурента. '
                    'Сначала привяжи конкурента в разделе «📦 Товары».'
                ),
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        user_id = update.effective_user.id if update.effective_user else None
        self._storage.set_auto_mode(
            enabled,
            profile_id=runtime_profile_id,
            user_id=user_id,
            source='telegram',
        )
        if enabled:
            self._storage.set_runtime_setting(
                'PAIR_ENABLED',
                'true',
                user_id=user_id,
                source='telegram',
                profile_id=runtime_profile_id,
            )
        logger.info(
            'Auto mode changed: profile=%s, product=%s, enabled=%s, user_id=%s',
            profile_id,
            product_id,
            enabled,
            user_id,
        )
        await update.message.reply_text(
            (
                f'🔔 Автоцена ({self._profile_name(profile_id)} / {product_id}): '
                f'{"ВКЛ" if enabled else "ВЫКЛ"}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def _set_chat_bool(
        self,
        *,
        chat_id: int,
        user_id: int,
        update,
        key: str,
        enabled: bool,
        message: str,
    ) -> None:
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return
        self._storage.set_runtime_setting(
            key,
            'true' if enabled else 'false',
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            message,
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def set_chat_autoreply_enabled(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ) -> None:
        await self._set_chat_bool(
            chat_id=chat_id,
            user_id=user_id,
            update=update,
            key='CHAT_AUTOREPLY_ENABLED',
            enabled=enabled,
            message=f'💬 Авто-инструкции: {"ВКЛ" if enabled else "ВЫКЛ"}',
        )

    async def set_chat_autoreply_only_empty_chat(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ) -> None:
        await self._set_chat_bool(
            chat_id=chat_id,
            user_id=user_id,
            update=update,
            key='CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
            enabled=enabled,
            message=(
                '📭 Отправка только в пустой чат: '
                f'{"ВКЛ" if enabled else "ВЫКЛ"}'
            ),
        )

    async def set_chat_autoreply_smart_non_empty(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ) -> None:
        await self._set_chat_bool(
            chat_id=chat_id,
            user_id=user_id,
            update=update,
            key='CHAT_AUTOREPLY_SMART_NON_EMPTY',
            enabled=enabled,
            message=(
                '🧠 Умный режим для непустого чата: '
                f'{"ВКЛ" if enabled else "ВЫКЛ"}'
            ),
        )

    async def cycle_chat_autoreply_policy(
        self,
        chat_id: int,
        user_id: int,
        update,
    ) -> None:
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return
        runtime = self._runtime(profile_id)
        if not self._has_active_product_pair(profile_id, runtime=runtime):
            await self._reply_no_active_pair(update, profile_id)
            return
        product_id = self._resolve_active_product_id(
            profile_id,
            runtime=runtime,
        )
        if int(product_id or 0) <= 0:
            await update.message.reply_text(
                '❌ Для активного товара не найден product_id',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return
        current = self._chat_autoreply_policy(
            profile_id,
            product_id=product_id,
        )
        try:
            index = CHAT_POLICY_SEQUENCE.index(current)
        except ValueError:
            index = 0
        new_policy = CHAT_POLICY_SEQUENCE[
            (index + 1) % len(CHAT_POLICY_SEQUENCE)
        ]
        self._storage.set_runtime_setting(
            f'CHAT_AUTOREPLY_POLICY:{int(product_id)}',
            new_policy,
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            (
                f'🧭 Режим отправки для товара {int(product_id)}: '
                f'{self._chat_policy_label(new_policy)}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def toggle_mode(self, chat_id: int, user_id: int, update) -> None:
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        if not self._has_active_product_pair(profile_id, runtime=runtime):
            await self._reply_no_active_pair(update, profile_id)
            return
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        new_mode = self._next_mode_for_profile(profile_id, runtime.MODE)
        self._storage.set_runtime_setting(
            'MODE',
            new_mode,
            user_id=user_id,
            source='telegram',
            profile_id=runtime_profile_id,
        )
        await update.message.reply_text(
            (
                f'✅ Режим ({self._profile_name(profile_id)} / {product_id}): '
                f'{self._mode_label(new_mode)}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def cycle_rounding_step(
        self,
        chat_id: int,
        user_id: int,
        update,
    ) -> None:
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        if not self._has_active_product_pair(profile_id, runtime=runtime):
            await self._reply_no_active_pair(update, profile_id)
            return
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        new_step = self._next_rounding_step(
            getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
        )
        self._storage.set_runtime_setting(
            'SHOWCASE_ROUND_STEP',
            str(new_step),
            user_id=user_id,
            source='telegram',
            profile_id=runtime_profile_id,
        )
        await update.message.reply_text(
            (
                f'✅ Округление витрины ({self._profile_name(profile_id)} / '
                f'{product_id}): {self._rounding_label(new_step)}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def set_rebound_to_desired(
        self,
        chat_id: int,
        user_id: int,
        update,
        *,
        enabled: bool,
    ) -> None:
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        if not self._has_active_product_pair(profile_id, runtime=runtime):
            await self._reply_no_active_pair(update, profile_id)
            return
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        self._storage.set_runtime_setting(
            'REBOUND_TO_DESIRED_ON_MIN',
            'true' if enabled else 'false',
            user_id=user_id,
            source='telegram',
            profile_id=runtime_profile_id,
        )
        await update.message.reply_text(
            (
                f'✅ Отскок к рекомендуемой цене ({self._profile_name(profile_id)} / '
                f'{product_id}): {"ВКЛ" if enabled else "ВЫКЛ"}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def handle_numeric_pending(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        update,
    ) -> bool:
        """Handle numeric settings input; return False for non-settings actions."""
        action, pending_profile_id = self._get_pending_action(chat_id)
        if action not in NUMERIC_SETTING_ACTIONS:
            return False
        if not update.message:
            return True
        profile_id = self._active_profile(chat_id)
        if self._is_pending_action_expired(chat_id):
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                '⌛ Незавершённый ввод устарел. Открой пункт заново.',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return True
        if pending_profile_id != profile_id:
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                (
                    '⚠️ Незавершённый ввод сброшен: '
                    'активный профиль был изменён.'
                ),
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return True
        runtime_parent = self._runtime(profile_id)
        product_id = self._resolve_active_product_id(
            profile_id,
            runtime=runtime_parent,
        )
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        if not self._has_active_product_pair(profile_id, runtime=runtime):
            self._clear_pending_action(chat_id)
            await self._reply_no_active_pair(update, profile_id)
            return True
        try:
            value = float(text.replace(',', '.'))
        except ValueError:
            await update.message.reply_text(
                '❌ Введи число',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return True
        if action == 'SHOWCASE_ROUND_STEP':
            if value < 0:
                await update.message.reply_text(
                    '❌ Значение должно быть >= 0',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return True
        elif value <= 0:
            await update.message.reply_text(
                '❌ Значение должно быть > 0',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return True
        runtime_min = float(getattr(runtime, 'MIN_PRICE', 0.0) or 0.0)
        runtime_max = float(getattr(runtime, 'MAX_PRICE', 0.0) or 0.0)
        if action == 'MIN_PRICE' and runtime_max > 0 and value > runtime_max:
            await update.message.reply_text(
                '❌ MIN_PRICE не может быть больше MAX_PRICE',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return True
        if action == 'MAX_PRICE' and runtime_min > 0 and value < runtime_min:
            await update.message.reply_text(
                '❌ MAX_PRICE не может быть меньше MIN_PRICE',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return True
        value = round(value, 4)
        self._storage.set_runtime_setting(
            action,
            str(value),
            user_id=user_id,
            source='telegram',
            profile_id=runtime_profile_id,
        )
        self._clear_pending_action(chat_id)
        await update.message.reply_text(
            (
                f'✅ {action} ({self._profile_name(profile_id)} / '
                f'{product_id}) = {value:.4f}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)
        return True

    async def handle_price_guard_callback(
        self,
        update,
        query,
        data: str,
    ) -> None:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        profile_id = self._active_profile(chat_id)
        parts = data.split(':')
        action = parts[1] if len(parts) > 1 else ''
        if (
            action in {'done', 'round', 'rebound'}
            and chat_id in self.pending_actions
        ):
            self._clear_pending_action(chat_id)
        if action == 'done':
            await query.answer('Готово')
            if query.message:
                await query.message.reply_text(
                    '✅ Лимиты и шаги закрыты',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
            return
        if action in {'min', 'max', 'under', 'raise', 'round', 'rebound'}:
            runtime = self._runtime(profile_id)
            if not self._has_active_product_pair(profile_id, runtime=runtime):
                if chat_id in self.pending_actions:
                    self._clear_pending_action(chat_id)
                await query.answer('Нет активной пары', show_alert=True)
                if query.message:
                    await query.message.reply_text(
                        (
                            '❌ Нет активной пары. Сначала добавь товар '
                            'в разделе «📦 Товары».'
                        ),
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                return
        if action in {'min', 'max', 'under', 'raise'}:
            action_map = {
                'min': ('MIN_PRICE', 'Введи нижний порог цены:'),
                'max': ('MAX_PRICE', 'Введи верхний порог цены:'),
                'under': (
                    'UNDERCUT_VALUE',
                    'Введи шаг понижения (например 0.0051 или 0.51):',
                ),
                'raise': (
                    'RAISE_VALUE',
                    'Введи шаг повышения (например 0.0049 или 0.49):',
                ),
            }
            pending_action, prompt = action_map[action]
            self._set_pending_action(chat_id, pending_action, profile_id)
            await query.answer('Жду значение')
            if query.message:
                await query.message.reply_text(
                    prompt,
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
            return
        if action == 'round':
            product_id = self._product_id(profile_id)
            runtime_profile_id = self._runtime_profile_id_for_product(
                profile_id,
                product_id,
            )
            runtime = self._runtime_for_product(profile_id, product_id)
            new_step = self._next_rounding_step(
                getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
            )
            self._storage.set_runtime_setting(
                'SHOWCASE_ROUND_STEP',
                str(new_step),
                user_id=user_id,
                source='telegram',
                profile_id=runtime_profile_id,
            )
            await query.answer(
                f'Округление: {self._rounding_label(new_step)}'
            )
            await self._refresh_price_guard_message(
                query=query,
                profile_id=profile_id,
            )
            return
        if action == 'rebound':
            product_id = self._product_id(profile_id)
            runtime_profile_id = self._runtime_profile_id_for_product(
                profile_id,
                product_id,
            )
            runtime = self._runtime_for_product(profile_id, product_id)
            enabled = bool(
                getattr(runtime, 'REBOUND_TO_DESIRED_ON_MIN', False)
            )
            new_enabled = not enabled
            self._storage.set_runtime_setting(
                'REBOUND_TO_DESIRED_ON_MIN',
                'true' if new_enabled else 'false',
                user_id=user_id,
                source='telegram',
                profile_id=runtime_profile_id,
            )
            await query.answer(
                f'Отскок: {"ВКЛ" if new_enabled else "ВЫКЛ"}'
            )
            await self._refresh_price_guard_message(
                query=query,
                profile_id=profile_id,
            )
            return
        await query.answer()

    def save_chat_rules(
        self,
        *,
        profile_id: str,
        product_id: int,
        rules: dict[str, dict[str, Any]],
        user_id: int | None,
    ) -> None:
        """Persist normalized chat-rule settings through one settings boundary."""
        normalized: dict[str, dict[str, Any]] = {}
        for key, value in (rules or {}).items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            normalized_key = key.strip().lower()
            if not normalized_key:
                continue
            normalized[normalized_key] = {
                'enabled': bool(value.get('enabled', True)),
                'text': str(value.get('text') or '').strip(),
                'option': str(value.get('option') or '').strip(),
                'value': str(value.get('value') or '').strip(),
            }
        payload = (
            json.dumps(
                {'version': 1, 'rules': normalized},
                ensure_ascii=False,
            )
            if normalized
            else ''
        )
        self._storage.set_runtime_setting(
            self._chat_rules_storage_key(product_id),
            payload,
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
