"""
Telegram бот с Reply Keyboard.
Поддерживает профильный режим (GGSEL / DIGISELLER).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import chat_autoreply as chat_keys
from .config import config
from .pricing_mode import (
    next_pricing_mode,
    normalize_pricing_mode,
    pricing_mode_label,
)
from .profile_smoke import run_profile_smoke
from .storage import DEFAULT_PROFILE, storage
from .validator import validate_runtime_config

logger = logging.getLogger(__name__)

# Главное меню
BTN_STATUS = '📊 Статус'
BTN_AUTO_ON = '🔔 Авто: ВКЛ'
BTN_AUTO_OFF = '🔕 Авто: ВЫКЛ'
BTN_PROFILE = '🧩 Профиль'
BTN_SETTINGS = '⚙ Настройки'
BTN_BACK = '🔙 Назад'

# Настройки
BTN_PRICE = '🎯 Цена'
BTN_PRICE_GUARD = '🧮 Лимиты и шаги'
BTN_MIN = '📉 Мин'
BTN_MAX = '📈 Макс'
BTN_UNDERCUT = '↘️ Шаг-'
BTN_RAISE = '↗️ Шаг+'
BTN_ROUNDING = '🔘 Округление'
BTN_PRODUCTS = '📦 Товары'
BTN_PRODUCT_REMOVE = '🗑 Удалить товар'
BTN_PRODUCT_PREV = '⬅ Пред. товар'
BTN_PRODUCT_NEXT = '➡ След. товар'
BTN_MODE = '🔀 Режим'
BTN_REBOUND_ON = '🔁 Отскок: ВКЛ'
BTN_REBOUND_OFF = '🔁 Отскок: ВЫКЛ'
BTN_CHAT_AUTOREPLY_ON = '💬 Инструкции: ВКЛ'
BTN_CHAT_AUTOREPLY_OFF = '💬 Инструкции: ВЫКЛ'
BTN_CHAT_EMPTY_ONLY_ON = '📭 Только пустой чат: ВКЛ'
BTN_CHAT_EMPTY_ONLY_OFF = '📨 Только пустой чат: ВЫКЛ'
BTN_CHAT_SMART_NON_EMPTY_ON = '🧠 Умный непустой: ВКЛ'
BTN_CHAT_SMART_NON_EMPTY_OFF = '🧠 Умный непустой: ВЫКЛ'
BTN_CHAT_POLICY = '🧭 Режим отправки'
BTN_CHAT_RULES = '📝 Правила инстр.'

_CHAT_PROFILE_PREFIX = {
    'ggsel': 'GGSEL',
    'digiseller': 'DIGISELLER',
}
_FRIEND_RULE_KEYWORDS = (
    'друз',
    'friend',
    'добавл',
    'already',
    'проверил',
    'проверила',
)
_CHAT_POLICY_SEQUENCE = (
    'ON_ORDER',
    'FIRST_BUYER_MESSAGE',
    'CODE_ONLY',
)
_PENDING_ACTION_TIMEOUT_SECONDS = 300
_CHAT_POLICY_LABELS_RU = {
    'ON_ORDER': 'После заказа',
    'FIRST_BUYER_MESSAGE': 'После 1-го сообщения',
    'CODE_ONLY': 'Только при коде',
}


class TelegramBot:
    """Telegram бот управления."""

    def __init__(
        self,
        api_client=None,
        *,
        api_clients: Optional[Dict[str, object]] = None,
        profile_products: Optional[Dict[str, int]] = None,
        profile_default_urls: Optional[Dict[str, list]] = None,
        profile_labels: Optional[Dict[str, str]] = None,
    ):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.admin_ids = set(config.TELEGRAM_ADMIN_IDS)
        self._app: Optional[Application] = None
        self.pending_actions: Dict[int, Tuple[str, str]] = {}
        self.pending_action_started_at: Dict[int, float] = {}
        self.manage_products_context: Dict[int, Dict[str, Any]] = {}
        self.chat_profile: Dict[int, str] = {}
        self.chat_rules_context: Dict[int, Dict[str, Any]] = {}

        if api_clients is None:
            api_clients = {DEFAULT_PROFILE: api_client} if api_client else {}
        self.api_clients: Dict[str, object] = {
            k.strip().lower(): v
            for k, v in api_clients.items()
            if v is not None
        }
        self.profile_primary_products = {
            (k or '').strip().lower(): int(v or 0)
            for k, v in (profile_products or {}).items()
        }
        self.profile_products = dict(self.profile_primary_products)
        self.profile_default_urls = {
            (k or '').strip().lower(): (v or [])
            for k, v in (profile_default_urls or {}).items()
        }
        self.profile_labels = {
            (k or '').strip().lower(): str(v)
            for k, v in (profile_labels or {}).items()
        }
        if not self.profile_labels:
            self.profile_labels = {
                'ggsel': 'GGSEL',
                'digiseller': 'DIGISELLER',
            }
        self.available_profiles = sorted(self.api_clients.keys()) or [DEFAULT_PROFILE]
        self.default_profile = (
            DEFAULT_PROFILE
            if DEFAULT_PROFILE in self.available_profiles
            else self.available_profiles[0]
        )

    # ================================
    # Helpers
    # ================================
    def _normalize_text(self, text: str) -> str:
        text_clean = unicodedata.normalize('NFKC', text or '')
        for ch in ('\ufe0f', '\ufe0e', '\u200d', '\u200b'):
            text_clean = text_clean.replace(ch, '')
        return text_clean.strip()

    def _profile_name(self, profile_id: str) -> str:
        return self.profile_labels.get(profile_id, profile_id.upper())

    def _normalize_mode(self, mode: object) -> str:
        return normalize_pricing_mode(mode)

    def _mode_label(self, mode: object) -> str:
        return pricing_mode_label(mode)

    def _next_mode(self, mode: object) -> str:
        return next_pricing_mode(mode)

    def _rounding_label(self, step: object) -> str:
        try:
            value = float(step or 0)
        except Exception:
            value = 0.0
        if value <= 0:
            return 'выкл'
        return f'{value:g}'

    def _next_rounding_step(self, step: object) -> float:
        sequence = [0.0, 0.0001, 0.01, 1.0]
        try:
            current = float(step or 0)
        except Exception:
            current = 0.0
        for idx, candidate in enumerate(sequence):
            if abs(candidate - current) < 1e-9:
                return sequence[(idx + 1) % len(sequence)]
        return sequence[0]

    def _active_profile(self, chat_id: Optional[int]) -> str:
        if chat_id is None:
            return self.default_profile
        profile = self.chat_profile.get(chat_id)
        if profile in self.available_profiles:
            return profile
        return self.default_profile

    def _set_profile(self, chat_id: int, profile_id: str):
        profile = (profile_id or '').strip().lower()
        if profile in self.available_profiles:
            self.chat_profile[chat_id] = profile

    def _set_pending_action(
        self,
        chat_id: int,
        action: str,
        profile_id: str,
    ):
        """Сохраняет pending-действие с привязкой к активному профилю."""
        if action != 'CHAT_RULES':
            self._clear_chat_rules_context(chat_id)
        self._clear_manage_products_context(chat_id)
        self.pending_actions[chat_id] = (action, profile_id)
        self.pending_action_started_at[chat_id] = time.monotonic()

    def _clear_manage_products_context(self, chat_id: int):
        self.manage_products_context.pop(chat_id, None)

    def _clear_pending_action(self, chat_id: int):
        self.pending_actions.pop(chat_id, None)
        self.pending_action_started_at.pop(chat_id, None)
        self._clear_chat_rules_context(chat_id)
        self._clear_manage_products_context(chat_id)

    def _clear_chat_rules_context(self, chat_id: int):
        self.chat_rules_context.pop(chat_id, None)

    async def _prompt_pending_action(
        self,
        *,
        chat_id: int,
        profile_id: str,
        action: str,
        prompt: str,
        update: Update,
    ):
        if not update.message:
            return
        self._set_pending_action(chat_id, action, profile_id)
        await update.message.reply_text(
            prompt,
            reply_markup=self.get_settings_keyboard(profile_id),
        )

    def _get_pending_action(self, chat_id: int) -> Tuple[Optional[str], str]:
        """
        Возвращает (action, profile_id) для pending-действия.
        Поддерживает soft-миграцию legacy-значения (str) в (str, profile_id).
        """
        pending = self.pending_actions.get(chat_id)
        if pending is None:
            self.pending_action_started_at.pop(chat_id, None)
            return None, self._active_profile(chat_id)
        if isinstance(pending, tuple) and len(pending) == 2:
            action, profile_id = pending
            self.pending_action_started_at.setdefault(
                chat_id,
                time.monotonic(),
            )
            return action, profile_id

        # Soft migration для in-memory legacy формата.
        action = str(pending)
        profile_id = self._active_profile(chat_id)
        self.pending_actions[chat_id] = (action, profile_id)
        self.pending_action_started_at[chat_id] = time.monotonic()
        return action, profile_id

    def _is_pending_action_expired(self, chat_id: int) -> bool:
        started_at = self.pending_action_started_at.get(chat_id)
        if started_at is None:
            return False
        return (
            time.monotonic() - started_at
            > _PENDING_ACTION_TIMEOUT_SECONDS
        )

    def _resolve_profile_arg(self, value: str) -> Optional[str]:
        normalized = (value or '').strip().lower()
        if not normalized:
            return None
        aliases = {
            'gg': 'ggsel',
            'ggsel': 'ggsel',
            'dg': 'digiseller',
            'digi': 'digiseller',
            'digiseller': 'digiseller',
            'plati': 'digiseller',
        }
        resolved = aliases.get(normalized, normalized)
        if resolved in self.available_profiles:
            return resolved
        return None

    async def _resolve_command_profile(
        self,
        *,
        chat_id: int,
        update: Update,
        context: Optional[ContextTypes.DEFAULT_TYPE],
    ) -> Optional[str]:
        """
        Возвращает профиль для slash-команды.
        По умолчанию — активный профиль чата.
        Если передан аргумент и он невалидный — отправляет ошибку и
        возвращает None.
        """
        profile_id = self._active_profile(chat_id)
        if not context or not getattr(context, 'args', None):
            return profile_id

        candidate = self._resolve_profile_arg(context.args[0])
        if candidate:
            return candidate

        if update.message:
            available = ', '.join(
                self._profile_name(pid).lower()
                for pid in self.available_profiles
            )
            await update.message.reply_text(
                (
                    f'❌ Неизвестный профиль: {context.args[0]}\n'
                    f'Доступно: {available}'
                ),
                reply_markup=self.get_main_keyboard(profile_id),
            )
        return None

    def _runtime(self, profile_id: str):
        return storage.get_runtime_config(
            config,
            profile_id=profile_id,
            default_urls=self.profile_default_urls.get(profile_id, []),
        )

    def _state(self, profile_id: str):
        return storage.get_state(profile_id=profile_id)

    def _api_client(self, profile_id: str):
        return self.api_clients.get(profile_id)

    def _product_id(self, profile_id: str) -> int:
        return int(self.profile_products.get(profile_id, 0))

    def _runtime_profile_id_for_product(
        self,
        profile_id: str,
        product_id: int,
    ) -> str:
        normalized_product_id = int(product_id or 0)
        if normalized_product_id <= 0:
            return profile_id
        return f'{profile_id}:{normalized_product_id}'

    def _runtime_for_product(
        self,
        profile_id: str,
        product_id: int,
    ):
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        return self._runtime(runtime_profile_id)

    def _state_for_product(
        self,
        profile_id: str,
        product_id: int,
    ) -> dict:
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        return self._state(runtime_profile_id)

    def _tracked_products(self, profile_id: str, runtime=None) -> list[dict]:
        current_runtime = runtime or self._runtime(profile_id)
        tracked = storage.list_tracked_products(
            profile_id=profile_id,
            default_product_id=self._product_id(profile_id),
            default_urls=getattr(current_runtime, 'COMPETITOR_URLS', []),
        )
        tracked_ids: list[int] = []
        for item in tracked:
            product_id = int(item.get('product_id') or 0)
            if product_id > 0 and product_id not in tracked_ids:
                tracked_ids.append(product_id)
        if tracked_ids and self._product_id(profile_id) not in tracked_ids:
            self.profile_products[profile_id] = tracked_ids[0]
        return tracked

    def _tracked_product_ids(self, profile_id: str, runtime=None) -> list[int]:
        tracked_products = self._tracked_products(profile_id, runtime=runtime)
        product_ids: list[int] = []
        for item in tracked_products:
            product_id = int(item.get('product_id') or 0)
            if product_id <= 0 or product_id in product_ids:
                continue
            product_ids.append(product_id)
        return product_ids

    def _active_product_slot(self, profile_id: str, runtime=None) -> tuple[int, int]:
        product_ids = self._tracked_product_ids(profile_id, runtime=runtime)
        if not product_ids:
            return (0, 0)
        active_product_id = self._product_id(profile_id)
        if active_product_id not in product_ids:
            return (1, len(product_ids))
        return (product_ids.index(active_product_id) + 1, len(product_ids))

    def _format_tracked_products(self, profile_id: str, runtime=None) -> list[str]:
        tracked_products = self._tracked_products(profile_id, runtime=runtime)
        if not tracked_products:
            return ['нет']
        lines = []
        active_product_id = self._product_id(profile_id)
        for item in tracked_products:
            product_id = int(item.get('product_id') or 0)
            competitor_urls = item.get('competitor_urls', []) or []
            markers = []
            if product_id == active_product_id:
                markers.append('активный')
            marker = f" ({', '.join(markers)})" if markers else ''
            lines.append(
                f'{self._product_label(profile_id, product_id)}{marker}: '
                f'{len(competitor_urls)} URL'
            )
        return lines

    def _format_tracking_pairs(self, profile_id: str, runtime=None) -> list[str]:
        tracked_products = self._tracked_products(profile_id, runtime=runtime)
        if not tracked_products:
            return ['нет']
        lines: list[str] = []
        for item in tracked_products:
            product_id = int(item.get('product_id') or 0)
            urls = item.get('competitor_urls', []) or []
            if not urls:
                lines.append(
                    f'{self._product_label(profile_id, product_id)} ↔ '
                    '(конкурент не задан)'
                )
                continue
            for url in urls:
                lines.append(f'{self._product_label(profile_id, product_id)} ↔ {url}')
        return lines

    def _fmt_price(self, value) -> str:
        if value is None:
            return 'N/A'
        try:
            return f'{float(value):.4f}'
        except Exception:
            return str(value)

    def _fmt_iso_datetime(self, value: Optional[str]) -> str:
        raw = (value or '').strip()
        if not raw:
            return 'Никогда'
        try:
            normalized = raw.replace('Z', '+00:00')
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return raw

    def _product_alias_key(self, product_id: int) -> str:
        return f'PRODUCT_ALIAS:{int(product_id or 0)}'

    def _product_auto_name_key(self, product_id: int) -> str:
        return f'PRODUCT_AUTO_NAME:{int(product_id or 0)}'

    def _set_product_alias(
        self,
        profile_id: str,
        product_id: int,
        alias: str,
        *,
        user_id: int,
        source: str,
    ) -> None:
        normalized_alias = re.sub(r'\s+', ' ', str(alias or '')).strip()
        key = self._product_alias_key(product_id)
        if normalized_alias:
            storage.set_runtime_setting(
                key,
                normalized_alias,
                user_id=user_id,
                source=source,
                profile_id=profile_id,
            )
            return
        storage.delete_runtime_setting(
            key,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def _cleanup_removed_product_runtime(
        self,
        *,
        profile_id: str,
        product_id: int,
        user_id: int,
        source: str,
    ) -> None:
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        storage.delete_runtime_setting(
            'competitor_urls',
            user_id=user_id,
            source=source,
            profile_id=runtime_profile_id,
        )
        storage.purge_product_runtime_data(
            profile_id=profile_id,
            product_id=product_id,
        )
        storage.delete_runtime_setting(
            self._product_alias_key(product_id),
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )
        storage.delete_runtime_setting(
            self._product_auto_name_key(product_id),
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def _remove_product_with_cleanup(
        self,
        *,
        profile_id: str,
        product_id: int,
        user_id: int,
        source: str,
    ) -> bool:
        removed = storage.remove_tracked_product(
            profile_id=profile_id,
            product_id=product_id,
        )
        if not removed:
            return False
        self._cleanup_removed_product_runtime(
            profile_id=profile_id,
            product_id=product_id,
            user_id=user_id,
            source=source,
        )
        return True

    def _clear_products_with_cleanup(
        self,
        *,
        profile_id: str,
        user_id: int,
        source: str,
        fallback_ids: Optional[list[int]] = None,
    ) -> list[int]:
        removed_ids = storage.clear_tracked_products(profile_id=profile_id)
        cleanup_ids = sorted({
            int(pid)
            for pid in (removed_ids or fallback_ids or [])
            if int(pid or 0) > 0
        })
        for product_id in cleanup_ids:
            self._cleanup_removed_product_runtime(
                profile_id=profile_id,
                product_id=product_id,
                user_id=user_id,
                source=source,
            )
        return cleanup_ids

    def _get_product_alias(self, profile_id: str, product_id: int) -> str:
        key = self._product_alias_key(product_id)
        try:
            raw = storage.get_runtime_setting(
                key,
                profile_id=profile_id,
                inherit_parent=False,
            )
        except TypeError:
            raw = storage.get_runtime_setting(
                key,
                profile_id=profile_id,
            )
        return re.sub(r'\s+', ' ', str(raw or '')).strip()

    def _get_product_auto_name(self, profile_id: str, product_id: int) -> str:
        key = self._product_auto_name_key(product_id)
        try:
            raw = storage.get_runtime_setting(
                key,
                profile_id=profile_id,
                inherit_parent=False,
            )
        except TypeError:
            raw = storage.get_runtime_setting(
                key,
                profile_id=profile_id,
            )
        return re.sub(r'\s+', ' ', str(raw or '')).strip()

    def _truncate_product_name(self, name: str, max_len: int = 42) -> str:
        clean = re.sub(r'\s+', ' ', str(name or '')).strip()
        if len(clean) <= max_len:
            return clean
        return clean[: max_len - 1].rstrip() + '…'

    def _product_name(self, profile_id: str, product_id: int) -> str:
        alias = self._get_product_alias(profile_id, product_id)
        if alias:
            return alias
        return self._get_product_auto_name(profile_id, product_id)

    def _product_label(self, profile_id: str, product_id: int) -> str:
        normalized_product_id = int(product_id or 0)
        if normalized_product_id <= 0:
            return 'N/A'
        name = self._product_name(profile_id, normalized_product_id)
        if not name:
            return str(normalized_product_id)
        return (
            f'{normalized_product_id} '
            f'«{self._truncate_product_name(name)}»'
        )

    def _extract_product_name_from_info(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ('name', 'title', 'product_name'):
                value = re.sub(r'\s+', ' ', str(payload.get(key) or '')).strip()
                if value and not value.isdigit():
                    return value
            for nested in payload.values():
                resolved = self._extract_product_name_from_info(nested)
                if resolved:
                    return resolved
        elif isinstance(payload, list):
            for item in payload:
                resolved = self._extract_product_name_from_info(item)
                if resolved:
                    return resolved
        return ''

    async def _ensure_product_auto_name(
        self,
        profile_id: str,
        product_id: int,
    ) -> str:
        normalized_product_id = int(product_id or 0)
        if normalized_product_id <= 0:
            return ''
        if self._get_product_auto_name(profile_id, normalized_product_id):
            return self._get_product_auto_name(profile_id, normalized_product_id)

        client = self._api_client(profile_id)
        if not client:
            return ''

        resolved_name = ''
        get_product = getattr(client, 'get_product', None)
        if callable(get_product):
            try:
                product_obj = await asyncio.to_thread(
                    get_product,
                    normalized_product_id,
                )
                resolved_name = re.sub(
                    r'\s+',
                    ' ',
                    str(getattr(product_obj, 'name', '') or ''),
                ).strip()
            except Exception as e:
                logger.debug(
                    '[%s] Не удалось получить имя товара через get_product(%s): %s',
                    self._profile_name(profile_id),
                    normalized_product_id,
                    e,
                )

        if not resolved_name:
            get_product_info = getattr(client, 'get_product_info', None)
            if callable(get_product_info):
                try:
                    payload = await asyncio.to_thread(
                        get_product_info,
                        normalized_product_id,
                    )
                    resolved_name = self._extract_product_name_from_info(payload)
                except Exception as e:
                    logger.debug(
                        '[%s] Не удалось получить имя товара через '
                        'get_product_info(%s): %s',
                        self._profile_name(profile_id),
                        normalized_product_id,
                        e,
                    )

        if resolved_name:
            storage.set_runtime_setting(
                self._product_auto_name_key(normalized_product_id),
                resolved_name,
                source='telegram_product_name_cache',
                profile_id=profile_id,
            )
        return resolved_name

    def _chat_profile_prefix(self, profile_id: str) -> Optional[str]:
        return _CHAT_PROFILE_PREFIX.get((profile_id or '').strip().lower())

    def _chat_autoreply_supported(self, profile_id: str) -> bool:
        if self._chat_profile_prefix(profile_id) is None:
            return False
        client = self._api_client(profile_id)
        if not client:
            return False
        required = (
            'list_chats',
            'send_chat_message',
            'get_order_info',
            'get_product_info',
        )
        return all(hasattr(client, name) for name in required)

    def _chat_cfg(self, profile_id: str, suffix: str, default):
        prefix = self._chat_profile_prefix(profile_id)
        if not prefix:
            return default
        key = f'{prefix}_CHAT_AUTOREPLY_{suffix}'
        return getattr(config, key, default)

    def _chat_autoreply_enabled(self, profile_id: str) -> bool:
        runtime_raw = storage.get_runtime_setting(
            'CHAT_AUTOREPLY_ENABLED',
            profile_id=profile_id,
        )
        if runtime_raw is not None:
            normalized = str(runtime_raw).strip().lower()
            return normalized in ('1', 'true', 'yes', 'on')
        return bool(self._chat_cfg(profile_id, 'ENABLED', False))

    def _chat_autoreply_only_empty_chat(self, profile_id: str) -> bool:
        runtime_raw = storage.get_runtime_setting(
            'CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
            profile_id=profile_id,
        )
        if runtime_raw is not None:
            normalized = str(runtime_raw).strip().lower()
            return normalized in ('1', 'true', 'yes', 'on')
        return bool(self._chat_cfg(profile_id, 'ONLY_EMPTY_CHAT', True))

    def _chat_autoreply_smart_non_empty(self, profile_id: str) -> bool:
        runtime_raw = storage.get_runtime_setting(
            'CHAT_AUTOREPLY_SMART_NON_EMPTY',
            profile_id=profile_id,
        )
        if runtime_raw is not None:
            normalized = str(runtime_raw).strip().lower()
            return normalized in ('1', 'true', 'yes', 'on')
        return bool(self._chat_cfg(profile_id, 'SMART_NON_EMPTY', False))

    def _chat_autoreply_require_rules(self, profile_id: str) -> bool:
        runtime_raw = storage.get_runtime_setting(
            'CHAT_AUTOREPLY_REQUIRE_RULES',
            profile_id=profile_id,
        )
        if runtime_raw is not None:
            normalized = str(runtime_raw).strip().lower()
            return normalized in ('1', 'true', 'yes', 'on')
        return bool(self._chat_cfg(profile_id, 'REQUIRE_RULES', False))

    def _chat_policy_label(self, value: str) -> str:
        normalized = str(value or '').strip().upper()
        return _CHAT_POLICY_LABELS_RU.get(normalized, _CHAT_POLICY_LABELS_RU['ON_ORDER'])

    def _chat_autoreply_policy(
        self,
        profile_id: str,
        *,
        product_id: Optional[int] = None,
    ) -> str:
        pid = int(product_id or self._product_id(profile_id) or 0)
        runtime_raw = None
        if pid > 0:
            runtime_raw = storage.get_runtime_setting(
                f'CHAT_AUTOREPLY_POLICY:{pid}',
                profile_id=profile_id,
            )
        if runtime_raw is None:
            runtime_raw = storage.get_runtime_setting(
                'CHAT_AUTOREPLY_POLICY',
                profile_id=profile_id,
            )
        if runtime_raw is None:
            runtime_raw = self._chat_cfg(profile_id, 'POLICY', 'ON_ORDER')
        normalized = str(runtime_raw or '').strip().upper()
        aliases = {
            'NEW_ORDER': 'ON_ORDER',
            'ORDER': 'ON_ORDER',
            'FIRST_MESSAGE': 'FIRST_BUYER_MESSAGE',
            'MESSAGE': 'FIRST_BUYER_MESSAGE',
            'CODE': 'CODE_ONLY',
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in _CHAT_POLICY_SEQUENCE:
            return 'ON_ORDER'
        return normalized

    def _chat_autoreply_meta(self, profile_id: str) -> Optional[dict]:
        if not self._chat_autoreply_supported(profile_id):
            return None
        active_product_id = self._product_id(profile_id)
        enabled = self._chat_autoreply_enabled(profile_id)
        dedupe = bool(
            self._chat_cfg(profile_id, 'DEDUPE_BY_MESSAGES', True)
        )
        lookback = int(
            self._chat_cfg(profile_id, 'LOOKBACK_MESSAGES', 30)
        )
        interval_seconds = int(
            self._chat_cfg(profile_id, 'INTERVAL_SECONDS', 30)
        )
        product_ids = self._chat_cfg(profile_id, 'PRODUCT_IDS', []) or []
        normalized_products = []
        for value in product_ids:
            try:
                listed_product_id = int(float(value))
            except (TypeError, ValueError):
                continue
            if listed_product_id > 0:
                normalized_products.append(str(listed_product_id))
        products_text = ', '.join(normalized_products)
        if not products_text:
            products_text = 'по активному товару'

        raw_sent_count = storage.get_runtime_setting(
            chat_keys.KEY_SENT_COUNT,
            profile_id=profile_id,
        )
        raw_duplicate_count = storage.get_runtime_setting(
            chat_keys.KEY_DUPLICATE_COUNT,
            profile_id=profile_id,
        )
        sent_count = 0
        if raw_sent_count is not None:
            try:
                sent_count = int(float(raw_sent_count))
            except (TypeError, ValueError):
                sent_count = 0
        duplicate_count = 0
        if raw_duplicate_count is not None:
            try:
                duplicate_count = int(float(raw_duplicate_count))
            except (TypeError, ValueError):
                duplicate_count = 0

        last_run = storage.get_runtime_setting(
            chat_keys.KEY_LAST_RUN_AT,
            profile_id=profile_id,
        )
        last_sent = storage.get_runtime_setting(
            chat_keys.KEY_LAST_SENT_AT,
            profile_id=profile_id,
        )
        last_cleanup = storage.get_runtime_setting(
            chat_keys.KEY_LAST_CLEANUP_AT,
            profile_id=profile_id,
        )
        last_error = storage.get_runtime_setting(
            chat_keys.KEY_LAST_ERROR,
            profile_id=profile_id,
        )

        return {
            'enabled': enabled,
            'only_empty_chat': self._chat_autoreply_only_empty_chat(profile_id),
            'smart_non_empty': self._chat_autoreply_smart_non_empty(profile_id),
            'require_rules': self._chat_autoreply_require_rules(profile_id),
            'policy': self._chat_autoreply_policy(
                profile_id,
                product_id=active_product_id,
            ),
            'dedupe': dedupe,
            'lookback': lookback,
            'interval_seconds': interval_seconds,
            'products': products_text,
            'sent_count': sent_count,
            'duplicate_count': duplicate_count,
            'last_run': self._fmt_iso_datetime(last_run),
            'last_sent': self._fmt_iso_datetime(last_sent),
            'last_cleanup': self._fmt_iso_datetime(last_cleanup),
            'last_error': (last_error or '').strip() or 'N/A',
        }

    def _chat_rules_storage_key(self, product_id: int) -> str:
        return chat_keys.rules_key(product_id)

    def _chat_rules_load(
        self,
        *,
        profile_id: str,
        product_id: int,
    ) -> dict[str, dict[str, Any]]:
        if int(product_id or 0) <= 0:
            return {}
        raw = storage.get_runtime_setting(
            self._chat_rules_storage_key(product_id),
            profile_id=profile_id,
        )
        payload = (raw or '').strip()
        if not payload:
            return {}
        try:
            data = json.loads(payload)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        rules = data.get('rules')
        if not isinstance(rules, dict):
            return {}
        normalized: dict[str, dict[str, Any]] = {}
        for key, value in rules.items():
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
        return normalized

    def _chat_rules_save(
        self,
        *,
        profile_id: str,
        product_id: int,
        rules: dict[str, dict[str, Any]],
        user_id: int,
    ):
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
        if normalized:
            payload = json.dumps(
                {'version': 1, 'rules': normalized},
                ensure_ascii=False,
            )
        else:
            payload = ''
        storage.set_runtime_setting(
            self._chat_rules_storage_key(product_id),
            payload,
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )

    def _rule_clean_text(self, value: Any) -> str:
        text = str(value or '').strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _rule_choice_text(self, value: Any) -> str:
        if value is None:
            return ''
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            as_float = float(value)
            return str(int(as_float)) if as_float.is_integer() else str(as_float)
        if isinstance(value, dict):
            for key in ('text', 'label', 'name', 'title', 'value'):
                if key in value:
                    inner = self._rule_choice_text(value.get(key))
                    if inner:
                        return inner
            return ''
        return self._rule_clean_text(value)

    def _iter_product_option_dicts(self, payload: Any):
        if isinstance(payload, dict):
            options_value = payload.get('options')
            if isinstance(options_value, list):
                for option in options_value:
                    if isinstance(option, dict):
                        yield option
            for nested in payload.values():
                yield from self._iter_product_option_dicts(nested)
            return
        if isinstance(payload, list):
            for item in payload:
                yield from self._iter_product_option_dicts(item)

    def _option_name_text(self, option: dict[str, Any]) -> str:
        # В GGSEL поле `name` часто содержит numeric id опции.
        # Для UX правил предпочитаем человекочитаемые label/title/question.
        for key in ('label', 'title', 'question', 'name'):
            value = self._rule_clean_text(option.get(key))
            if not value:
                continue
            if key == 'name' and value.isdigit():
                continue
            return value
        # Если доступен только numeric name/id — оставляем как fallback.
        return self._rule_clean_text(option.get('name'))

    def _rule_option_id(self, option: dict[str, Any]) -> int:
        for key in ('id', 'name'):
            if key not in option:
                continue
            parsed = chat_keys.parse_numeric_id(option.get(key))
            if parsed > 0:
                return parsed
        return 0

    def _rule_variant_id(self, variant: Any) -> int:
        if not isinstance(variant, dict):
            return 0
        for key in ('id', 'value'):
            if key not in variant:
                continue
            parsed = chat_keys.parse_numeric_id(variant.get(key))
            if parsed > 0:
                return parsed
        return 0

    def _is_friend_rule_candidate(
        self,
        option_name: str,
        variant_text: str,
    ) -> bool:
        haystack = f'{option_name} {variant_text}'.lower()
        return any(token in haystack for token in _FRIEND_RULE_KEYWORDS)

    def _build_chat_rules_items(
        self,
        product_info: dict[str, Any],
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for option in self._iter_product_option_dicts(product_info):
            option_name = self._option_name_text(option)
            option_id = self._rule_option_id(option)
            variants = (
                option.get('variants')
                or option.get('values')
                or option.get('options')
            )
            if not option_name or not isinstance(variants, list):
                continue
            for raw_variant in variants:
                variant_text = self._rule_choice_text(raw_variant)
                if not variant_text:
                    continue
                variant_id = self._rule_variant_id(raw_variant)
                key = chat_keys.option_variant_rule_key(option_id, variant_id)
                legacy_key = chat_keys.option_rule_key(option_name, variant_text)
                if not key:
                    key = legacy_key
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        'key': key,
                        'legacy_key': legacy_key,
                        'option_id': str(option_id) if option_id > 0 else '',
                        'variant_id': str(variant_id) if variant_id > 0 else '',
                        'option': option_name,
                        'value': variant_text,
                        'label': f'{option_name} -> {variant_text}',
                    }
                )

        if not items:
            return []

        friend_items = [
            item for item in items
            if self._is_friend_rule_candidate(
                item.get('option', ''),
                item.get('value', ''),
            )
        ]
        return friend_items or items

    def _chat_rules_rebind_legacy_keys(
        self,
        *,
        rules: dict[str, dict[str, Any]],
        items: list[dict[str, str]],
    ) -> tuple[dict[str, dict[str, Any]], bool]:
        """
        Миграция text-key -> id-key для стабильного matching по option/variant id.
        """
        if not isinstance(rules, dict) or not isinstance(items, list):
            return rules, False
        migrated = dict(rules)
        changed = False
        for item in items:
            new_key = str(item.get('key') or '').strip().lower()
            legacy_key = str(item.get('legacy_key') or '').strip().lower()
            if not new_key or not legacy_key or new_key == legacy_key:
                continue
            if legacy_key not in migrated or new_key in migrated:
                continue
            migrated[new_key] = dict(migrated.get(legacy_key) or {})
            del migrated[legacy_key]
            changed = True
        return migrated, changed

    def _format_chat_rules_overview(
        self,
        *,
        profile_id: str,
        product_id: int,
        items: list[dict[str, str]],
        rules: dict[str, dict[str, Any]],
    ) -> str:
        lines = [
            '📝 Правила авто-инструкций',
            '',
            f'Профиль: {self._profile_name(profile_id)}',
            f'Товар: {product_id}',
            '',
            'Нажимай кнопки под этим сообщением, чтобы включать/выключать '
            'варианты.',
            'Если включено хотя бы одно правило, отправка идёт только по '
            'включённым вариантам.',
            '',
        ]
        if not items:
            lines.append('❌ В товаре не найдены параметры с вариантами.')
            return '\n'.join(lines)

        enabled_count = 0
        custom_count = 0
        for idx, item in enumerate(items, start=1):
            entry = rules.get(item['key']) or {}
            enabled = bool(entry.get('enabled', False))
            has_custom = bool((entry.get('text') or '').strip())
            if enabled:
                enabled_count += 1
            if has_custom:
                custom_count += 1
            status = '✅' if enabled else '🚫'
            custom = '✍️' if has_custom else '—'
            lines.append(
                f'{idx}. {status} {item["label"]} | текст: {custom}'
            )
            if has_custom:
                preview = self._rule_clean_text(entry.get('text'))
                if len(preview) > 120:
                    preview = preview[:117].rstrip() + '...'
                lines.append(f'   ↳ {preview}')
        lines.extend(
            [
                '',
                f'Включено: {enabled_count}/{len(items)}, '
                f'кастомных текстов: {custom_count}',
                '',
                'Кнопки под сообщением: вкл/выкл, сброс, готово.',
                'Кастомный текст (опционально): text <номер> <текст>',
                'Очистить кастомный текст: clear <номер>',
                'Если текст пустой, берётся инструкция из товара.',
                'Закрыть редактор: done',
            ]
        )
        return '\n'.join(lines)

    def _trim_rule_button_text(
        self,
        value: str,
        *,
        limit: int = 34,
    ) -> str:
        text = self._rule_clean_text(value)
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + '...'

    def _chat_rules_inline_keyboard(
        self,
        *,
        items: list[dict[str, str]],
        rules: dict[str, dict[str, Any]],
    ) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        for idx, item in enumerate(items, start=1):
            entry = rules.get(item['key']) or {}
            enabled = bool(entry.get('enabled', False))
            status = '✅' if enabled else '🚫'
            label = self._trim_rule_button_text(item.get('value') or item.get('label') or '')
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f'{idx}. {status} {label}',
                        callback_data=f'cr:t:{idx}',
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton('🔄 Обновить', callback_data='cr:r'),
                InlineKeyboardButton('♻️ Сброс', callback_data='cr:x'),
                InlineKeyboardButton('✅ Готово', callback_data='cr:d'),
            ]
        )
        return InlineKeyboardMarkup(rows)

    def _products_inline_keyboard(
        self,
        profile_id: str,
        *,
        runtime: Optional[Any] = None,
        confirm: Optional[str] = None,
    ) -> InlineKeyboardMarkup:
        tracked = self._tracked_products(profile_id, runtime=runtime)
        active_product_id = self._product_id(profile_id)
        rows: list[list[InlineKeyboardButton]] = []

        for item in tracked:
            product_id = int(item.get('product_id') or 0)
            if product_id <= 0:
                continue
            prefix = '✅' if product_id == active_product_id else '📦'
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f'{prefix} {self._product_label(profile_id, product_id)}',
                        callback_data=f'pm:s:{product_id}',
                    )
                ]
            )

        rows.append(
            [
                InlineKeyboardButton('➕ Товар', callback_data='pm:a'),
                InlineKeyboardButton('🔗 Конкурент', callback_data='pm:u'),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton('✏️ Переименовать', callback_data='pm:n'),
                InlineKeyboardButton('♻️ Сбросить имя', callback_data='pm:c'),
            ]
        )

        if confirm == 'active':
            rows.append(
                [
                    InlineKeyboardButton('✅ Да, удалить', callback_data='pm:y:active'),
                    InlineKeyboardButton('↩️ Отмена', callback_data='pm:r'),
                ]
            )
        elif confirm == 'all':
            rows.append(
                [
                    InlineKeyboardButton('✅ Да, удалить всё', callback_data='pm:y:all'),
                    InlineKeyboardButton('↩️ Отмена', callback_data='pm:r'),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton('🗑 Удалить активный', callback_data='pm:rd'),
                    InlineKeyboardButton('🧹 Удалить все', callback_data='pm:ra'),
                ]
            )

        rows.append(
            [
                InlineKeyboardButton('🔄 Обновить', callback_data='pm:r'),
                InlineKeyboardButton('✅ Готово', callback_data='pm:d'),
            ]
        )
        return InlineKeyboardMarkup(rows)

    def _format_products_management_text(
        self,
        profile_id: str,
        *,
        runtime: Optional[Any] = None,
        confirm: Optional[str] = None,
    ) -> str:
        tracked_lines = self._format_tracked_products(profile_id, runtime=runtime)
        active_product_id = self._product_id(profile_id)
        active_label = (
            self._product_label(profile_id, active_product_id)
            if active_product_id
            else 'не выбран'
        )
        lines = [
            '📦 Управление товарами',
            '',
            f'Площадка: {self._profile_name(profile_id)}',
            f'Активный товар: {active_label}',
            '',
            'Товары в профиле:',
            *tracked_lines,
            '',
            'Кнопки ниже:',
            '- выбрать активный товар',
            '- добавить товар',
            '- привязать URL конкурента к активному товару',
            '- переименовать товар',
            '- удалить активный товар или весь список',
        ]
        if confirm == 'active':
            lines.extend(
                [
                    '',
                    '⚠️ Подтверди удаление активного товара кнопкой ниже.',
                ]
            )
        elif confirm == 'all':
            lines.extend(
                [
                    '',
                    '⚠️ Подтверди полную очистку списка товаров кнопкой ниже.',
                ]
            )
        return '\n'.join(lines)

    # ================================
    # Keyboards
    # ================================
    def _profile_button(self, profile_id: str) -> str:
        return f'🧩 {self._profile_name(profile_id)}'

    def get_main_keyboard(self, profile_id: Optional[str] = None):
        return ReplyKeyboardMarkup(
            [
                [BTN_STATUS, BTN_PRODUCTS],
                [BTN_PRODUCT_PREV, BTN_PRODUCT_NEXT],
                [BTN_PROFILE, BTN_SETTINGS],
            ],
            resize_keyboard=True,
        )

    def get_settings_keyboard(
        self,
        profile_id: Optional[str] = None,
    ):
        profile = profile_id or self.default_profile
        state = self._state_for_product(profile, self._product_id(profile))
        auto_enabled = bool(state.get('auto_mode', True))
        auto_toggle_button = BTN_AUTO_OFF if auto_enabled else BTN_AUTO_ON
        rows = [
            [auto_toggle_button],
            [BTN_PRICE, BTN_MODE],
            [BTN_PRICE_GUARD],
            [BTN_PRODUCT_REMOVE],
        ]
        if self._chat_autoreply_supported(profile):
            chat_enabled = self._chat_autoreply_enabled(profile)
            chat_toggle_button = (
                BTN_CHAT_AUTOREPLY_OFF
                if chat_enabled else BTN_CHAT_AUTOREPLY_ON
            )
            empty_chat_only_enabled = self._chat_autoreply_only_empty_chat(
                profile
            )
            empty_chat_button = (
                BTN_CHAT_EMPTY_ONLY_OFF
                if empty_chat_only_enabled
                else BTN_CHAT_EMPTY_ONLY_ON
            )
            smart_non_empty_enabled = self._chat_autoreply_smart_non_empty(
                profile
            )
            smart_non_empty_button = (
                BTN_CHAT_SMART_NON_EMPTY_OFF
                if smart_non_empty_enabled
                else BTN_CHAT_SMART_NON_EMPTY_ON
            )
            rows.append([chat_toggle_button, empty_chat_button])
            rows.append([smart_non_empty_button])
            rows.append([BTN_CHAT_POLICY, BTN_CHAT_RULES])
        rows.append([BTN_BACK])
        return ReplyKeyboardMarkup(rows, resize_keyboard=True)

    def _price_guard_inline_keyboard(
        self,
        *,
        profile_id: str,
    ) -> InlineKeyboardMarkup:
        product_id = self._product_id(profile_id)
        runtime = self._runtime_for_product(profile_id, product_id)
        round_step = getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
        rebound_enabled = bool(
            getattr(runtime, 'REBOUND_TO_DESIRED_ON_MIN', False)
        )
        rebound_label = '🔁 Отскок: ВКЛ' if rebound_enabled else '🔁 Отскок: ВЫКЛ'
        rounding_label = f'🔘 Округление: {self._rounding_label(round_step)}'
        rows = [
            [
                InlineKeyboardButton(BTN_MIN, callback_data='pc:min'),
                InlineKeyboardButton(BTN_MAX, callback_data='pc:max'),
            ],
            [
                InlineKeyboardButton(BTN_UNDERCUT, callback_data='pc:under'),
                InlineKeyboardButton(BTN_RAISE, callback_data='pc:raise'),
            ],
            [
                InlineKeyboardButton(
                    rounding_label,
                    callback_data='pc:round',
                ),
            ],
            [
                InlineKeyboardButton(
                    rebound_label,
                    callback_data='pc:rebound',
                ),
            ],
            [
                InlineKeyboardButton('✅ Готово', callback_data='pc:done'),
            ],
        ]
        return InlineKeyboardMarkup(rows)

    def _format_price_guard_text(self, profile_id: str) -> str:
        product_id = self._product_id(profile_id)
        runtime = self._runtime_for_product(profile_id, product_id)
        min_price = float(getattr(runtime, 'MIN_PRICE', 0.0) or 0.0)
        max_price = float(getattr(runtime, 'MAX_PRICE', 0.0) or 0.0)
        undercut = float(getattr(runtime, 'UNDERCUT_VALUE', 0.0051) or 0.0051)
        raise_value = float(getattr(runtime, 'RAISE_VALUE', 0.0049) or 0.0049)
        round_step = getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
        rebound_enabled = bool(
            getattr(runtime, 'REBOUND_TO_DESIRED_ON_MIN', False)
        )
        return '\n'.join(
            [
                '🧮 Лимиты и шаги',
                '',
                f'Профиль: {self._profile_name(profile_id)}',
                f'Товар: {product_id}',
                '',
                f'📉 Мин: {min_price:.4f}',
                f'📈 Макс: {max_price:.4f}',
                f'↘️ Шаг-: {undercut:.4f}',
                f'↗️ Шаг+: {raise_value:.4f}',
                f'🔘 Округление: {self._rounding_label(round_step)}',
                (
                    f'🔁 Отскок к рекомендуемой: '
                    f'{"ВКЛ" if rebound_enabled else "ВЫКЛ"}'
                ),
                '',
                'Изменения применяются только к активному товару.',
            ]
        )

    async def open_price_guard_panel(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        await update.message.reply_text(
            self._format_price_guard_text(profile_id),
            reply_markup=self._price_guard_inline_keyboard(
                profile_id=profile_id,
            ),
        )

    def get_profile_keyboard(self):
        profile_rows = [[self._profile_button(pid)] for pid in self.available_profiles]
        profile_rows.append([BTN_BACK])
        return ReplyKeyboardMarkup(profile_rows, resize_keyboard=True)

    # ================================
    # Telegram setup
    # ================================
    @property
    def app(self):
        if self._app is None:
            self._app = Application.builder().token(self.bot_token).build()
            self._setup_handlers()
        return self._app

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler('start', self.cmd_start))
        self.app.add_handler(CommandHandler('status', self.cmd_status))
        self.app.add_handler(CommandHandler('diag', self.cmd_diag))
        self.app.add_handler(CommandHandler('smoke', self.cmd_smoke))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.app.add_error_handler(self.handle_app_error)

    async def handle_app_error(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        err = getattr(context, 'error', None)
        if isinstance(err, TimedOut):
            logger.warning('Telegram timeout: %s', err)
            return
        if isinstance(err, NetworkError):
            logger.warning('Telegram network error: %s', err)
            return
        logger.error('Unhandled telegram exception: %s', err, exc_info=err)

    def _check_access(self, user_id: int) -> bool:
        if user_id not in self.admin_ids:
            logger.warning('Доступ запрещён для user_id=%s', user_id)
            return False
        return True

    # ================================
    # Commands
    # ================================
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.message:
            return
        if not self._check_access(update.effective_user.id):
            await update.message.reply_text(
                '❌ Нет доступа',
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        chat_id = update.effective_chat.id if update.effective_chat else None
        profile_id = self._active_profile(chat_id)
        await update.message.reply_text(
            (
                '👋 Бот запущен\n'
                f'Профиль: {self._profile_name(profile_id)}\n'
                'Выбери действие:'
            ),
            reply_markup=self.get_main_keyboard(profile_id),
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return
        if not self._check_access(update.effective_user.id):
            if update.message:
                await update.message.reply_text(
                    '❌ Нет доступа',
                    reply_markup=ReplyKeyboardRemove(),
                )
            return
        chat_id = update.effective_chat.id
        profile_id = await self._resolve_command_profile(
            chat_id=chat_id,
            update=update,
            context=context,
        )
        if profile_id is None:
            return
        await self.send_status(chat_id, update, profile_id=profile_id)

    async def cmd_diag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return
        if not self._check_access(update.effective_user.id):
            if update.message:
                await update.message.reply_text(
                    '❌ Нет доступа',
                    reply_markup=ReplyKeyboardRemove(),
                )
            return
        chat_id = update.effective_chat.id
        profile_id = await self._resolve_command_profile(
            chat_id=chat_id,
            update=update,
            context=context,
        )
        if profile_id is None:
            return
        await self.send_diagnostics(chat_id, update, profile_id=profile_id)

    async def cmd_smoke(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat or not update.message:
            return
        if not self._check_access(update.effective_user.id):
            await update.message.reply_text(
                '❌ Нет доступа',
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        chat_id = update.effective_chat.id
        profile_id = await self._resolve_command_profile(
            chat_id=chat_id,
            update=update,
            context=context,
        )
        if profile_id is None:
            return
        profile_name = self._profile_name(profile_id)
        client = self._api_client(profile_id)
        product_id = self._product_id(profile_id)

        if not client or not product_id:
            await update.message.reply_text(
                (
                    '❌ Smoke недоступен: не настроены '
                    'API-клиент или product_id для профиля'
                ),
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        await update.message.reply_text(
            f'🧪 Запуск smoke API для профиля {profile_name}...',
            reply_markup=self.get_main_keyboard(profile_id),
        )

        result = await asyncio.to_thread(
            run_profile_smoke,
            client,
            int(product_id),
            mutate=False,
            verify_read=True,
            write_probe=False,
        )
        lines = [
            '🧪 Smoke API',
            '',
            f'Профиль: {profile_name}',
            f'API: {"OK" if result.api_access else "FAIL"}',
            f'Read: {"OK" if result.product_read_ok else "FAIL"}',
            f'Write probe: {"OK" if result.write_probe_ok else "FAIL"}',
            f'Current price: {self._fmt_price(result.current_price)}',
            f'Probe price: {self._fmt_price(result.probe_price)}',
            f'Verify price: {self._fmt_price(result.verify_price)}',
        ]
        token_perms_ok = getattr(result, 'token_perms_ok', None)
        token_perms_desc = getattr(result, 'token_perms_desc', None)
        if token_perms_ok is not None or token_perms_desc:
            lines.append(
                'Token perms: '
                f'{"OK" if token_perms_ok else "FAIL"} '
                f'({token_perms_desc or "N/A"})'
            )
        token_refresh_ok = getattr(result, 'token_refresh_ok', None)
        token_refresh_desc = getattr(result, 'token_refresh_desc', None)
        if token_refresh_ok is not None or token_refresh_desc:
            lines.append(
                'Token refresh: '
                f'{"OK" if token_refresh_ok else "FAIL"} '
                f'({token_refresh_desc or "N/A"})'
            )
        if result.error:
            lines.append(f'Error: {result.error}')
        await update.message.reply_text(
            '\n'.join(lines),
            reply_markup=self.get_main_keyboard(profile_id),
        )

    # ================================
    # Message handler
    # ================================
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat or not update.message:
            return
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        raw_text = update.message.text or ''
        text = self._normalize_text(raw_text)
        profile_id = self._active_profile(chat_id)

        logger.info('Получено: %r -> %r', raw_text, text)
        if not self._check_access(user_id):
            await update.message.reply_text(
                '❌ Нет доступа',
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        # Главное меню
        if text == BTN_STATUS:
            await self.send_status(chat_id, update)
            return
        if text == BTN_AUTO_ON:
            await self.set_auto_enabled(update, enabled=True)
            return
        if text == BTN_AUTO_OFF:
            await self.set_auto_enabled(update, enabled=False)
            return
        if text == BTN_PROFILE:
            await update.message.reply_text(
                'Выбери профиль:',
                reply_markup=self.get_profile_keyboard(),
            )
            return
        if text == BTN_SETTINGS:
            await self.send_settings(chat_id, update)
            return
        if text == BTN_CHAT_AUTOREPLY_ON:
            await self.set_chat_autoreply_enabled(
                chat_id,
                user_id,
                update,
                enabled=True,
            )
            return
        if text == BTN_CHAT_AUTOREPLY_OFF:
            await self.set_chat_autoreply_enabled(
                chat_id,
                user_id,
                update,
                enabled=False,
            )
            return
        if text == BTN_CHAT_EMPTY_ONLY_ON:
            await self.set_chat_autoreply_only_empty_chat(
                chat_id,
                user_id,
                update,
                enabled=True,
            )
            return
        if text == BTN_CHAT_EMPTY_ONLY_OFF:
            await self.set_chat_autoreply_only_empty_chat(
                chat_id,
                user_id,
                update,
                enabled=False,
            )
            return
        if text == BTN_CHAT_SMART_NON_EMPTY_ON:
            await self.set_chat_autoreply_smart_non_empty(
                chat_id,
                user_id,
                update,
                enabled=True,
            )
            return
        if text == BTN_CHAT_SMART_NON_EMPTY_OFF:
            await self.set_chat_autoreply_smart_non_empty(
                chat_id,
                user_id,
                update,
                enabled=False,
            )
            return
        if text == BTN_CHAT_POLICY:
            await self.cycle_chat_autoreply_policy(
                chat_id,
                user_id,
                update,
            )
            return
        if text == BTN_CHAT_RULES:
            await self.start_chat_rules(chat_id, update)
            return
        # Выбор профиля
        for pid in self.available_profiles:
            if text == self._profile_button(pid):
                had_pending = chat_id in self.pending_actions
                self._set_profile(chat_id, pid)
                if had_pending:
                    self._clear_pending_action(chat_id)
                suffix = (
                    '\n⚠️ Незавершённый ввод сброшен.'
                    if had_pending else ''
                )
                await update.message.reply_text(
                    f'✅ Активный профиль: {self._profile_name(pid)}{suffix}',
                    reply_markup=self.get_main_keyboard(pid),
                )
                return

        # Настройки
        if text == BTN_PRICE:
            await self._prompt_pending_action(
                chat_id=chat_id,
                profile_id=profile_id,
                action='DESIRED_PRICE',
                prompt='Введи желаемую цену (например 0.35):',
                update=update,
            )
            return
        if text == BTN_PRICE_GUARD:
            await self.open_price_guard_panel(chat_id, update)
            return
        if text == BTN_MIN:
            await self._prompt_pending_action(
                chat_id=chat_id,
                profile_id=profile_id,
                action='MIN_PRICE',
                prompt='Введи нижний порог цены:',
                update=update,
            )
            return
        if text == BTN_MAX:
            await self._prompt_pending_action(
                chat_id=chat_id,
                profile_id=profile_id,
                action='MAX_PRICE',
                prompt='Введи верхний порог цены:',
                update=update,
            )
            return
        if text == BTN_UNDERCUT:
            await self._prompt_pending_action(
                chat_id=chat_id,
                profile_id=profile_id,
                action='UNDERCUT_VALUE',
                prompt='Введи шаг понижения (например 0.0051 или 0.51):',
                update=update,
            )
            return
        if text == BTN_RAISE:
            await self._prompt_pending_action(
                chat_id=chat_id,
                profile_id=profile_id,
                action='RAISE_VALUE',
                prompt='Введи шаг повышения (например 0.0049 или 0.49):',
                update=update,
            )
            return
        if text == BTN_ROUNDING:
            await self.cycle_rounding_step(chat_id, user_id, update)
            return
        if text == BTN_REBOUND_ON:
            await self.set_rebound_to_desired(chat_id, user_id, update, enabled=True)
            return
        if text == BTN_REBOUND_OFF:
            await self.set_rebound_to_desired(chat_id, user_id, update, enabled=False)
            return
        if text == BTN_PRODUCTS:
            runtime = self._runtime_for_product(profile_id, self._product_id(profile_id))
            await update.message.reply_text(
                self._format_products_management_text(
                    profile_id,
                    runtime=runtime,
                ),
                reply_markup=self._products_inline_keyboard(
                    profile_id,
                    runtime=runtime,
                ),
            )
            return
        if text == BTN_PRODUCT_REMOVE:
            runtime = self._runtime_for_product(profile_id, self._product_id(profile_id))
            await update.message.reply_text(
                self._format_products_management_text(
                    profile_id,
                    runtime=runtime,
                    confirm='active',
                ),
                reply_markup=self._products_inline_keyboard(
                    profile_id,
                    runtime=runtime,
                    confirm='active',
                ),
            )
            return
        if text == BTN_PRODUCT_PREV:
            await self.switch_active_product(chat_id, update, step=-1)
            return
        if text == BTN_PRODUCT_NEXT:
            await self.switch_active_product(chat_id, update, step=1)
            return
        if text == BTN_MODE:
            await self.toggle_mode(chat_id, user_id, update)
            return
        if text == BTN_BACK:
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                '📋 Главное меню',
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        if chat_id in self.pending_actions:
            if self._is_pending_action_expired(chat_id):
                self._clear_pending_action(chat_id)
                await update.message.reply_text(
                    (
                        '⌛ Незавершённый ввод устарел '
                        '(больше 5 минут) и был сброшен.'
                    ),
                    reply_markup=self.get_main_keyboard(profile_id),
                )
                return
            await self.handle_pending_action(chat_id, user_id, text, update)
            return

        await update.message.reply_text(
            'Используй кнопки 👇',
            reply_markup=self.get_main_keyboard(profile_id),
        )

    async def _refresh_chat_rules_message(self, chat_id: int, query):
        context = self.chat_rules_context.get(chat_id) or {}
        profile_id = str(context.get('profile_id') or '').strip().lower()
        product_id = int(context.get('product_id') or 0)
        items = context.get('items')
        if not profile_id or product_id <= 0 or not isinstance(items, list):
            await query.answer('Сессия правил устарела. Открой заново.', show_alert=True)
            return False

        rules = self._chat_rules_load(
            profile_id=profile_id,
            product_id=product_id,
        )
        overview = self._format_chat_rules_overview(
            profile_id=profile_id,
            product_id=product_id,
            items=items,
            rules=rules,
        )
        keyboard = self._chat_rules_inline_keyboard(items=items, rules=rules)
        try:
            await query.edit_message_text(
                overview,
                reply_markup=keyboard,
            )
        except Exception:
            if query.message:
                await query.message.reply_text(
                    overview,
                    reply_markup=keyboard,
                )
        return True

    async def handle_callback_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        query = update.callback_query
        if not query or not update.effective_user or not update.effective_chat:
            return
        if not self._check_access(update.effective_user.id):
            await query.answer('Нет доступа', show_alert=True)
            return

        data = (query.data or '').strip()
        if data.startswith('pm:'):
            await self._handle_products_callback_query(update, query, data)
            return
        if data.startswith('pc:'):
            await self._handle_price_guard_callback_query(update, query, data)
            return
        if not data.startswith('cr:'):
            await query.answer()
            return

        chat_id = update.effective_chat.id
        if chat_id not in self.pending_actions:
            await query.answer('Открой редактор правил заново', show_alert=True)
            return
        pending_action, pending_profile = self._get_pending_action(chat_id)
        current_profile = self._active_profile(chat_id)
        if pending_action != 'CHAT_RULES' or pending_profile != current_profile:
            await query.answer('Открой редактор правил заново', show_alert=True)
            return

        context_payload = self.chat_rules_context.get(chat_id) or {}
        product_id = int(context_payload.get('product_id') or 0)
        items = context_payload.get('items')
        if product_id <= 0 or not isinstance(items, list):
            await query.answer('Сессия правил устарела', show_alert=True)
            return

        parts = data.split(':')
        action = parts[1] if len(parts) > 1 else ''

        if action == 'd':
            self._clear_pending_action(chat_id)
            await query.answer('Готово')
            if query.message:
                await query.message.reply_text(
                    '✅ Редактор правил закрыт',
                    reply_markup=self.get_settings_keyboard(current_profile),
                )
            return

        if action == 'x':
            self._chat_rules_save(
                profile_id=current_profile,
                product_id=product_id,
                rules={},
                user_id=update.effective_user.id,
            )
            await query.answer('Правила сброшены')
            await self._refresh_chat_rules_message(chat_id, query)
            return

        if action == 'r':
            await query.answer('Обновлено')
            await self._refresh_chat_rules_message(chat_id, query)
            return

        if action == 't':
            if len(parts) < 3:
                await query.answer('Некорректная кнопка', show_alert=True)
                return
            try:
                index = int(parts[2])
            except Exception:
                await query.answer('Некорректный номер', show_alert=True)
                return
            if index <= 0 or index > len(items):
                await query.answer('Правило не найдено', show_alert=True)
                return
            item = items[index - 1]
            key = str(item.get('key') or '').strip().lower()
            if not key:
                await query.answer('Ошибка правила', show_alert=True)
                return
            rules = self._chat_rules_load(
                profile_id=current_profile,
                product_id=product_id,
            )
            entry = rules.get(key) or {}
            enabled = not bool(entry.get('enabled', False))
            entry = {
                'enabled': enabled,
                'text': str(entry.get('text') or '').strip(),
                'option': str(entry.get('option') or item.get('option') or '').strip(),
                'value': str(entry.get('value') or item.get('value') or '').strip(),
            }
            rules[key] = entry
            self._chat_rules_save(
                profile_id=current_profile,
                product_id=product_id,
                rules=rules,
                user_id=update.effective_user.id,
            )
            await query.answer('Включено' if enabled else 'Выключено')
            await self._refresh_chat_rules_message(chat_id, query)
            return

        await query.answer()

    async def _refresh_price_guard_message(
        self,
        *,
        query,
        profile_id: str,
    ) -> None:
        text = self._format_price_guard_text(profile_id)
        markup = self._price_guard_inline_keyboard(profile_id=profile_id)
        if query.message:
            await query.message.edit_text(text, reply_markup=markup)

    async def _handle_price_guard_callback_query(
        self,
        update: Update,
        query,
        data: str,
    ) -> None:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        profile_id = self._active_profile(chat_id)
        parts = data.split(':')
        action = parts[1] if len(parts) > 1 else ''
        if action == 'done':
            await query.answer('Готово')
            if query.message:
                await query.message.reply_text(
                    '✅ Лимиты и шаги закрыты',
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
            storage.set_runtime_setting(
                'SHOWCASE_ROUND_STEP',
                str(new_step),
                user_id=user_id,
                source='telegram',
                profile_id=runtime_profile_id,
            )
            await query.answer(f'Округление: {self._rounding_label(new_step)}')
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
            storage.set_runtime_setting(
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

    async def _refresh_products_message(
        self,
        *,
        query,
        profile_id: str,
        confirm: Optional[str] = None,
    ) -> None:
        runtime = self._runtime_for_product(profile_id, self._product_id(profile_id))
        text = self._format_products_management_text(
            profile_id,
            runtime=runtime,
            confirm=confirm,
        )
        markup = self._products_inline_keyboard(
            profile_id,
            runtime=runtime,
            confirm=confirm,
        )
        if query.message:
            await query.message.edit_text(text, reply_markup=markup)

    async def _handle_products_callback_query(
        self,
        update: Update,
        query,
        data: str,
    ) -> None:
        chat_id = update.effective_chat.id
        profile_id = self._active_profile(chat_id)
        user_id = update.effective_user.id
        parts = data.split(':')
        action = parts[1] if len(parts) > 1 else ''

        if action == 'd':
            await query.answer('Готово')
            if query.message:
                await query.message.reply_text(
                    '✅ Управление товарами закрыто',
                    reply_markup=self.get_main_keyboard(profile_id),
                )
            return

        if action == 'r':
            await query.answer('Обновлено')
            await self._refresh_products_message(query=query, profile_id=profile_id)
            return

        if action == 's':
            try:
                product_id = int(parts[2])
            except Exception:
                await query.answer('Некорректный товар', show_alert=True)
                return
            tracked_ids = self._tracked_product_ids(profile_id)
            if product_id not in tracked_ids:
                await query.answer('Товар уже отсутствует', show_alert=True)
                await self._refresh_products_message(
                    query=query,
                    profile_id=profile_id,
                )
                return
            had_pending = chat_id in self.pending_actions
            if had_pending:
                # Если пользователь переключает товар во время незавершённого
                # ввода, сбрасываем pending, чтобы значение не записалось
                # в другую товарную пару.
                self._clear_pending_action(chat_id)
            self.profile_products[profile_id] = product_id
            await self._ensure_product_auto_name(profile_id, product_id)
            answer_text = (
                'Активный товар выбран (ввод сброшен)'
                if had_pending
                else 'Активный товар выбран'
            )
            await query.answer(answer_text)
            await self._refresh_products_message(query=query, profile_id=profile_id)
            return

        if action == 'a':
            self._set_pending_action(chat_id, 'PRODUCT_ADD', profile_id)
            await query.answer('Жду ID товара')
            if query.message:
                await query.message.reply_text(
                    'Отправь ID товара для добавления или выбора.',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
            return

        if action == 'u':
            if not self._product_id(profile_id):
                await query.answer('Сначала выбери товар', show_alert=True)
                return
            self._set_pending_action(chat_id, 'PRODUCT_ADD_URL', profile_id)
            await query.answer('Жду URL конкурента')
            if query.message:
                await query.message.reply_text(
                    (
                        'Отправь URL конкурента для активного товара.\n'
                        'Можно отправить несколько URL через пробел или запятую.'
                    ),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
            return

        if action == 'n':
            if not self._product_id(profile_id):
                await query.answer('Сначала выбери товар', show_alert=True)
                return
            self._set_pending_action(chat_id, 'PRODUCT_RENAME', profile_id)
            await query.answer('Жду новое имя')
            if query.message:
                await query.message.reply_text(
                    'Отправь новое имя для активного товара.',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
            return

        if action == 'c':
            product_id = self._product_id(profile_id)
            if product_id <= 0:
                await query.answer('Сначала выбери товар', show_alert=True)
                return
            self._set_product_alias(
                profile_id,
                product_id,
                '',
                user_id=user_id,
                source='telegram_product_alias_clear',
            )
            await self._ensure_product_auto_name(profile_id, product_id)
            await query.answer('Имя сброшено')
            await self._refresh_products_message(query=query, profile_id=profile_id)
            return

        if action == 'rd':
            await query.answer('Подтверди удаление')
            await self._refresh_products_message(
                query=query,
                profile_id=profile_id,
                confirm='active',
            )
            return

        if action == 'ra':
            await query.answer('Подтверди очистку')
            await self._refresh_products_message(
                query=query,
                profile_id=profile_id,
                confirm='all',
            )
            return

        if action == 'y':
            scope = parts[2] if len(parts) > 2 else ''
            if scope == 'active':
                target_product_id = self._product_id(profile_id)
                tracked_ids = self._tracked_product_ids(profile_id)
                if target_product_id <= 0 or target_product_id not in tracked_ids:
                    await query.answer('Товар не найден', show_alert=True)
                    await self._refresh_products_message(
                        query=query,
                        profile_id=profile_id,
                    )
                    return
                removed = self._remove_product_with_cleanup(
                    profile_id=profile_id,
                    product_id=target_product_id,
                    user_id=user_id,
                    source='telegram',
                )
                if not removed:
                    await query.answer('Не удалось удалить товар', show_alert=True)
                    await self._refresh_products_message(
                        query=query,
                        profile_id=profile_id,
                    )
                    return
                remaining_ids = self._tracked_product_ids(profile_id)
                self.profile_products[profile_id] = remaining_ids[0] if remaining_ids else 0
                await query.answer('Активный товар удалён')
                await self._refresh_products_message(query=query, profile_id=profile_id)
                return
            if scope == 'all':
                tracked_ids = self._tracked_product_ids(profile_id)
                self._clear_products_with_cleanup(
                    profile_id=profile_id,
                    user_id=user_id,
                    source='telegram',
                    fallback_ids=tracked_ids,
                )
                self.profile_products[profile_id] = 0
                await query.answer('Список очищен')
                await self._refresh_products_message(query=query, profile_id=profile_id)
                return

        await query.answer()

    # ================================
    # Status and diagnostics
    # ================================
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
        product_id = self._product_id(profile_id)
        state = self._state_for_product(profile_id, product_id)
        runtime = self._runtime_for_product(profile_id, product_id)
        tracked_lines = self._format_tracked_products(profile_id, runtime=runtime)
        tracked_count = len(tracked_lines) if tracked_lines != ['нет'] else 0
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
        update_str = last_update.strftime('%Y-%m-%d %H:%M') if last_update else 'Никогда'

        parse_at = state.get('last_competitor_parse_at')
        parse_at_str = parse_at.strftime('%Y-%m-%d %H:%M:%S') if parse_at else 'Никогда'
        competitor_url = state.get('last_competitor_url') or 'N/A'
        parse_method = state.get('last_competitor_method') or 'N/A'

        target_price = state.get('last_target_price')
        if target_price is None:
            target_price = state.get('last_price')
        display_price: Optional[float] = None
        client = self._api_client(profile_id)
        product_id = self._product_id(profile_id)
        get_display_price = (
            getattr(client, 'get_display_price', None) if client else None
        )
        get_my_price = getattr(client, 'get_my_price', None) if client else None
        if profile_id == 'ggsel':
            # Для GGSEL в первую очередь показываем фактическую витринную цену
            # (публичный goods API), а не округлённую seller-базу.
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
                except Exception as e:
                    logger.warning(
                        '[%s] Не удалось получить публичную цену для статуса: %s',
                        profile_name,
                        e,
                    )
            if display_price is None:
                if callable(get_my_price) and product_id > 0:
                    try:
                        api_price = await asyncio.to_thread(get_my_price, product_id)
                        if api_price is not None:
                            display_price = float(api_price)
                    except Exception as e:
                        logger.warning(
                            '[%s] Не удалось получить API-цену для статуса: %s',
                            profile_name,
                            e,
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
                except Exception as e:
                    logger.warning(
                        '[%s] Не удалось получить display-цену для статуса: %s',
                        profile_name,
                        e,
                    )
            if (
                display_price is None
                and profile_id != 'digiseller'
                and callable(get_my_price)
                and product_id > 0
            ):
                try:
                    api_price = await asyncio.to_thread(get_my_price, product_id)
                    if api_price is not None:
                        display_price = float(api_price)
                except Exception as e:
                    logger.warning(
                        '[%s] Не удалось получить live-цену для статуса: %s',
                        profile_name,
                        e,
                    )
            if display_price is None:
                display_price = target_price
        competitor_price = state.get('last_competitor_min')
        target_price_str = (
            f'{target_price:.4f}' if target_price is not None else 'N/A'
        )
        display_price_str = (
            f'{display_price:.4f}'
            if display_price is not None else 'N/A'
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
        chat_block = ''
        chat_meta = self._chat_autoreply_meta(profile_id)
        if chat_meta:
            if chat_meta["enabled"]:
                chat_block = (
                    '\n'
                    f'💬 Авто-инструкции: ВКЛ\n'
                    f'🧷 Только по правилам: '
                    f'{"Да" if chat_meta["require_rules"] else "Нет"}\n'
                    f'🧭 Режим отправки: '
                    f'{self._chat_policy_label(chat_meta["policy"])}\n'
                    f'📨 Отправлено: {chat_meta["sent_count"]}\n'
                    f'🕓 Последняя отправка: {chat_meta["last_sent"]}'
                )
            else:
                chat_block = '\n💬 Авто-инструкции: ВЫКЛ'

        text = f"""📊 Статус

🧭 Площадка: {profile_name}
🆔 Активный товар: {self._product_label(profile_id, product_id)} ({active_product_slot_text})
📦 Товаров в мониторинге: {tracked_count}
{display_price_label}: {display_price_str}₽
{target_price_label}: {target_price_str}₽
📈 Цена конкурента: {competitor_price_str}₽
🔗 URL: {competitor_url}
🧪 Метод парсинга: {parse_method}
🕓 Последний парс: {parse_at_str}
📡 Мониторинг: {monitor_mode}
{chat_block}

🔔 Авто: {'ВКЛ' if state.get('auto_mode', True) else 'ВЫКЛ'}
🎯 Режим: {self._mode_label(runtime.MODE)}
🕐 Обновление: {update_str}
⏲️ Интервал: {runtime.CHECK_INTERVAL}s
"""
        await update.message.reply_text(
            text,
            reply_markup=self.get_main_keyboard(profile_id),
        )

    async def send_settings(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        profile_name = self._profile_name(profile_id)
        product_id = self._product_id(profile_id)
        state = self._state_for_product(profile_id, product_id)
        runtime = self._runtime_for_product(profile_id, product_id)
        tracked_lines = self._format_tracked_products(profile_id, runtime=runtime)
        pair_lines = self._format_tracking_pairs(profile_id, runtime=runtime)
        tracked_count = len(tracked_lines) if tracked_lines != ['нет'] else 0
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
        min_price = float(getattr(runtime, 'MIN_PRICE', 0.0) or 0.0)
        max_price = float(getattr(runtime, 'MAX_PRICE', 0.0) or 0.0)
        desired_price = float(getattr(runtime, 'DESIRED_PRICE', 0.0) or 0.0)
        undercut_value = float(getattr(runtime, 'UNDERCUT_VALUE', 0.0) or 0.0)
        raise_value = float(getattr(runtime, 'RAISE_VALUE', 0.0049) or 0.0049)
        round_step = getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
        rebound_on_min = bool(
            getattr(runtime, 'REBOUND_TO_DESIRED_ON_MIN', False)
        )
        chat_block = ''
        chat_meta = self._chat_autoreply_meta(profile_id)
        if chat_meta:
            if chat_meta["enabled"]:
                chat_block = (
                    '\n'
                    f'💬 Авто-инструкции: ВКЛ\n'
                    f'📭 Только пустой чат: '
                    f'{"Да" if chat_meta["only_empty_chat"] else "Нет"}\n'
                    f'🧠 Умный непустой чат: '
                    f'{"Да" if chat_meta["smart_non_empty"] else "Нет"}\n'
                    f'🧷 Только по правилам: '
                    f'{"Да" if chat_meta["require_rules"] else "Нет"}\n'
                    f'🧭 Режим отправки: '
                    f'{self._chat_policy_label(chat_meta["policy"])}\n'
                    f'📨 Отправлено: {chat_meta["sent_count"]}\n'
                    f'🕓 Последний запуск: {chat_meta["last_run"]}'
                )
            else:
                chat_block = '\n💬 Авто-инструкции: ВЫКЛ'

        base_lines = [
            '⚙️ Настройки',
            '',
            f'🧭 Активная площадка: {profile_name}',
            (
                '🆔 Активный товар (для редактирования): '
                f'{self._product_label(profile_id, product_id)}'
            ),
            f'📦 Товаров в мониторинге: {tracked_count} (активный: {active_product_slot_text})',
            f'🔗 Активная пара: {pair_lines[0] if pair_lines else "не задана"}',
            '',
            f'🔔 Автоцена: {"ВКЛ" if state.get("auto_mode", True) else "ВЫКЛ"}',
            f'🔹 Режим: {self._mode_label(runtime.MODE)}',
            f'⏱️ CHECK_INTERVAL: {runtime.CHECK_INTERVAL}s',
            f'📡 Мониторинг: {monitor_mode} | URL: {len(runtime.COMPETITOR_URLS)}',
            '',
            f'🧮 Лимиты: {min_price:.4f}₽ .. {max_price:.4f}₽',
            f'🎯 Рекомендуемая: {desired_price:.4f}₽ | ↘️ {undercut_value:.4f} | ↗️ {raise_value:.4f}',
            (
                '🔘 Округление витрины: '
                f'{self._rounding_label(round_step)}'
            ),
            (
                '🔁 Отскок к рекомендуемой на минимуме: '
                f'{"Да" if rebound_on_min else "Нет"}'
            ),
            '',
            (
                '🔁 Обновлять только при изменении конкурента: '
                f'{"Да" if runtime.UPDATE_ONLY_ON_COMPETITOR_CHANGE else "Нет"}'
            ),
            'ℹ️ Настройки применяются только к активному товару.',
        ]
        base_lines.extend(
            [
                '',
                f'📦 Список товаров: {", ".join(tracked_lines)}',
            ]
        )

        if chat_block:
            base_lines.extend(['', chat_block.strip()])

        text = '\n'.join(base_lines)
        await update.message.reply_text(
            text,
            reply_markup=self.get_settings_keyboard(profile_id),
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
        product_id = self._product_id(profile_id)
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
                    product = await asyncio.to_thread(client.get_product, product_id)
                    product_ok = product is not None
                    product_price = product.price if product else None
            except Exception as e:
                logger.error('Ошибка API в диагностике: %s', e)
            try:
                if hasattr(client, 'can_refresh_access_token'):
                    can_refresh = await asyncio.to_thread(
                        client.can_refresh_access_token,
                    )
                    refresh_line = (
                        'Token refresh: '
                        f'{"OK" if can_refresh else "FAIL"}'
                    )
            except Exception as e:
                logger.error('Ошибка проверки refresh capability: %s', e)

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
            except Exception as e:
                logger.error('Ошибка token/perms в диагностике: %s', e)

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
            except Exception as e:
                logger.error('Ошибка chat/perms в диагностике: %s', e)

        now = datetime.now()
        last_cycle = state.get('last_cycle')
        age = int((now - last_cycle).total_seconds()) if last_cycle else 0
        lines = [
            '🩺 Диагностика',
            '',
            f'Профиль: {profile_name}',
            f'API: {"OK" if api_ok else "FAIL"}',
            (
                f'Product: {"OK" if product_ok else "FAIL"} '
                f'({self._fmt_price(product_price)}₽)'
            ),
            f'Config: {"OK" if is_valid else "INVALID"}',
            f'Heartbeat: {age}s',
            f'Auto: {"ON" if state.get("auto_mode", True) else "OFF"}',
            f'Competitors: {len(runtime.COMPETITOR_URLS)}',
            f'Last parser error: {state.get("last_competitor_error") or "N/A"}',
            (
                'Last block reason: '
                f'{state.get("last_competitor_block_reason") or "N/A"}'
            ),
        ]
        if perms_line:
            lines.append(perms_line)
        if chat_perms_line:
            lines.append(chat_perms_line)
        if refresh_line:
            lines.append(refresh_line)
        auto_change = storage.get_last_setting_change(
            'auto_mode',
            profile_id=runtime_profile_id,
        )
        if auto_change:
            auto_actor = auto_change.get('user_id')
            auto_actor_text = (
                str(auto_actor) if auto_actor is not None else 'system'
            )
            lines.append(
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
            lines.append(
                'Monitoring changed: '
                f'{monitor_change.get("timestamp")} by {monitor_actor_text} '
                f'({monitor_change.get("source")})'
            )
        chat_meta = self._chat_autoreply_meta(profile_id)
        if chat_meta:
            lines.append(
                'Chat autoreply: '
                f'{"ON" if chat_meta["enabled"] else "OFF"} '
                f'(sent={chat_meta["sent_count"]})'
            )
            lines.append(
                'Chat dedupe: '
                f'{"ON" if chat_meta["dedupe"] else "OFF"} '
                f'(duplicates={chat_meta["duplicate_count"]}, '
                f'lookback={chat_meta["lookback"]})'
            )
            lines.append(
                f'Chat interval: {chat_meta["interval_seconds"]}s'
            )
            lines.append(f'Chat last run: {chat_meta["last_run"]}')
            lines.append(f'Chat last sent: {chat_meta["last_sent"]}')
            lines.append(f'Chat last cleanup: {chat_meta["last_cleanup"]}')
            if chat_meta['last_error'] != 'N/A':
                lines.append(f'Chat last error: {chat_meta["last_error"]}')
        if errors:
            lines.append('Errors: ' + '; '.join(errors[:3]))
        await update.message.reply_text(
            '\n'.join(lines),
            reply_markup=self.get_main_keyboard(profile_id),
        )

    # ================================
    # Actions
    # ================================
    async def handle_price_change(self, chat_id: int, delta: float, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        state = self._state_for_product(profile_id, product_id)
        client = self._api_client(profile_id)
        current_price = state.get('last_price')

        if current_price is None and client and product_id:
            try:
                current_price = await asyncio.to_thread(client.get_my_price, product_id)
            except Exception:
                current_price = None

        if current_price is None:
            await update.message.reply_text(
                '❌ Нет текущей цены',
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        new_price = round(max(current_price + delta, runtime.MIN_PRICE), 4)
        if new_price == current_price:
            await update.message.reply_text(
                f'⚠️ Минимум {runtime.MIN_PRICE}₽',
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        if not client or not product_id:
            await update.message.reply_text(
                '❌ Нет API клиента/товара для профиля',
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        success = await asyncio.to_thread(client.update_price, product_id, new_price)
        if success:
            storage.update_state(
                profile_id=runtime_profile_id,
                last_price=new_price,
                last_target_price=new_price,
                last_target_competitor_min=state.get('last_competitor_min'),
                last_update=datetime.now(),
            )
            await update.message.reply_text(
                (
                    f'✅ [{self._profile_name(profile_id)}] '
                    f'{current_price:.4f}₽ → {new_price:.4f}₽'
                ),
                reply_markup=self.get_main_keyboard(profile_id),
            )
        else:
            await update.message.reply_text(
                '❌ Ошибка API',
                reply_markup=self.get_main_keyboard(profile_id),
            )

    async def toggle_auto(self, update: Update):
        if not update.message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        state = self._state_for_product(profile_id, product_id)
        await self.set_auto_enabled(
            update,
            enabled=not state.get('auto_mode', True),
        )

    async def set_auto_enabled(self, update: Update, *, enabled: bool):
        if not update.message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        user_id = update.effective_user.id if update.effective_user else None
        storage.set_auto_mode(
            enabled,
            profile_id=runtime_profile_id,
            user_id=user_id,
            source='telegram',
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

    async def set_chat_autoreply_enabled(
        self,
        chat_id: int,
        user_id: int,
        update: Update,
        *,
        enabled: bool,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        storage.set_runtime_setting(
            'CHAT_AUTOREPLY_ENABLED',
            'true' if enabled else 'false',
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            f'💬 Авто-инструкции: {"ВКЛ" if enabled else "ВЫКЛ"}',
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def set_chat_autoreply_only_empty_chat(
        self,
        chat_id: int,
        user_id: int,
        update: Update,
        *,
        enabled: bool,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        storage.set_runtime_setting(
            'CHAT_AUTOREPLY_ONLY_EMPTY_CHAT',
            'true' if enabled else 'false',
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            (
                '📭 Отправка только в пустой чат: '
                f'{"ВКЛ" if enabled else "ВЫКЛ"}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def set_chat_autoreply_smart_non_empty(
        self,
        chat_id: int,
        user_id: int,
        update: Update,
        *,
        enabled: bool,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        storage.set_runtime_setting(
            'CHAT_AUTOREPLY_SMART_NON_EMPTY',
            'true' if enabled else 'false',
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            (
                '🧠 Умный режим для непустого чата: '
                f'{"ВКЛ" if enabled else "ВЫКЛ"}'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )
        await self.send_settings(chat_id, update)

    async def cycle_chat_autoreply_policy(
        self,
        chat_id: int,
        user_id: int,
        update: Update,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        product_id = self._product_id(profile_id)
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
            index = _CHAT_POLICY_SEQUENCE.index(current)
        except ValueError:
            index = 0
        new_policy = _CHAT_POLICY_SEQUENCE[
            (index + 1) % len(_CHAT_POLICY_SEQUENCE)
        ]

        storage.set_runtime_setting(
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

    async def start_chat_rules(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        if product_id <= 0:
            await update.message.reply_text(
                '❌ Для активного профиля не задан product_id',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return
        if not self._chat_autoreply_supported(profile_id):
            await update.message.reply_text(
                '❌ Для этого профиля авто-инструкции недоступны',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        client = self._api_client(profile_id)
        get_product_info = getattr(client, 'get_product_info', None) if client else None
        if not callable(get_product_info):
            await update.message.reply_text(
                '❌ API клиента для инструкций нет',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        best_items: list[dict[str, str]] = []
        best_info: dict[str, Any] = {}
        for lang in ('ru-RU', 'en-US'):
            try:
                info = await asyncio.to_thread(
                    get_product_info,
                    product_id,
                    timeout=10,
                    lang=lang,
                ) or {}
            except Exception:
                info = {}
            if not isinstance(info, dict):
                info = {}
            items = self._build_chat_rules_items(info)
            if len(items) > len(best_items):
                best_items = items
                best_info = info

        if not best_info:
            try:
                fallback_info = await asyncio.to_thread(
                    get_product_info,
                    product_id,
                    timeout=10,
                ) or {}
            except Exception:
                fallback_info = {}
            if isinstance(fallback_info, dict):
                best_info = fallback_info
                best_items = self._build_chat_rules_items(fallback_info)

        rules = self._chat_rules_load(
            profile_id=profile_id,
            product_id=product_id,
        )
        rules, migrated = self._chat_rules_rebind_legacy_keys(
            rules=rules,
            items=best_items,
        )
        if migrated:
            self._chat_rules_save(
                profile_id=profile_id,
                product_id=product_id,
                rules=rules,
                user_id=update.effective_user.id if update.effective_user else None,
            )
        self.chat_rules_context[chat_id] = {
            'profile_id': profile_id,
            'product_id': product_id,
            'items': best_items,
            'product_info': best_info,
        }
        self._set_pending_action(chat_id, 'CHAT_RULES', profile_id)
        keyboard = self._chat_rules_inline_keyboard(items=best_items, rules=rules)
        await update.message.reply_text(
            self._format_chat_rules_overview(
                profile_id=profile_id,
                product_id=product_id,
                items=best_items,
                rules=rules,
            ),
            reply_markup=keyboard,
        )
        await update.message.reply_text(
            (
                'ℹ️ Включение/выключение теперь кнопками.\n'
                'Кастомный текст опционален: text <номер> <текст>\n'
                'Если текст не задан, отправится инструкция из карточки товара.'
            ),
            reply_markup=self.get_settings_keyboard(profile_id),
        )

    async def switch_active_product(
        self,
        chat_id: int,
        update: Update,
        *,
        step: int,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        product_ids = self._tracked_product_ids(profile_id, runtime=runtime)
        if not product_ids:
            await update.message.reply_text(
                '❌ В профиле нет товаров для переключения',
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        current_product_id = self._product_id(profile_id)
        if current_product_id not in product_ids:
            current_idx = 0
        else:
            current_idx = product_ids.index(current_product_id)
        if len(product_ids) == 1:
            new_product_id = product_ids[0]
        else:
            direction = -1 if step < 0 else 1
            new_product_id = product_ids[
                (current_idx + direction) % len(product_ids)
            ]

        had_pending = chat_id in self.pending_actions
        if had_pending:
            self._clear_pending_action(chat_id)
        self.profile_products[profile_id] = new_product_id

        new_idx = product_ids.index(new_product_id) + 1
        suffix = '\n⚠️ Незавершённый ввод сброшен.' if had_pending else ''
        await update.message.reply_text(
            (
                f'✅ Активный товар: {new_product_id} '
                f'({new_idx}/{len(product_ids)})\n'
                'ℹ️ Стратегия и автоцена применяются только к '
                'активному товару.\n'
                'Открой ⚙ Настройки, если нужно изменить параметры.'
                f'{suffix}'
            ),
            reply_markup=self.get_main_keyboard(profile_id),
        )

    async def toggle_mode(self, chat_id: int, user_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        new_mode = self._next_mode(runtime.MODE)
        storage.set_runtime_setting(
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
        update: Update,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)
        new_step = self._next_rounding_step(
            getattr(runtime, 'SHOWCASE_ROUND_STEP', 0.01)
        )
        storage.set_runtime_setting(
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
        update: Update,
        *,
        enabled: bool,
    ):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        storage.set_runtime_setting(
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

    async def handle_pending_action(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        update: Update,
    ):
        if not update.message:
            return
        action, pending_profile_id = self._get_pending_action(chat_id)
        if not action:
            return
        profile_id = self._active_profile(chat_id)
        if self._is_pending_action_expired(chat_id):
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                '⌛ Незавершённый ввод устарел. Открой пункт заново.',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return
        if pending_profile_id != profile_id:
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                (
                    '⚠️ Незавершённый ввод сброшен: '
                    'активный профиль был изменён.'
                ),
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return
        product_id = self._product_id(profile_id)
        runtime_profile_id = self._runtime_profile_id_for_product(
            profile_id,
            product_id,
        )
        runtime = self._runtime_for_product(profile_id, product_id)

        if action in {
            'DESIRED_PRICE',
            'UNDERCUT_VALUE',
            'RAISE_VALUE',
            'MIN_PRICE',
            'MAX_PRICE',
            'SHOWCASE_ROUND_STEP',
        }:
            try:
                value = float(text.replace(',', '.'))
            except ValueError:
                await update.message.reply_text(
                    '❌ Введи число',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if action == 'SHOWCASE_ROUND_STEP':
                if value < 0:
                    await update.message.reply_text(
                        '❌ Значение должно быть >= 0',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return
            elif value <= 0:
                await update.message.reply_text(
                    '❌ Значение должно быть > 0',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            runtime_min = float(getattr(runtime, 'MIN_PRICE', 0.0) or 0.0)
            runtime_max = float(getattr(runtime, 'MAX_PRICE', 0.0) or 0.0)
            if action == 'MIN_PRICE' and runtime_max > 0 and value > runtime_max:
                await update.message.reply_text(
                    '❌ MIN_PRICE не может быть больше MAX_PRICE',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if action == 'MAX_PRICE' and runtime_min > 0 and value < runtime_min:
                await update.message.reply_text(
                    '❌ MAX_PRICE не может быть меньше MIN_PRICE',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            value = round(value, 4)
            storage.set_runtime_setting(
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
            return

        if action == 'CHAT_RULES':
            context = self.chat_rules_context.get(chat_id) or {}
            ctx_profile = str(context.get('profile_id') or '').strip().lower()
            ctx_product = int(context.get('product_id') or 0)
            if ctx_profile != profile_id or ctx_product != product_id:
                self._clear_pending_action(chat_id)
                await update.message.reply_text(
                    (
                        '⚠️ Контекст правил сброшен: активный '
                        'профиль или товар изменился.'
                    ),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            items = context.get('items')
            if not isinstance(items, list):
                items = []
            rules = self._chat_rules_load(
                profile_id=profile_id,
                product_id=product_id,
            )

            normalized = text.strip()
            lower = normalized.lower()
            if lower in {'done', 'готово', 'выход', 'exit'}:
                self._clear_pending_action(chat_id)
                await update.message.reply_text(
                    '✅ Редактор правил закрыт',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if lower in {'reset', 'сброс'}:
                self._chat_rules_save(
                    profile_id=profile_id,
                    product_id=product_id,
                    rules={},
                    user_id=user_id,
                )
                await update.message.reply_text(
                    self._format_chat_rules_overview(
                        profile_id=profile_id,
                        product_id=product_id,
                        items=items,
                        rules={},
                    ),
                    reply_markup=self._chat_rules_inline_keyboard(
                        items=items,
                        rules={},
                    ),
                )
                await update.message.reply_text(
                    '✅ Все правила сброшены',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            match = re.match(
                r'^(clear|text)\s+(\d+)(?:\s+(.+))?$',
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not match:
                await update.message.reply_text(
                    (
                        '❌ Команда не распознана.\n'
                        'Используй: text N <текст> | clear N | reset | done'
                    ),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            command = match.group(1).lower()
            index = int(match.group(2))
            payload = (match.group(3) or '').strip()
            if index <= 0 or index > len(items):
                await update.message.reply_text(
                    f'❌ Номер должен быть в диапазоне 1..{len(items)}',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            item = items[index - 1]
            key = str(item.get('key') or '').strip().lower()
            if not key:
                await update.message.reply_text(
                    '❌ Не удалось обработать выбранный пункт',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            entry = rules.get(key) or {}
            entry = {
                'enabled': bool(entry.get('enabled', False)),
                'text': str(entry.get('text') or '').strip(),
                'option': str(entry.get('option') or item.get('option') or '').strip(),
                'value': str(entry.get('value') or item.get('value') or '').strip(),
            }

            if command == 'clear':
                entry['text'] = ''
            elif command == 'text':
                if not payload:
                    await update.message.reply_text(
                        '❌ Укажи текст: text <номер> <сообщение>',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return
                entry['text'] = payload
                entry['enabled'] = True

            rules[key] = entry
            self._chat_rules_save(
                profile_id=profile_id,
                product_id=product_id,
                rules=rules,
                user_id=user_id,
            )
            await update.message.reply_text(
                self._format_chat_rules_overview(
                    profile_id=profile_id,
                    product_id=product_id,
                    items=items,
                    rules=rules,
                ),
                reply_markup=self._chat_rules_inline_keyboard(
                    items=items,
                    rules=rules,
                ),
            )
            await update.message.reply_text(
                'ℹ️ Вкл/выкл удобнее делать кнопками под списком.',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            return

        if action == 'MANAGE_PRODUCTS':
            normalized = text.strip()
            if not normalized:
                await update.message.reply_text(
                    '❌ Отправь ID товара или `list`',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            lower = normalized.lower()
            if lower in {'list', 'список'}:
                self._clear_manage_products_context(chat_id)
                lines = self._format_tracked_products(
                    profile_id,
                    runtime=runtime,
                )
                await update.message.reply_text(
                    '📦 Товары в мониторинге:\n' + '\n'.join(lines),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            def _resolve_product_token(token: str) -> int:
                normalized_token = str(token or '').strip().lower()
                if normalized_token in {'active', 'активный', 'текущий'}:
                    return int(self._product_id(profile_id) or 0)
                try:
                    return int(float(normalized_token.replace(',', '.')))
                except Exception:
                    return 0

            name_match = re.match(
                r'^(?:name|название)\s+([^\s]+)\s+(.+)$',
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if name_match:
                target_product_id = _resolve_product_token(name_match.group(1))
                if target_product_id <= 0:
                    await update.message.reply_text(
                        '❌ Укажи корректный product_id или `active`',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return
                alias_text = re.sub(
                    r'\s+',
                    ' ',
                    str(name_match.group(2) or '').strip(),
                ).strip()
                if not alias_text:
                    await update.message.reply_text(
                        '❌ Имя не должно быть пустым',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return
                self._set_product_alias(
                    profile_id,
                    target_product_id,
                    alias_text,
                    user_id=user_id,
                    source='telegram_product_alias',
                )
                self.profile_products[profile_id] = target_product_id
                self._clear_manage_products_context(chat_id)
                self._clear_pending_action(chat_id)
                await update.message.reply_text(
                    (
                        '✅ Имя товара сохранено:\n'
                        f'{self._product_label(profile_id, target_product_id)}'
                    ),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                await self.send_settings(chat_id, update)
                return

            clear_name_match = re.match(
                r'^(?:clearname|nameclear|сбросимени)\s+([^\s]+)$',
                normalized,
                flags=re.IGNORECASE,
            )
            if clear_name_match:
                target_product_id = _resolve_product_token(clear_name_match.group(1))
                if target_product_id <= 0:
                    await update.message.reply_text(
                        '❌ Укажи корректный product_id или `active`',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return
                self._set_product_alias(
                    profile_id,
                    target_product_id,
                    '',
                    user_id=user_id,
                    source='telegram_product_alias_clear',
                )
                self.profile_products[profile_id] = target_product_id
                self._clear_manage_products_context(chat_id)
                self._clear_pending_action(chat_id)
                await self._ensure_product_auto_name(profile_id, target_product_id)
                await update.message.reply_text(
                    (
                        '✅ Пользовательское имя удалено:\n'
                        f'{self._product_label(profile_id, target_product_id)}'
                    ),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                await self.send_settings(chat_id, update)
                return

            normalized_urls = []
            product_token = normalized
            if ' ' in normalized:
                product_token, raw_urls_part = normalized.split(' ', 1)
                raw_urls = [
                    item for item in raw_urls_part
                    .replace('\n', ' ')
                    .split(',') if item.strip()
                ]
                if len(raw_urls) == 1 and ' ' in raw_urls[0].strip():
                    raw_urls = [
                        item for item in raw_urls[0].split(' ')
                        if item.strip()
                    ]
                normalized_urls = storage.normalize_competitor_urls(raw_urls)
                if not normalized_urls:
                    await update.message.reply_text(
                        '❌ Не найдено валидных URL (http/https)',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return

            try:
                product_id = int(float(product_token.replace(',', '.')))
            except ValueError:
                await update.message.reply_text(
                    '❌ Нужен ID товара (число) или `list`',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if product_id <= 0:
                await update.message.reply_text(
                    '❌ ID товара должен быть > 0',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if not normalized_urls:
                current_ctx = self.manage_products_context.get(chat_id) or {}
                ctx_profile = str(
                    current_ctx.get('profile_id') or ''
                ).strip().lower()
                ctx_product_id = int(current_ctx.get('product_id') or 0)
                if ctx_profile != profile_id or ctx_product_id != product_id:
                    self.manage_products_context[chat_id] = {
                        'profile_id': profile_id,
                        'product_id': product_id,
                        'set_at': time.monotonic(),
                    }
                    await update.message.reply_text(
                        (
                            '⚠️ Подтверди добавление/выбор товара: '
                            f'отправь `{product_id}` ещё раз.\n'
                            'Или отправь пару сразу:\n'
                            '<product_id> <url_конкурента>'
                        ),
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return
            else:
                self._clear_manage_products_context(chat_id)

            tracked = self._tracked_products(profile_id, runtime=runtime)
            tracked_ids = {
                int(item.get('product_id') or 0)
                for item in tracked
            }
            is_new_product = product_id not in tracked_ids
            existing_urls = []
            if not is_new_product:
                for item in tracked:
                    if int(item.get('product_id') or 0) == product_id:
                        existing_urls = list(item.get('competitor_urls', []) or [])
                        break
            merged_urls = storage.normalize_competitor_urls(
                existing_urls + normalized_urls
            )
            target_runtime_profile_id = self._runtime_profile_id_for_product(
                profile_id,
                product_id,
            )
            if is_new_product:
                storage.upsert_tracked_product(
                    profile_id=profile_id,
                    product_id=product_id,
                    competitor_urls=merged_urls,
                )
            elif normalized_urls:
                storage.upsert_tracked_product(
                    profile_id=profile_id,
                    product_id=product_id,
                    competitor_urls=merged_urls,
                )
            if is_new_product or normalized_urls:
                storage.set_competitor_urls(
                    merged_urls,
                    user_id=user_id,
                    source='telegram',
                    profile_id=target_runtime_profile_id,
                )
            auto_hint = ''
            if is_new_product and target_runtime_profile_id != profile_id:
                # Fail-safe: новый дополнительный товар стартует с выключенной
                # автоценой, пока пользователь отдельно не включит её.
                storage.set_auto_mode(
                    False,
                    profile_id=target_runtime_profile_id,
                    user_id=user_id,
                    source='telegram_add_product',
                )
                auto_hint = (
                    '\n🛡️ Для нового товара автоцена выключена '
                    '(включается отдельно).'
                )
                mode_change = storage.get_last_setting_change(
                    'MODE',
                    profile_id=target_runtime_profile_id,
                )
                if mode_change is None:
                    storage.set_runtime_setting(
                        'MODE',
                        'FOLLOW',
                        user_id=user_id,
                        source='telegram_add_product',
                        profile_id=target_runtime_profile_id,
                    )
                    auto_hint += (
                        '\n🎯 Дефолтный режим для нового товара: Следование.'
                    )
            self.profile_products[profile_id] = product_id
            self._clear_pending_action(chat_id)
            await self._ensure_product_auto_name(profile_id, product_id)

            action_text = 'добавлен' if is_new_product else 'выбран'
            pair_hint = (
                f'\nПара(ы) добавлены: {len(normalized_urls)}'
                if normalized_urls else ''
            )
            await update.message.reply_text(
                (
                    f'✅ Товар {self._product_label(profile_id, product_id)} {action_text}\n'
                    'Чтобы привязать конкурента, отправь сразу:\n'
                    '<product_id> <url_конкурента>'
                    f'{pair_hint}\n'
                    f'{auto_hint}'
                    'ℹ️ Бот мониторит все товары из списка, '
                    'активный товар нужен только для редактирования.'
                ),
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'PRODUCT_ADD':
            normalized = text.strip()
            try:
                product_id = int(float(normalized.replace(',', '.')))
            except Exception:
                await update.message.reply_text(
                    '❌ Отправь корректный ID товара',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if product_id <= 0:
                await update.message.reply_text(
                    '❌ ID товара должен быть > 0',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            tracked = self._tracked_products(profile_id, runtime=runtime)
            tracked_ids = {
                int(item.get('product_id') or 0)
                for item in tracked
            }
            is_new_product = product_id not in tracked_ids
            target_runtime_profile_id = self._runtime_profile_id_for_product(
                profile_id,
                product_id,
            )
            if is_new_product:
                storage.upsert_tracked_product(
                    profile_id=profile_id,
                    product_id=product_id,
                    competitor_urls=[],
                )
                if target_runtime_profile_id != profile_id:
                    storage.set_auto_mode(
                        False,
                        profile_id=target_runtime_profile_id,
                        user_id=user_id,
                        source='telegram_add_product',
                    )
                    mode_change = storage.get_last_setting_change(
                        'MODE',
                        profile_id=target_runtime_profile_id,
                    )
                    if mode_change is None:
                        storage.set_runtime_setting(
                            'MODE',
                            'FOLLOW',
                            user_id=user_id,
                            source='telegram_add_product',
                            profile_id=target_runtime_profile_id,
                        )
            self.profile_products[profile_id] = product_id
            self._clear_pending_action(chat_id)
            await self._ensure_product_auto_name(profile_id, product_id)
            await update.message.reply_text(
                (
                    f'✅ Товар выбран: {self._product_label(profile_id, product_id)}\n'
                    'Если нужно, теперь кнопкой `🔗 Конкурент` привяжи URL конкурента.'
                ),
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'PRODUCT_ADD_URL':
            normalized = text.strip()
            raw_urls = [
                item for item in re.split(r'[\s,]+', normalized) if item.strip()
            ]
            normalized_urls = storage.normalize_competitor_urls(raw_urls)
            if not normalized_urls:
                await update.message.reply_text(
                    '❌ Не найдено валидных URL (http/https)',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            product_id = self._product_id(profile_id)
            if product_id <= 0:
                await update.message.reply_text(
                    '❌ Сначала выбери активный товар',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            tracked = self._tracked_products(profile_id, runtime=runtime)
            existing_urls = []
            for item in tracked:
                if int(item.get('product_id') or 0) == product_id:
                    existing_urls = list(item.get('competitor_urls', []) or [])
                    break
            merged_urls = storage.normalize_competitor_urls(
                existing_urls + normalized_urls
            )
            storage.upsert_tracked_product(
                profile_id=profile_id,
                product_id=product_id,
                competitor_urls=merged_urls,
            )
            storage.set_competitor_urls(
                merged_urls,
                user_id=user_id,
                source='telegram',
                profile_id=self._runtime_profile_id_for_product(
                    profile_id,
                    product_id,
                ),
            )
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                (
                    f'✅ Конкурент(ы) обновлены для {self._product_label(profile_id, product_id)}\n'
                    f'Добавлено URL: {len(normalized_urls)}'
                ),
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'PRODUCT_RENAME':
            alias_text = re.sub(r'\s+', ' ', str(text or '').strip()).strip()
            product_id = self._product_id(profile_id)
            if product_id <= 0:
                await update.message.reply_text(
                    '❌ Сначала выбери активный товар',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            if not alias_text:
                await update.message.reply_text(
                    '❌ Имя не должно быть пустым',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            self._set_product_alias(
                profile_id,
                product_id,
                alias_text,
                user_id=user_id,
                source='telegram_product_alias',
            )
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                (
                    '✅ Имя товара сохранено:\n'
                    f'{self._product_label(profile_id, product_id)}'
                ),
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'REMOVE_PRODUCT':
            normalized = text.strip()
            if not normalized:
                await update.message.reply_text(
                    '❌ Отправь ID товара, `active` или `all`',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return
            tracked_ids = self._tracked_product_ids(profile_id, runtime=runtime)
            if not tracked_ids:
                self._clear_pending_action(chat_id)
                self.profile_products[profile_id] = 0
                await update.message.reply_text(
                    'ℹ️ В профиле уже нет товаров',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                await self.send_settings(chat_id, update)
                return

            normalized_lower = normalized.lower()
            if normalized_lower in {'all', 'все'}:
                cleanup_ids = self._clear_products_with_cleanup(
                    profile_id=profile_id,
                    user_id=user_id,
                    source='telegram',
                    fallback_ids=tracked_ids,
                )
                self.profile_products[profile_id] = 0
                self._clear_pending_action(chat_id)
                await update.message.reply_text(
                    (
                        '✅ Все товары удалены:\n'
                        + ', '.join(
                            str(item)
                            for item in (cleanup_ids or tracked_ids)
                        )
                    ),
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                await self.send_settings(chat_id, update)
                return

            if normalized_lower in {'active', 'активный', 'текущий'}:
                target_product_id = self._product_id(profile_id)
            else:
                try:
                    target_product_id = int(
                        float(normalized.replace(',', '.'))
                    )
                except ValueError:
                    await update.message.reply_text(
                        '❌ Нужен ID товара (число), `active` или `all`',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return

            if target_product_id <= 0:
                await update.message.reply_text(
                    '❌ ID товара должен быть > 0',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            if target_product_id not in tracked_ids:
                await update.message.reply_text(
                    '❌ Такого товара нет в списке профиля',
                    reply_markup=self.get_settings_keyboard(profile_id),
                )
                return

            removed = self._remove_product_with_cleanup(
                profile_id=profile_id,
                product_id=target_product_id,
                user_id=user_id,
                source='telegram',
            )
            if not removed:
                if len(tracked_ids) == 1 and tracked_ids[0] == target_product_id:
                    self._clear_products_with_cleanup(
                        profile_id=profile_id,
                        user_id=user_id,
                        source='telegram',
                        fallback_ids=[target_product_id],
                    )
                else:
                    await update.message.reply_text(
                        '❌ Не удалось удалить товар',
                        reply_markup=self.get_settings_keyboard(profile_id),
                    )
                    return

            remaining_ids = self._tracked_product_ids(profile_id)
            self.profile_products[profile_id] = remaining_ids[0] if remaining_ids else 0
            self._clear_pending_action(chat_id)
            await update.message.reply_text(
                f'✅ Товар удалён: {target_product_id}',
                reply_markup=self.get_settings_keyboard(profile_id),
            )
            await self.send_settings(chat_id, update)
            return

        logger.warning(
            'Неизвестное pending действие: %s (profile=%s)',
            action,
            profile_id,
        )
        self._clear_pending_action(chat_id)
        await update.message.reply_text(
            '⚠️ Незавершённый ввод сброшен: неизвестное действие.',
            reply_markup=self.get_settings_keyboard(profile_id),
        )

    # ================================
    # Notifications
    # ================================
    async def notify(self, message: str):
        for admin_id in self.admin_ids:
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.error('Ошибка отправки уведомления admin_id=%s: %s', admin_id, e)

    async def notify_price_updated(
        self,
        old_price: float,
        new_price: float,
        competitor_price: float,
        reason: str,
        profile_name: Optional[str] = None,
    ):
        profile = profile_name or 'default'
        text = (
            '💰 *Цена обновлена*\n\n'
            f'Профиль: `{profile}`\n'
            f'Старая: `{old_price:.4f}₽`\n'
            f'Новая: `{new_price:.4f}₽`\n'
            f'Конкурент: `{competitor_price:.4f}₽`\n'
            f'Причина: `{reason}`'
        )
        await self.notify(text)

    async def notify_skip(
        self,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
        profile_name: Optional[str] = None,
    ):
        profile = profile_name or 'default'
        text = (
            '⏭️ *Пропуск обновления*\n\n'
            f'Профиль: `{profile}`\n'
            f'Текущая: `{current_price:.4f}₽`\n'
            f'Целевая: `{target_price:.4f}₽`\n'
            f'Конкурент: `{competitor_price:.4f}₽`\n'
            f'Причина: `{reason}`'
        )
        await self.notify(text)

    async def notify_error(self, error: str):
        await self.notify(f'❌ *Ошибка*\n\n`{error}`')

    async def notify_competitor_price_changed(
        self,
        old_price: float,
        new_price: float,
        delta: float,
        rank: Optional[int] = None,
        url: Optional[str] = None,
        profile_name: Optional[str] = None,
    ):
        rank_text = f'#{rank}' if rank is not None else 'N/A'
        profile = profile_name or 'default'
        text = (
            '📡 *Изменение цены конкурента*\n\n'
            f'Профиль: `{profile}`\n'
            f'Было: `{old_price:.4f}₽`\n'
            f'Стало: `{new_price:.4f}₽`\n'
            f'Δ: `{delta:.4f}₽`\n'
            f'Позиция: `{rank_text}`\n'
            f'URL: `{url or "N/A"}`'
        )
        await self.notify(text)

    async def notify_parser_issue(
        self,
        *,
        url: str,
        method: str,
        reason: str,
        error: str,
        status_code: Optional[int] = None,
        profile_name: Optional[str] = None,
    ):
        profile = profile_name or 'default'
        status = status_code if status_code is not None else 'N/A'
        text = (
            '🚫 *Проблема парсинга конкурента*\n\n'
            f'Профиль: `{profile}`\n'
            f'URL: `{url}`\n'
            f'Метод: `{method}`\n'
            f'Причина: `{reason}`\n'
            f'HTTP: `{status}`\n'
            f'Ошибка: `{error}`'
        )
        await self.notify(text)

    # ================================
    # Lifecycle
    # ================================
    async def start(self):
        app = self.app
        await app.initialize()
        await app.start()
        if app.updater:
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info('Telegram бот запущен')

    async def stop(self):
        if not self._app:
            return
        if self._app.updater and self._app.updater.running:
            await self._app.updater.stop()
        if self._app.running:
            await self._app.stop()
        await self._app.shutdown()

telegram_bot: Optional[TelegramBot] = None
