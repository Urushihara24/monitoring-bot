"""
Telegram бот с Reply Keyboard (кнопки внизу)
Чистая структура с полным функционалом
"""

import logging
import re
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .config import config
from .storage import storage
from .validator import validate_runtime_config

logger = logging.getLogger(__name__)


# ===== КНОПКИ: ГЛАВНОЕ МЕНЮ =====
BTN_STATUS = "📊 Статус"
BTN_UP = "⬆ +0.01₽"  # унифицированный текст (без вариационного селектора)
BTN_DOWN = "⬇ -0.01₽"
BTN_AUTO_ON = "🔔 Авто: ВКЛ"
BTN_AUTO_OFF = "🔕 Авто: ВЫКЛ"
BTN_SETTINGS = "⚙ Настройки"
BTN_DIAGNOSTICS = "🩺 Диагностика"
BTN_BACK = "🔙 Назад"

# ===== КНОПКИ: НАСТРОЙКИ =====
BTN_PRICE = "🎯 Цена"
BTN_STEP = "➖ Шаг"
BTN_MIN = "📉 Мин"
BTN_MAX = "📈 Макс"
BTN_MODE = "🔀 Режим"
BTN_POSITION = "📍 Позиция"
BTN_ADD_URL = "🔗 Добавить URL"
BTN_REMOVE_URL = "🗑 Удалить URL"
BTN_EXPORT = "📤 Экспорт"
BTN_IMPORT = "📥 Импорт"
BTN_HISTORY = "🧾 История"


class TelegramBot:
    """Telegram бот с Reply Keyboard"""

    def __init__(self, api_client=None):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.admin_ids = set(config.TELEGRAM_ADMIN_IDS)  # для быстрой проверки
        self.api_client = api_client
        self._app: Optional[Application] = None
        self.pending_actions: Dict[int, str] = {}  # chat_id -> action
        # Убираем self.auto_mode – будем всегда брать актуальное из storage

    # ===== КЛАВИАТУРЫ =====
    def get_main_keyboard(self):
        """Главная клавиатура с актуальным состоянием авторежима"""
        auto_mode = storage.get_state().get("auto_mode", True)
        auto_btn = BTN_AUTO_ON if auto_mode else BTN_AUTO_OFF
        return ReplyKeyboardMarkup(
            [
                [BTN_STATUS],
                [BTN_UP, BTN_DOWN],
                [auto_btn],
                [BTN_SETTINGS, BTN_DIAGNOSTICS],
            ],
            resize_keyboard=True,
        )

    def get_settings_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_PRICE, BTN_STEP],
                [BTN_MIN, BTN_MAX],
                [BTN_MODE, BTN_POSITION],
                [BTN_ADD_URL, BTN_REMOVE_URL],
                [BTN_EXPORT, BTN_IMPORT],
                [BTN_HISTORY],
                [BTN_BACK],
            ],
            resize_keyboard=True,
        )

    # ===== INIT APP =====
    @property
    def app(self):
        if self._app is None:
            self._app = Application.builder().token(self.bot_token).build()
            self._setup_handlers()
        return self._app

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

    # ===== ACCESS =====
    def _check_access(self, user_id: int) -> bool:
        if user_id not in self.admin_ids:
            logger.warning(f"Доступ запрещён для user_id={user_id}")
            return False
        return True

    def _runtime(self):
        return storage.get_runtime_config(config)

    # ===== COMMANDS =====
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.message:
            return
        user_id = update.effective_user.id
        if not self._check_access(user_id):
            # Неавторизованным не показываем клавиатуру
            await update.message.reply_text(
                "❌ Нет доступа", reply_markup=ReplyKeyboardRemove()
            )
            return
        await update.message.reply_text(
            "👋 Бот запущен\nВыбери действие:", reply_markup=self.get_main_keyboard()
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat:
            await self.send_status(update.effective_chat.id, update)

    # ===== MESSAGE HANDLER =====
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat or not update.message:
            return
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        text = update.message.text or ""

        # Нормализация текста (убираем variation selectors и прочее)
        import unicodedata

        text_clean = unicodedata.normalize("NFKC", text)
        for ch in ("\ufe0f", "\ufe0e", "\u200d", "\u200b"):
            text_clean = text_clean.replace(ch, "")

        logger.info(f"Получено: {text!r} → {text_clean!r}")

        if not self._check_access(user_id):
            await update.message.reply_text(
                "❌ Нет доступа", reply_markup=ReplyKeyboardRemove()
            )
            return

        # ===== ГЛАВНОЕ МЕНЮ (сравниваем только нормализованный текст) =====
        if text_clean == BTN_STATUS:
            await self.send_status(chat_id, update)

        elif text_clean == BTN_UP:
            await self.handle_price_change(chat_id, 0.01, update)

        elif text_clean == BTN_DOWN:
            await self.handle_price_change(chat_id, -0.01, update)

        elif text_clean in (BTN_AUTO_ON, BTN_AUTO_OFF):
            await self.toggle_auto(update)

        elif text_clean == BTN_SETTINGS:
            await self.send_settings(chat_id, update)

        elif text_clean == BTN_DIAGNOSTICS:
            await self.send_diagnostics(chat_id, update)

        # ===== НАСТРОЙКИ =====
        elif text_clean == BTN_PRICE:
            self.pending_actions[chat_id] = "DESIRED_PRICE"
            await update.message.reply_text(
                "Введи желаемую цену (например 0.35):",
                reply_markup=self.get_settings_keyboard(),
            )

        elif text_clean == BTN_STEP:
            self.pending_actions[chat_id] = "UNDERCUT_VALUE"
            await update.message.reply_text(
                "Введи шаг снижения (например 0.0051):",
                reply_markup=self.get_settings_keyboard(),
            )

        elif text_clean == BTN_MIN:
            self.pending_actions[chat_id] = "MIN_PRICE"
            await update.message.reply_text(
                "Введи минимальную цену:", reply_markup=self.get_settings_keyboard()
            )

        elif text_clean == BTN_MAX:
            self.pending_actions[chat_id] = "MAX_PRICE"
            await update.message.reply_text(
                "Введи максимальную цену:", reply_markup=self.get_settings_keyboard()
            )

        elif text_clean == BTN_MODE:
            await self.toggle_mode(chat_id, user_id, update)

        elif text_clean == BTN_POSITION:
            await self.toggle_position_filter(chat_id, user_id, update)

        elif text_clean == BTN_ADD_URL:
            self.pending_actions[chat_id] = "ADD_URL"
            await update.message.reply_text(
                "Отправь URL конкурента:", reply_markup=self.get_settings_keyboard()
            )

        elif text_clean == BTN_REMOVE_URL:
            await self.start_remove_url(chat_id, update)

        elif text_clean == BTN_EXPORT:
            await self.export_settings(chat_id, update)

        elif text_clean == BTN_IMPORT:
            self.pending_actions[chat_id] = "IMPORT_SETTINGS"
            await update.message.reply_text(
                "Отправь настройки в формате key=value\nПример:\nMIN_PRICE=0.25\nMAX_PRICE=10",
                reply_markup=self.get_settings_keyboard(),
            )

        elif text_clean == BTN_HISTORY:
            await self.show_settings_history(chat_id, update)

        elif text_clean == BTN_BACK:
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                "📋 Главное меню", reply_markup=self.get_main_keyboard()
            )

        # ===== PENDING ACTIONS =====
        elif chat_id in self.pending_actions:
            await self.handle_pending_action(chat_id, user_id, text_clean, update)

        else:
            logger.warning(f"❌ Нераспознанная кнопка: {text!r} (clean={text_clean!r})")
            await update.message.reply_text(
                "Используй кнопки 👇", reply_markup=self.get_main_keyboard()
            )

    # ===== STATUS =====
    async def send_status(self, chat_id: int, update: Update):
        if not update.message:
            return
        state = storage.get_state()
        runtime = self._runtime()
        auto_mode = state.get("auto_mode", True)  # берём актуальное

        competitor_info = "N/A"
        if state.get("last_competitor_min"):
            rank = state.get("last_competitor_rank")
            competitor_info = f"#{rank}" if rank else "N/A"

        last_update = state.get("last_update")
        update_str = last_update.strftime("%Y-%m-%d %H:%M") if last_update else "Никогда"

        text = f"""📊 Статус

💰 Моя цена: {state.get('last_price') or 'N/A'}₽
📈 Цена конкурента: {state.get('last_competitor_min') or 'N/A'}₽
🔍 Позиция: {competitor_info}

🔔 Авто: {'ВКЛ' if auto_mode else 'ВЫКЛ'}
🎯 Режим: {runtime.MODE}
🕐 Обновление: {update_str}

📊 Обновлений: {state.get('update_count', 0)}
⏭️ Пропусков: {state.get('skip_count', 0)}
"""
        await update.message.reply_text(text, reply_markup=self.get_main_keyboard())

    # ===== SETTINGS =====
    async def send_settings(self, chat_id: int, update: Update):
        if not update.message:
            return
        runtime = self._runtime()
        text = f"""⚙️ Настройки

📉 MIN: {runtime.MIN_PRICE}₽
📈 MAX: {runtime.MAX_PRICE}₽
🎯 Желаемая: {runtime.DESIRED_PRICE}₽
↘️ Шаг: {runtime.UNDERCUT_VALUE}

🔹 Режим: {runtime.MODE}
   - FIXED: {runtime.FIXED_PRICE}₽
   - STEP_UP: {runtime.STEP_UP_VALUE}₽

🚫 Слабый конкурент: {runtime.LOW_PRICE_THRESHOLD or 'Выкл'}
📍 Фильтр позиции: {'Вкл' if runtime.POSITION_FILTER_ENABLED else 'Выкл'}
⏱️ Cooldown: {runtime.COOLDOWN_SECONDS}с
🔗 Конкурентов: {len(runtime.COMPETITOR_URLS)}
"""
        await update.message.reply_text(text, reply_markup=self.get_settings_keyboard())

    # ===== DIAGNOSTICS =====
    async def send_diagnostics(self, chat_id: int, update: Update):
        if not update.message:
            return
        state = storage.get_state()
        runtime = self._runtime()
        is_valid, errors = validate_runtime_config(runtime)

        api_ok = False
        product_price = None
        if self.api_client:
            try:
                api_ok = await asyncio.to_thread(self.api_client.check_api_access)
                if api_ok:
                    product = await asyncio.to_thread(
                        self.api_client.get_product, config.GGSEL_PRODUCT_ID
                    )
                    product_price = product.price if product else None
            except Exception as e:
                logger.error(f"Ошибка API в диагностике: {e}")
                api_ok = False

        now = datetime.now()
        last_cycle = state.get("last_cycle")
        age = int((now - last_cycle).total_seconds()) if last_cycle else 0

        lines = [
            "🩺 Диагностика",
            "",
            f'API: {"OK" if api_ok else "FAIL"}',
            f'Product: {"OK" if product_price else "FAIL"} ({product_price}₽)',
            f'Config: {"OK" if is_valid else "INVALID"}',
            f"Heartbeat: {age}s",
            f'Auto: {"ON" if state.get("auto_mode", True) else "OFF"}',
            f"Competitors: {len(runtime.COMPETITOR_URLS)}",
        ]
        if errors:
            lines.append("Errors: " + "; ".join(errors[:3]))

        text = "\n".join(lines)
        await update.message.reply_text(text, reply_markup=self.get_main_keyboard())

    # ===== PRICE CHANGE =====
    async def handle_price_change(self, chat_id: int, delta: float, update: Update):
        if not update.message:
            return
        runtime = self._runtime()
        state = storage.get_state()
        current_price = state.get("last_price")

        if not current_price and self.api_client:
            try:
                current_price = await asyncio.to_thread(
                    self.api_client.get_my_price, config.GGSEL_PRODUCT_ID
                )
            except Exception as e:
                logger.error(f"Ошибка получения текущей цены: {e}")
                await update.message.reply_text(
                    "❌ Ошибка получения цены", reply_markup=self.get_main_keyboard()
                )
                return

        if not current_price:
            await update.message.reply_text(
                "❌ Нет цены", reply_markup=self.get_main_keyboard()
            )
            return

        new_price = round(max(current_price + delta, runtime.MIN_PRICE), 4)

        if new_price == current_price:
            await update.message.reply_text(
                f"⚠️ Минимум {runtime.MIN_PRICE}₽", reply_markup=self.get_main_keyboard()
            )
            return

        if self.api_client:
            try:
                success = await asyncio.to_thread(
                    self.api_client.update_price, config.GGSEL_PRODUCT_ID, new_price
                )
                if success:
                    storage.update_state(
                        last_price=new_price, last_update=datetime.now()
                    )
                    await update.message.reply_text(
                        f"✅ {current_price:.4f}₽ → {new_price:.4f}₽",
                        reply_markup=self.get_main_keyboard(),
                    )
                else:
                    await update.message.reply_text(
                        "❌ Ошибка API", reply_markup=self.get_main_keyboard()
                    )
            except Exception as e:
                logger.error(f"Ошибка обновления цены: {e}")
                await update.message.reply_text(
                    "❌ Ошибка API", reply_markup=self.get_main_keyboard()
                )
        else:
            await update.message.reply_text(
                "❌ Нет API клиента", reply_markup=self.get_main_keyboard()
            )

    # ===== AUTO MODE =====
    async def toggle_auto(self, update: Update):
        if not update.message:
            return
        state = storage.get_state()
        new_auto = not state.get("auto_mode", True)
        storage.update_state(auto_mode=new_auto)
        status = "ВКЛ" if new_auto else "ВЫКЛ"
        await update.message.reply_text(
            f"🔔 Авто {status}", reply_markup=self.get_main_keyboard()
        )

    # ===== MODE TOGGLE =====
    async def toggle_mode(self, chat_id: int, user_id: int, update: Update):
        if not update.message:
            return
        runtime = self._runtime()
        new_mode = "STEP_UP" if runtime.MODE == "FIXED" else "FIXED"
        storage.set_runtime_setting(
            "MODE", new_mode, user_id=user_id, source="telegram"
        )
        await update.message.reply_text(
            f"✅ Режим: {new_mode}", reply_markup=self.get_settings_keyboard()
        )
        await self.send_settings(chat_id, update)

    # ===== POSITION FILTER =====
    async def toggle_position_filter(self, chat_id: int, user_id: int, update: Update):
        if not update.message:
            return
        runtime = self._runtime()
        new_value = not runtime.POSITION_FILTER_ENABLED
        storage.set_runtime_setting(
            "POSITION_FILTER_ENABLED",
            "true" if new_value else "false",
            user_id=user_id,
            source="telegram",
        )
        await update.message.reply_text(
            f'✅ Позиция: {"Вкл" if new_value else "Выкл"}',
            reply_markup=self.get_settings_keyboard(),
        )
        await self.send_settings(chat_id, update)

    # ===== REMOVE URL =====
    async def start_remove_url(self, chat_id: int, update: Update):
        if not update.message:
            return
        urls = storage.get_competitor_urls(config.COMPETITOR_URLS)
        if not urls:
            await update.message.reply_text(
                "Список пуст", reply_markup=self.get_settings_keyboard()
            )
            return
        lines = ["Удали номер URL:"] + [f"{i}. {u}" for i, u in enumerate(urls, 1)]
        self.pending_actions[chat_id] = "REMOVE_URL"
        await update.message.reply_text(
            "\n".join(lines), reply_markup=self.get_settings_keyboard()
        )

    # ===== EXPORT =====
    async def export_settings(self, chat_id: int, update: Update):
        if not update.message:
            return
        settings = storage.get_all_runtime_settings()
        if not settings:
            await update.message.reply_text(
                "Настройки пусты (используется .env)",
                reply_markup=self.get_settings_keyboard(),
            )
            return
        lines = ["Настройки:"] + [f"{k}={v}" for k, v in sorted(settings.items())]
        await update.message.reply_text(
            "\n".join(lines), reply_markup=self.get_settings_keyboard()
        )

    # ===== HISTORY =====
    async def show_settings_history(self, chat_id: int, update: Update):
        if not update.message:
            return
        rows = storage.get_settings_history(limit=15)
        if not rows:
            await update.message.reply_text(
                "История пуста", reply_markup=self.get_settings_keyboard()
            )
            return
        lines = ["История:"] + [
            f"{r['timestamp']} | {r['key']}: {r['old_value']} → {r['new_value']}"
            for r in rows
        ]
        await update.message.reply_text(
            "\n".join(lines), reply_markup=self.get_settings_keyboard()
        )

    # ===== NOTIFICATIONS =====
    async def notify(self, message: str):
        """Уведомление всем администраторам (без клавиатуры, чтобы не сбивать контекст)"""
        for admin_id in self.admin_ids:
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    # Не передаём reply_markup, чтобы не менять текущую клавиатуру пользователя
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления admin_id={admin_id}: {e}")

    async def notify_price_updated(
        self,
        old_price: float,
        new_price: float,
        competitor_price: float,
        reason: str,
    ):
        text = (
            "💰 *Цена обновлена*\n\n"
            f"Старая: `{old_price:.4f}₽`\n"
            f"Новая: `{new_price:.4f}₽`\n"
            f"Конкурент: `{competitor_price:.4f}₽`\n"
            f"Причина: `{reason}`"
        )
        await self.notify(text)

    async def notify_skip(
        self,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
    ):
        text = (
            "⏭️ *Пропуск обновления*\n\n"
            f"Текущая: `{current_price:.4f}₽`\n"
            f"Целевая: `{target_price:.4f}₽`\n"
            f"Конкурент: `{competitor_price:.4f}₽`\n"
            f"Причина: `{reason}`"
        )
        await self.notify(text)

    async def notify_error(self, error: str):
        await self.notify(f"❌ *Ошибка*\n\n`{error}`")

    async def notify_competitor_price_changed(
        self,
        old_price: float,
        new_price: float,
        delta: float,
        rank: Optional[int] = None,
    ):
        rank_text = f"`#{rank}`" if rank is not None else "`N/A`"
        text = (
            "📡 *Изменение цены конкурента*\n\n"
            f"Было: `{old_price:.4f}₽`\n"
            f"Стало: `{new_price:.4f}₽`\n"
            f"Δ: `{delta:.4f}₽`\n"
            f"Позиция: {rank_text}"
        )
        await self.notify(text)

    async def notify_startup(self):
        runtime = self._runtime()
        text = (
            "🚀 *Auto-Pricing Bot запущен*\n\n"
            f"Товар: `{config.GGSEL_PRODUCT_ID}`\n"
            f"Конкурентов: `{len(runtime.COMPETITOR_URLS)}`\n"
            f"Интервал: `{runtime.CHECK_INTERVAL}s`"
        )
        await self.notify(text)

    # ===== PENDING ACTIONS =====
    async def handle_pending_action(
        self, chat_id: int, user_id: int, text: str, update: Update
    ):
        if not update.message:
            return
        action = self.pending_actions.get(chat_id)
        if not action:
            return

        if action in {"DESIRED_PRICE", "UNDERCUT_VALUE", "MIN_PRICE", "MAX_PRICE"}:
            try:
                value = float(text.replace(",", "."))
            except ValueError:
                await update.message.reply_text(
                    "❌ Введи число", reply_markup=self.get_settings_keyboard()
                )
                return
            if value <= 0:
                await update.message.reply_text(
                    "❌ > 0", reply_markup=self.get_settings_keyboard()
                )
                return
            storage.set_runtime_setting(
                action, str(value), user_id=user_id, source="telegram"
            )
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                f"✅ {action} = {value}", reply_markup=self.get_settings_keyboard()
            )
            await self.send_settings(chat_id, update)

        elif action == "ADD_URL":
            if not text.startswith("http"):
                await update.message.reply_text(
                    "❌ Нужен URL", reply_markup=self.get_settings_keyboard()
                )
                return
            urls = storage.get_competitor_urls(config.COMPETITOR_URLS)
            if text not in urls:
                urls.append(text)
                storage.set_competitor_urls(urls, user_id=user_id, source="telegram")
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                "✅ URL добавлен", reply_markup=self.get_settings_keyboard()
            )
            await self.send_settings(chat_id, update)

        elif action == "REMOVE_URL":
            try:
                idx = int(text) - 1
            except ValueError:
                await update.message.reply_text(
                    "❌ Введи номер", reply_markup=self.get_settings_keyboard()
                )
                return
            urls = storage.get_competitor_urls(config.COMPETITOR_URLS)
            if 0 <= idx < len(urls):
                removed = urls.pop(idx)
                storage.set_competitor_urls(urls, user_id=user_id, source="telegram")
                self.pending_actions.pop(chat_id, None)
                await update.message.reply_text(
                    f"✅ Удалён: {removed}", reply_markup=self.get_settings_keyboard()
                )
                await self.send_settings(chat_id, update)

        elif action == "IMPORT_SETTINGS":
            allowed = {
                "MIN_PRICE",
                "MAX_PRICE",
                "DESIRED_PRICE",
                "UNDERCUT_VALUE",
                "MODE",
                "FIXED_PRICE",
                "STEP_UP_VALUE",
                "LOW_PRICE_THRESHOLD",
                "WEAK_PRICE_CEIL_LIMIT",
                "POSITION_FILTER_ENABLED",
                "WEAK_POSITION_THRESHOLD",
                "COOLDOWN_SECONDS",
                "IGNORE_DELTA",
                "CHECK_INTERVAL",
                "COMPETITOR_COOKIES",
            }
            imported = 0
            for line in text.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in allowed:
                        # Простая валидация типов
                        if k in {
                            "MIN_PRICE",
                            "MAX_PRICE",
                            "DESIRED_PRICE",
                            "UNDERCUT_VALUE",
                            "FIXED_PRICE",
                            "STEP_UP_VALUE",
                            "LOW_PRICE_THRESHOLD",
                            "WEAK_PRICE_CEIL_LIMIT",
                            "WEAK_POSITION_THRESHOLD",
                            "COOLDOWN_SECONDS",
                            "IGNORE_DELTA",
                            "CHECK_INTERVAL",
                        }:
                            try:
                                float(v)
                            except ValueError:
                                continue
                        elif k in {"POSITION_FILTER_ENABLED"}:
                            if v.lower() not in ("true", "false", "1", "0"):
                                continue
                        storage.set_runtime_setting(
                            k, v.strip(), user_id=user_id, source="telegram"
                        )
                        imported += 1
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                f"✅ Импорт завершён (импортировано {imported})",
                reply_markup=self.get_settings_keyboard(),
            )
            await self.send_settings(chat_id, update)

    # ===== START / STOP =====
    async def start(self):
        app = self.app
        await app.initialize()
        await app.start()
        if app.updater:
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram бот запущен")

    async def stop(self):
        if self._app:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()


# Глобальный экземпляр (можно оставить, но лучше использовать dependency injection)
telegram_bot: Optional[TelegramBot] = None
