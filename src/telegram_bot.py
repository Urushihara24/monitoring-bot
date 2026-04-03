"""
Telegram бот с Reply Keyboard.
Поддерживает профильный режим (GGSEL / DIGISELLER).
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import datetime
from typing import Dict, Optional

from telegram import (
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import config
from .profile_smoke import run_profile_smoke
from .storage import DEFAULT_PROFILE, storage
from .validator import validate_runtime_config

logger = logging.getLogger(__name__)

# Главное меню
BTN_STATUS = '📊 Статус'
BTN_UP = '⬆ +0.01₽'
BTN_DOWN = '⬇ -0.01₽'
BTN_AUTO_ON = '🔔 Авто: ВКЛ'
BTN_AUTO_OFF = '🔕 Авто: ВЫКЛ'
BTN_PROFILE = '🧩 Профиль'
BTN_SETTINGS = '⚙ Настройки'
BTN_DIAGNOSTICS = '🩺 Диагностика'
BTN_BACK = '🔙 Назад'

# Настройки
BTN_PRICE = '🎯 Цена'
BTN_STEP = '➖ Шаг'
BTN_MIN = '📉 Мин'
BTN_MAX = '📈 Макс'
BTN_INTERVAL = '⏱ Интервал'
BTN_MODE = '🔀 Режим'
BTN_POSITION = '📍 Позиция'
BTN_ADD_URL = '🔗 Добавить URL'
BTN_REMOVE_URL = '🗑 Удалить URL'
BTN_HISTORY = '🧾 История'


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
        self.pending_actions: Dict[int, str] = {}
        self.chat_profile: Dict[int, str] = {}

        if api_clients is None:
            api_clients = {DEFAULT_PROFILE: api_client} if api_client else {}
        self.api_clients: Dict[str, object] = {
            k.strip().lower(): v
            for k, v in api_clients.items()
            if v is not None
        }
        self.profile_products = {
            (k or '').strip().lower(): int(v or 0)
            for k, v in (profile_products or {}).items()
        }
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

    def _resolve_profile_arg(self, value: str) -> Optional[str]:
        normalized = (value or '').strip().lower()
        if not normalized:
            return None
        aliases = {
            'gg': 'ggsel',
            'ggsel': 'ggsel',
            'digi': 'digiseller',
            'digiseller': 'digiseller',
        }
        resolved = aliases.get(normalized, normalized)
        if resolved in self.available_profiles:
            return resolved
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

    def _fmt_price(self, value) -> str:
        if value is None:
            return 'N/A'
        try:
            return f'{float(value):.4f}'
        except Exception:
            return str(value)

    # ================================
    # Keyboards
    # ================================
    def _profile_button(self, profile_id: str) -> str:
        return f'🧩 {self._profile_name(profile_id)}'

    def get_main_keyboard(self, profile_id: Optional[str] = None):
        profile = profile_id or self.default_profile
        auto_mode = self._state(profile).get('auto_mode', True)
        auto_btn = BTN_AUTO_ON if auto_mode else BTN_AUTO_OFF
        return ReplyKeyboardMarkup(
            [
                [BTN_STATUS],
                [auto_btn],
                [BTN_PROFILE, BTN_SETTINGS],
            ],
            resize_keyboard=True,
        )

    def get_settings_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_UP, BTN_DOWN],
                [BTN_PRICE, BTN_STEP],
                [BTN_MIN, BTN_MAX],
                [BTN_INTERVAL, BTN_MODE],
                [BTN_POSITION],
                [BTN_ADD_URL, BTN_REMOVE_URL],
                [BTN_HISTORY],
                [BTN_BACK],
            ],
            resize_keyboard=True,
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
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

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
        if not update.effective_chat:
            return
        await self.send_status(update.effective_chat.id, update)

    async def cmd_diag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_chat:
            return
        await self.send_diagnostics(update.effective_chat.id, update)

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
        profile_id = self._active_profile(chat_id)
        if context and context.args:
            candidate = self._resolve_profile_arg(context.args[0])
            if not candidate:
                available = ', '.join(
                    self._profile_name(pid).lower() for pid in self.available_profiles
                )
                await update.message.reply_text(
                    (
                        f'❌ Неизвестный профиль: {context.args[0]}\n'
                        f'Доступно: {available}'
                    ),
                    reply_markup=self.get_main_keyboard(profile_id),
                )
                return
            profile_id = candidate
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
        if text == BTN_UP:
            await self.handle_price_change(chat_id, 0.01, update)
            return
        if text == BTN_DOWN:
            await self.handle_price_change(chat_id, -0.01, update)
            return
        if text in (BTN_AUTO_ON, BTN_AUTO_OFF):
            await self.toggle_auto(update)
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
        if text == BTN_DIAGNOSTICS:
            await self.send_diagnostics(chat_id, update)
            return

        # Выбор профиля
        for pid in self.available_profiles:
            if text == self._profile_button(pid):
                self._set_profile(chat_id, pid)
                await update.message.reply_text(
                    f'✅ Активный профиль: {self._profile_name(pid)}',
                    reply_markup=self.get_main_keyboard(pid),
                )
                return

        # Настройки
        if text == BTN_PRICE:
            self.pending_actions[chat_id] = 'DESIRED_PRICE'
            await update.message.reply_text(
                'Введи желаемую цену (например 0.35):',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        if text == BTN_STEP:
            self.pending_actions[chat_id] = 'UNDERCUT_VALUE'
            await update.message.reply_text(
                'Введи шаг снижения (например 0.0051):',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        if text == BTN_MIN:
            self.pending_actions[chat_id] = 'MIN_PRICE'
            await update.message.reply_text(
                'Введи минимальную цену:',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        if text == BTN_MAX:
            self.pending_actions[chat_id] = 'MAX_PRICE'
            await update.message.reply_text(
                'Введи максимальную цену:',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        if text == BTN_INTERVAL:
            self.pending_actions[chat_id] = 'CHECK_INTERVAL'
            runtime = self._runtime(profile_id)
            await update.message.reply_text(
                (
                    'Введи интервал проверки в секундах '
                    f'({runtime.FAST_CHECK_INTERVAL_MIN}..'
                    f'{runtime.FAST_CHECK_INTERVAL_MAX}):'
                ),
                reply_markup=self.get_settings_keyboard(),
            )
            return
        if text == BTN_MODE:
            await self.toggle_mode(chat_id, user_id, update)
            return
        if text == BTN_POSITION:
            await self.toggle_position_filter(chat_id, user_id, update)
            return
        if text == BTN_ADD_URL:
            self.pending_actions[chat_id] = 'ADD_URL'
            await update.message.reply_text(
                'Отправь URL конкурента:',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        if text == BTN_REMOVE_URL:
            await self.start_remove_url(chat_id, update)
            return
        if text == BTN_HISTORY:
            await self.show_settings_history(chat_id, update)
            return
        if text == BTN_BACK:
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                '📋 Главное меню',
                reply_markup=self.get_main_keyboard(profile_id),
            )
            return

        if chat_id in self.pending_actions:
            await self.handle_pending_action(chat_id, user_id, text, update)
            return

        await update.message.reply_text(
            'Используй кнопки 👇',
            reply_markup=self.get_main_keyboard(profile_id),
        )

    # ================================
    # Status and diagnostics
    # ================================
    async def send_status(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        profile_name = self._profile_name(profile_id)
        state = self._state(profile_id)
        runtime = self._runtime(profile_id)

        competitor_rank = state.get('last_competitor_rank')
        competitor_info = f'#{competitor_rank}' if competitor_rank else 'N/A'
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

        my_price = state.get('last_target_price')
        if my_price is None:
            my_price = state.get('last_price')
        competitor_price = state.get('last_competitor_min')
        my_price_str = f'{my_price:.4f}' if my_price is not None else 'N/A'
        competitor_price_str = (
            f'{competitor_price:.4f}'
            if competitor_price is not None else 'N/A'
        )

        text = f"""📊 Статус

🧩 Профиль: {profile_name}
💰 Моя цена: {my_price_str}₽
📈 Цена конкурента: {competitor_price_str}₽
🔍 Позиция: {competitor_info}
🔗 URL: {competitor_url}
🧪 Метод парсинга: {parse_method}
🕓 Последний парс: {parse_at_str}
📡 Мониторинг: {monitor_mode}

🔔 Авто: {'ВКЛ' if state.get('auto_mode', True) else 'ВЫКЛ'}
🎯 Режим: {runtime.MODE}
🕐 Обновление: {update_str}
⏲️ Интервал: {runtime.CHECK_INTERVAL}s

📊 Обновлений: {state.get('update_count', 0)}
⏭️ Пропусков: {state.get('skip_count', 0)}
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
        runtime = self._runtime(profile_id)
        monitor_enabled = bool(runtime.COMPETITOR_URLS)
        monitor_mode = (
            f'АКТИВЕН ({len(runtime.COMPETITOR_URLS)} URL)'
            if monitor_enabled
            else 'ВЫКЛ (нет URL)'
        )

        text = f"""⚙️ Настройки

🧩 Профиль: {profile_name}
📉 MIN: {runtime.MIN_PRICE:.4f}₽
📈 MAX: {runtime.MAX_PRICE:.4f}₽
🎯 Желаемая: {runtime.DESIRED_PRICE:.4f}₽
↘️ Шаг: {runtime.UNDERCUT_VALUE:.4f}

🔹 Режим: {runtime.MODE}
   - FIXED: {runtime.FIXED_PRICE:.4f}₽
   - STEP_UP: {runtime.STEP_UP_VALUE:.4f}₽

⏱️ CHECK_INTERVAL: {runtime.CHECK_INTERVAL}s
⛑️ MAX_DOWN_STEP: {runtime.MAX_DOWN_STEP:.4f}₽
🚀 FAST_REBOUND_DELTA: {runtime.FAST_REBOUND_DELTA:.4f}₽
🔁 Обновлять только при изменении конкурента: {'Да' if runtime.UPDATE_ONLY_ON_COMPETITOR_CHANGE else 'Нет'}
📍 Позиция: {'Вкл' if runtime.POSITION_FILTER_ENABLED else 'Выкл'}
📡 Мониторинг: {monitor_mode}
🔗 Конкурентов: {len(runtime.COMPETITOR_URLS)}
"""
        await update.message.reply_text(
            text,
            reply_markup=self.get_settings_keyboard(),
        )

    async def send_diagnostics(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        profile_name = self._profile_name(profile_id)
        state = self._state(profile_id)
        runtime = self._runtime(profile_id)
        is_valid, errors = validate_runtime_config(runtime)

        api_ok = False
        product_price = None
        product_ok = False
        client = self._api_client(profile_id)
        product_id = self._product_id(profile_id)
        if client:
            try:
                api_ok = await asyncio.to_thread(client.check_api_access)
                if api_ok and product_id:
                    product = await asyncio.to_thread(client.get_product, product_id)
                    product_ok = product is not None
                    product_price = product.price if product else None
            except Exception as e:
                logger.error('Ошибка API в диагностике: %s', e)

        perms_line = None
        if profile_id == 'digiseller' and client and hasattr(
            client,
            'get_token_perms_status',
        ):
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
        runtime = self._runtime(profile_id)
        state = self._state(profile_id)
        client = self._api_client(profile_id)
        product_id = self._product_id(profile_id)
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
                profile_id=profile_id,
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
        state = self._state(profile_id)
        new_auto = not state.get('auto_mode', True)
        storage.update_state(profile_id=profile_id, auto_mode=new_auto)
        await update.message.reply_text(
            f'🔔 Авто: {"ВКЛ" if new_auto else "ВЫКЛ"}',
            reply_markup=self.get_main_keyboard(profile_id),
        )

    async def toggle_mode(self, chat_id: int, user_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        new_mode = 'STEP_UP' if runtime.MODE == 'FIXED' else 'FIXED'
        storage.set_runtime_setting(
            'MODE',
            new_mode,
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            f'✅ Режим: {new_mode}',
            reply_markup=self.get_settings_keyboard(),
        )
        await self.send_settings(chat_id, update)

    async def toggle_position_filter(self, chat_id: int, user_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)
        new_value = not runtime.POSITION_FILTER_ENABLED
        storage.set_runtime_setting(
            'POSITION_FILTER_ENABLED',
            'true' if new_value else 'false',
            user_id=user_id,
            source='telegram',
            profile_id=profile_id,
        )
        await update.message.reply_text(
            f'✅ Позиция: {"Вкл" if new_value else "Выкл"}',
            reply_markup=self.get_settings_keyboard(),
        )
        await self.send_settings(chat_id, update)

    async def start_remove_url(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        urls = storage.get_competitor_urls(
            self.profile_default_urls.get(profile_id, []),
            profile_id=profile_id,
        )
        if not urls:
            await update.message.reply_text(
                'Список пуст',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        self.pending_actions[chat_id] = 'REMOVE_URL'
        lines = ['Удали номер URL:'] + [f'{i}. {u}' for i, u in enumerate(urls, 1)]
        await update.message.reply_text(
            '\n'.join(lines),
            reply_markup=self.get_settings_keyboard(),
        )

    async def show_settings_history(self, chat_id: int, update: Update):
        if not update.message:
            return
        profile_id = self._active_profile(chat_id)
        rows = storage.get_settings_history(limit=15, profile_id=profile_id)
        if not rows:
            await update.message.reply_text(
                'История пуста',
                reply_markup=self.get_settings_keyboard(),
            )
            return
        lines = [f'История ({self._profile_name(profile_id)}):'] + [
            (
                f"{r['timestamp']} | {r['key']}: "
                f"{r['old_value']} → {r['new_value']}"
            )
            for r in rows
        ]
        await update.message.reply_text(
            '\n'.join(lines),
            reply_markup=self.get_settings_keyboard(),
        )

    async def handle_pending_action(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        update: Update,
    ):
        if not update.message:
            return
        action = self.pending_actions.get(chat_id)
        if not action:
            return
        profile_id = self._active_profile(chat_id)
        runtime = self._runtime(profile_id)

        if action in {'DESIRED_PRICE', 'UNDERCUT_VALUE', 'MIN_PRICE', 'MAX_PRICE'}:
            try:
                value = float(text.replace(',', '.'))
            except ValueError:
                await update.message.reply_text(
                    '❌ Введи число',
                    reply_markup=self.get_settings_keyboard(),
                )
                return
            if value <= 0:
                await update.message.reply_text(
                    '❌ Значение должно быть > 0',
                    reply_markup=self.get_settings_keyboard(),
                )
                return
            value = round(value, 4)
            storage.set_runtime_setting(
                action,
                str(value),
                user_id=user_id,
                source='telegram',
                profile_id=profile_id,
            )
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                f'✅ {action} = {value:.4f}',
                reply_markup=self.get_settings_keyboard(),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'CHECK_INTERVAL':
            try:
                value = int(float(text.replace(',', '.')))
            except ValueError:
                await update.message.reply_text(
                    '❌ Введи целое число секунд',
                    reply_markup=self.get_settings_keyboard(),
                )
                return
            if value < runtime.FAST_CHECK_INTERVAL_MIN or (
                value > runtime.FAST_CHECK_INTERVAL_MAX
            ):
                await update.message.reply_text(
                    (
                        '❌ Интервал должен быть в диапазоне '
                        f'{runtime.FAST_CHECK_INTERVAL_MIN}..'
                        f'{runtime.FAST_CHECK_INTERVAL_MAX} секунд'
                    ),
                    reply_markup=self.get_settings_keyboard(),
                )
                return
            storage.set_runtime_setting(
                'CHECK_INTERVAL',
                str(value),
                user_id=user_id,
                source='telegram',
                profile_id=profile_id,
            )
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                f'✅ CHECK_INTERVAL = {value}s',
                reply_markup=self.get_settings_keyboard(),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'ADD_URL':
            if not text.startswith('http'):
                await update.message.reply_text(
                    '❌ Нужен URL',
                    reply_markup=self.get_settings_keyboard(),
                )
                return
            urls = storage.get_competitor_urls(
                self.profile_default_urls.get(profile_id, []),
                profile_id=profile_id,
            )
            if text not in urls:
                urls.append(text)
                storage.set_competitor_urls(
                    urls,
                    user_id=user_id,
                    source='telegram',
                    profile_id=profile_id,
                )
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                '✅ URL добавлен',
                reply_markup=self.get_settings_keyboard(),
            )
            await self.send_settings(chat_id, update)
            return

        if action == 'REMOVE_URL':
            try:
                idx = int(text) - 1
            except ValueError:
                await update.message.reply_text(
                    '❌ Введи номер',
                    reply_markup=self.get_settings_keyboard(),
                )
                return
            urls = storage.get_competitor_urls(
                self.profile_default_urls.get(profile_id, []),
                profile_id=profile_id,
            )
            if 0 <= idx < len(urls):
                removed = urls.pop(idx)
                storage.set_competitor_urls(
                    urls,
                    user_id=user_id,
                    source='telegram',
                    profile_id=profile_id,
                )
                self.pending_actions.pop(chat_id, None)
                await update.message.reply_text(
                    f'✅ Удалён: {removed}',
                    reply_markup=self.get_settings_keyboard(),
                )
                await self.send_settings(chat_id, update)
            return

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
