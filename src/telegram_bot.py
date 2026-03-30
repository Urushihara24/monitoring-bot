"""
Telegram бот с Reply Keyboard (кнопки внизу)
"""

import logging
import re
import asyncio
from datetime import datetime
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup
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


class TelegramBot:
    """Telegram бот с кнопками внизу"""

    def __init__(self, api_client=None):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.admin_ids = config.TELEGRAM_ADMIN_IDS
        self.api_client = api_client
        self._app: Optional[Application] = None
        self.auto_mode = bool(storage.get_state().get('auto_mode', True))
        self.pending_actions = {}

        # Главное меню
        self.main_keyboard = ReplyKeyboardMarkup([
            ['📊 Статус'],
            ['⬆️ +0.01₽', '⬇️ -0.01₽'],
            ['🔔 Авто: ВКЛ' if self.auto_mode else '🔕 Авто: ВЫКЛ'],
            ['⚙️ Настройки', '🩺 Диагностика'],
        ], resize_keyboard=True, one_time_keyboard=False)

        # Меню настроек
        self.settings_keyboard = ReplyKeyboardMarkup([
            ['🎯 Цена', '➖ Шаг'],
            ['📉 Мин', '📈 Макс'],
            ['🔀 Режим', '📍 Позиция'],
            ['🔗 Добавить URL', '🗑 Удалить URL'],
            ['📤 Экспорт', '📥 Импорт'],
            ['🧾 История'],
            ['🔙 Назад'],
        ], resize_keyboard=True, one_time_keyboard=False)

    @property
    def app(self) -> Application:
        """Ленивая инициализация приложения"""
        if self._app is None:
            self._app = Application.builder().token(self.bot_token).build()
            self._setup_handlers()
        return self._app

    def _setup_handlers(self):
        """Настройка обработчиков"""
        self.app.add_handler(CommandHandler('start', self.cmd_start))
        self.app.add_handler(CommandHandler('status', self.cmd_status))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    def _check_access(self, user_id: int) -> bool:
        """Проверка доступа"""
        if user_id not in self.admin_ids:
            logger.warning(f'Доступ запрещён для user_id={user_id}')
            return False
        return True

    async def _reply_with_main_keyboard(self, update: Update, text: str):
        """Ответ в текущий чат с основной Reply клавиатурой"""
        if update.message:
            await update.message.reply_text(text, reply_markup=self.main_keyboard)

    async def _send_with_main_keyboard(self, chat_id: int, text: str):
        """Отправка в чат с основной Reply клавиатурой"""
        await self.app.bot.send_message(chat_id=chat_id, text=text, reply_markup=self.main_keyboard)

    async def _send_with_settings_keyboard(self, chat_id: int, text: str):
        """Отправка в чат с клавиатурой настроек"""
        await self.app.bot.send_message(chat_id=chat_id, text=text, reply_markup=self.settings_keyboard)

    def _runtime(self):
        return storage.get_runtime_config(config)

    def _known_buttons(self) -> set:
        return {
            '📊 Статус', '⬆️ +0.01₽', '⬇️ -0.01₽',
            '🔔 Авто: ВКЛ', '🔕 Авто: ВЫКЛ',
            '⚙️ Настройки', '🩺 Диагностика', '🔙 Назад',
            '🎯 Цена', '➖ Шаг', '📉 Мин', '📈 Макс',
            '🔀 Режим', '📍 Позиция',
            '🔗 Добавить URL', '🗑 Удалить URL',
            '📤 Экспорт', '📥 Импорт', '🧾 История',
        }

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id

        if not self._check_access(user_id):
            await self._reply_with_main_keyboard(update, '❌ У вас нет доступа к этому боту')
            return

        await update.message.reply_text(
            '👋 Бот управления ценой GGSEL\n\nВыберите действие:',
            reply_markup=self.main_keyboard,
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status"""
        user_id = update.effective_user.id

        if not self._check_access(user_id):
            await self._reply_with_main_keyboard(update, '❌ У вас нет доступа к этому боту')
            return

        await self.send_status(update.message.chat_id)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        text = update.message.text.strip()

        if not self._check_access(user_id):
            await self._send_with_main_keyboard(chat_id, '❌ У вас нет доступа к этому боту')
            return

        if chat_id in self.pending_actions and text not in self._known_buttons():
            handled = await self._handle_pending_action(chat_id, user_id, text)
            if handled:
                return

        logger.info(f'Получено сообщение: {text}')

        if text == '📊 Статус':
            await self.send_status(chat_id)

        elif text == '⬆️ +0.01₽':
            await self.handle_price_change(chat_id, 0.01)

        elif text == '⬇️ -0.01₽':
            await self.handle_price_change(chat_id, -0.01)

        elif text in ('🔔 Авто: ВКЛ', '🔕 Авто: ВЫКЛ'):
            await self.handle_toggle_auto(chat_id)

        elif text == '⚙️ Настройки':
            await self.send_settings(chat_id)

        elif text == '🩺 Диагностика':
            await self.send_diagnostics(chat_id)

        elif text == '🎯 Цена':
            self.pending_actions[chat_id] = 'DESIRED_PRICE'
            await self._send_with_settings_keyboard(chat_id, 'Введите желаемую цену (например 0.35):')

        elif text == '➖ Шаг':
            self.pending_actions[chat_id] = 'UNDERCUT_VALUE'
            await self._send_with_settings_keyboard(chat_id, 'Введите шаг снижения (например 0.0051):')

        elif text == '📉 Мин':
            self.pending_actions[chat_id] = 'MIN_PRICE'
            await self._send_with_settings_keyboard(chat_id, 'Введите минимальную цену:')

        elif text == '📈 Макс':
            self.pending_actions[chat_id] = 'MAX_PRICE'
            await self._send_with_settings_keyboard(chat_id, 'Введите максимальную цену:')

        elif text == '🔀 Режим':
            await self._toggle_mode(chat_id, user_id)

        elif text == '📍 Позиция':
            await self._toggle_position_filter(chat_id, user_id)

        elif text == '🔗 Добавить URL':
            self.pending_actions[chat_id] = 'ADD_URL'
            await self._send_with_settings_keyboard(chat_id, 'Отправьте URL конкурента:')

        elif text == '🗑 Удалить URL':
            await self._start_remove_url(chat_id)

        elif text == '📤 Экспорт':
            await self._export_runtime_settings(chat_id)

        elif text == '📥 Импорт':
            self.pending_actions[chat_id] = 'IMPORT_SETTINGS'
            await self._send_with_settings_keyboard(
                chat_id,
                'Отправьте настройки в формате key=value, по одной на строку.\n'
                'Пример:\nMIN_PRICE=0.25\nMAX_PRICE=10\nMODE=FIXED',
            )

        elif text == '🧾 История':
            await self._show_settings_history(chat_id)

        elif text == '🔙 Назад':
            self.pending_actions.pop(chat_id, None)
            await update.message.reply_text(
                '📋 Главное меню:',
                reply_markup=self.main_keyboard,
            )
        else:
            await self._send_with_main_keyboard(chat_id, 'Выберите действие кнопками ниже 👇')

    async def send_status(self, chat_id: int):
        """Отправка статуса"""
        state = storage.get_state()
        runtime = self._runtime()

        competitor_info = 'N/A'
        if state.get('last_competitor_min'):
            rank = state.get('last_competitor_rank')
            if rank:
                competitor_info = f'#{rank}'
            else:
                competitor_info = 'N/A'

        text = f"""📊 Статус

💰 Моя цена: {state.get('last_price') or 'N/A'}₽
📈 Цена конкурента: {state.get('last_competitor_min') or 'N/A'}₽
🔍 Позиция конкурента: {competitor_info}

🔔 Авто-режим: {'ВКЛ' if self.auto_mode else 'ВЫКЛ'}
🎯 Режим: {runtime.MODE}
🕐 Последнее обновление: {state.get('last_update').strftime('%Y-%m-%d %H:%M') if state.get('last_update') else 'Никогда'}

📊 Обновлений: {state.get('update_count', 0)}
⏭️ Пропусков: {state.get('skip_count', 0)}
"""

        await self.app.bot.send_message(chat_id=chat_id, text=text, reply_markup=self.main_keyboard)

    async def send_diagnostics(self, chat_id: int):
        """Быстрая диагностика состояния бота и окружения"""
        state = storage.get_state()
        runtime = self._runtime()

        is_valid, errors = validate_runtime_config(runtime)
        config_status = 'OK' if is_valid else 'INVALID'

        api_ok = False
        product_ok = False
        product_price = None
        if self.api_client:
            api_ok = await asyncio.to_thread(self.api_client.check_api_access)
            if api_ok:
                product = await asyncio.to_thread(
                    self.api_client.get_product,
                    config.GGSEL_PRODUCT_ID,
                )
                product_ok = product is not None
                product_price = product.price if product else None

        now = datetime.now()
        last_cycle = state.get('last_cycle')
        if last_cycle:
            age_seconds = int((now - last_cycle).total_seconds())
            heartbeat_text = f'OK ({age_seconds}s)'
        else:
            heartbeat_text = 'NO_DATA'

        lines = [
            '🩺 Диагностика',
            '',
            f'API: {"OK" if api_ok else "FAIL"}',
            f'Product: {"OK" if product_ok else "FAIL"} (id={config.GGSEL_PRODUCT_ID})',
            f'Current price API: {product_price if product_price is not None else "N/A"}',
            f'Runtime config: {config_status}',
            f'Heartbeat: {heartbeat_text}',
            f'Auto mode: {"ON" if self.auto_mode else "OFF"}',
            f'Competitors configured: {len(runtime.COMPETITOR_URLS)}',
            f'DB path: {storage.db_path}',
        ]
        if errors:
            lines.append('Errors: ' + '; '.join(errors[:3]))

        await self._send_with_main_keyboard(chat_id, '\n'.join(lines))

    async def send_settings(self, chat_id: int):
        """Отправка настроек"""
        runtime = self._runtime()
        competitor_urls = runtime.COMPETITOR_URLS
        text = f"""⚙️ Настройки

📉 MIN_PRICE: {runtime.MIN_PRICE}₽
📈 MAX_PRICE: {runtime.MAX_PRICE}₽
🎯 Желаемая цена: {runtime.DESIRED_PRICE}₽
↘️ Шаг снижения: {runtime.UNDERCUT_VALUE}

🔹 Режим: {runtime.MODE}
   - FIXED_PRICE: {runtime.FIXED_PRICE}₽
   - STEP_UP_VALUE: {runtime.STEP_UP_VALUE}₽

🚫 Порог "слабого" конкурента: {runtime.LOW_PRICE_THRESHOLD or 'Выкл'}
📐 Граница ceil-логики: {runtime.WEAK_PRICE_CEIL_LIMIT}
📍 Фильтр позиции: {'Вкл' if runtime.POSITION_FILTER_ENABLED else 'Выкл'}
🔢 Слабая позиция: > {runtime.WEAK_POSITION_THRESHOLD}
⏱️ Cooldown: {runtime.COOLDOWN_SECONDS} сек
📏 Ignore delta: {runtime.IGNORE_DELTA}
🔄 Интервал: {runtime.CHECK_INTERVAL} сек
🔗 Конкурентов: {len(competitor_urls)}
"""

        await self.app.bot.send_message(chat_id=chat_id, text=text, reply_markup=self.settings_keyboard)

    async def handle_price_change(self, chat_id: int, delta: float):
        """Изменение цены"""
        runtime = self._runtime()
        state = storage.get_state()
        current_price = state.get('last_price')

        if not current_price:
            # Пробуем получить из API
            current_price = self.api_client.get_my_price(config.GGSEL_PRODUCT_ID) if self.api_client else None

        if not current_price:
            await self._send_with_main_keyboard(chat_id, '❌ Не удалось получить текущую цену')
            return

        new_price = round(max(current_price + delta, runtime.MIN_PRICE), 4)

        if new_price == current_price:
            await self._send_with_main_keyboard(chat_id, f'⚠️ Нельзя изменить цену (минимум {runtime.MIN_PRICE}₽)')
            return

        # Обновляем через API
        if self.api_client:
            success = self.api_client.update_price(config.GGSEL_PRODUCT_ID, new_price)

            if success:
                storage.update_state(
                    last_price=new_price,
                    last_update=__import__('datetime').datetime.now(),
                )
                await self._send_with_main_keyboard(chat_id, f'✅ Цена изменена: {current_price:.4f}₽ → {new_price:.4f}₽')
            else:
                await self._send_with_main_keyboard(chat_id, '❌ Ошибка обновления цены')
        else:
            await self._send_with_main_keyboard(chat_id, '❌ API-клиент не инициализирован')

    async def _handle_pending_action(self, chat_id: int, user_id: int, text: str) -> bool:
        action = self.pending_actions.get(chat_id)
        if not action:
            return False

        if action in {'DESIRED_PRICE', 'UNDERCUT_VALUE', 'MIN_PRICE', 'MAX_PRICE'}:
            try:
                value = float(text.replace(',', '.'))
            except ValueError:
                await self._send_with_settings_keyboard(chat_id, 'Некорректное число. Попробуйте ещё раз.')
                return True

            if value <= 0:
                await self._send_with_settings_keyboard(chat_id, 'Значение должно быть больше 0.')
                return True

            storage.set_runtime_setting(action, str(value), user_id=user_id, source='telegram')
            self.pending_actions.pop(chat_id, None)
            await self._send_with_settings_keyboard(chat_id, f'✅ {action} = {value}')
            await self.send_settings(chat_id)
            return True

        if action == 'ADD_URL':
            if not re.match(r'^https?://', text.strip(), re.IGNORECASE):
                await self._send_with_settings_keyboard(chat_id, 'Нужен полный URL, начинающийся с http:// или https://')
                return True
            current = storage.get_competitor_urls(config.COMPETITOR_URLS)
            url = text.strip()
            if url not in current:
                current.append(url)
                storage.set_competitor_urls(current, user_id=user_id, source='telegram')
            self.pending_actions.pop(chat_id, None)
            await self._send_with_settings_keyboard(chat_id, '✅ URL добавлен')
            await self.send_settings(chat_id)
            return True

        if action == 'REMOVE_URL':
            current = storage.get_competitor_urls(config.COMPETITOR_URLS)
            try:
                index = int(text.strip())
            except ValueError:
                await self._send_with_settings_keyboard(chat_id, 'Введите номер URL из списка.')
                return True
            if index < 1 or index > len(current):
                await self._send_with_settings_keyboard(chat_id, 'Номер вне диапазона.')
                return True
            removed = current.pop(index - 1)
            storage.set_competitor_urls(current, user_id=user_id, source='telegram')
            self.pending_actions.pop(chat_id, None)
            await self._send_with_settings_keyboard(chat_id, f'✅ Удалён: {removed}')
            await self.send_settings(chat_id)
            return True

        if action == 'IMPORT_SETTINGS':
            await self._import_runtime_settings(chat_id, user_id, text)
            self.pending_actions.pop(chat_id, None)
            return True

        return False

    async def _start_remove_url(self, chat_id: int):
        urls = storage.get_competitor_urls(config.COMPETITOR_URLS)
        if not urls:
            await self._send_with_settings_keyboard(chat_id, 'Список конкурентов пуст.')
            return
        lines = ['Выберите номер URL для удаления:']
        for i, url in enumerate(urls, start=1):
            lines.append(f'{i}. {url}')
        self.pending_actions[chat_id] = 'REMOVE_URL'
        await self._send_with_settings_keyboard(chat_id, '\n'.join(lines))

    async def _toggle_mode(self, chat_id: int, user_id: int):
        runtime = self._runtime()
        new_mode = 'STEP_UP' if runtime.MODE == 'FIXED' else 'FIXED'
        storage.set_runtime_setting('MODE', new_mode, user_id=user_id, source='telegram')
        await self._send_with_settings_keyboard(chat_id, f'✅ Режим переключен: {new_mode}')
        await self.send_settings(chat_id)

    async def _toggle_position_filter(self, chat_id: int, user_id: int):
        runtime = self._runtime()
        new_value = not runtime.POSITION_FILTER_ENABLED
        storage.set_runtime_setting(
            'POSITION_FILTER_ENABLED',
            'true' if new_value else 'false',
            user_id=user_id,
            source='telegram',
        )
        await self._send_with_settings_keyboard(
            chat_id,
            f'✅ Фильтр позиции: {"Вкл" if new_value else "Выкл"}',
        )
        await self.send_settings(chat_id)

    async def _export_runtime_settings(self, chat_id: int):
        settings = storage.get_all_runtime_settings()
        if not settings:
            await self._send_with_settings_keyboard(chat_id, 'Runtime-настройки пусты, используются значения из .env')
            return
        lines = ['Текущие runtime-настройки:']
        for key, value in sorted(settings.items()):
            lines.append(f'{key}={value}')
        await self._send_with_settings_keyboard(chat_id, '\n'.join(lines))

    async def _show_settings_history(self, chat_id: int):
        rows = storage.get_settings_history(limit=15)
        if not rows:
            await self._send_with_settings_keyboard(chat_id, 'История изменений пока пуста.')
            return
        lines = ['Последние изменения:']
        for row in rows:
            user = row.get('user_id')
            lines.append(
                f"{row['timestamp']} | {row['key']}: "
                f"{row['old_value']} -> {row['new_value']} "
                f"(user={user}, src={row.get('source')})"
            )
        await self._send_with_settings_keyboard(chat_id, '\n'.join(lines))

    async def _import_runtime_settings(self, chat_id: int, user_id: int, text: str):
        allowed_keys = {
            'MIN_PRICE', 'MAX_PRICE', 'DESIRED_PRICE', 'UNDERCUT_VALUE',
            'MODE', 'FIXED_PRICE', 'STEP_UP_VALUE', 'LOW_PRICE_THRESHOLD',
            'WEAK_PRICE_CEIL_LIMIT', 'POSITION_FILTER_ENABLED',
            'WEAK_POSITION_THRESHOLD', 'COOLDOWN_SECONDS',
            'IGNORE_DELTA', 'CHECK_INTERVAL', 'competitor_urls',
        }
        updated = 0
        errors = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if '=' not in line:
                errors.append(f'Пропущена "=": {line}')
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if key not in allowed_keys:
                errors.append(f'Неизвестный ключ: {key}')
                continue
            if key == 'competitor_urls':
                urls = [x.strip() for x in value.split(',') if x.strip()]
                storage.set_competitor_urls(urls, user_id=user_id, source='telegram_import')
            else:
                storage.set_runtime_setting(key, value, user_id=user_id, source='telegram_import')
            updated += 1

        result_lines = [f'Импорт завершен. Обновлено: {updated}']
        if errors:
            result_lines.append('Ошибки:')
            result_lines.extend(errors[:10])
        await self._send_with_settings_keyboard(chat_id, '\n'.join(result_lines))
        await self.send_settings(chat_id)

    async def handle_toggle_auto(self, chat_id: int):
        """Переключение авто-режима"""
        self.auto_mode = not self.auto_mode
        storage.update_state(auto_mode=self.auto_mode)
        status = 'ВКЛ' if self.auto_mode else 'ВЫКЛ'

        # Обновляем клавиатуру
        self.main_keyboard = ReplyKeyboardMarkup([
            ['📊 Статус'],
            ['⬆️ +0.01₽', '⬇️ -0.01₽'],
            ['🔔 Авто: ВКЛ' if self.auto_mode else '🔕 Авто: ВЫКЛ'],
            ['⚙️ Настройки', '🩺 Диагностика'],
        ], resize_keyboard=True, one_time_keyboard=False)

        await self.app.bot.send_message(
            chat_id=chat_id,
            text=f'🔔 Авто-режим {status}',
            reply_markup=self.main_keyboard,
        )

    async def notify(self, message: str):
        """Отправка уведомления всем админам"""
        for chat_id in self.admin_ids:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.main_keyboard,
                )
                logger.debug(f'Уведомление отправлено chat_id={chat_id}')
            except Exception as e:
                logger.error(f'Ошибка отправки уведомления: {e}')

    async def notify_price_updated(self, old_price: float, new_price: float,
                                   competitor_price: float, reason: str):
        """Уведомление об обновлении цены"""
        text = (
            f"💰 *Цена обновлена*\n\n"
            f"Старая: `{old_price:.4f}₽`\n"
            f"Новая: `{new_price:.4f}₽`\n"
            f"Конкурент: `{competitor_price:.4f}₽`\n"
            f"Причина: `{reason}`"
        )
        await self.notify(text)

    async def notify_skip(self, current_price: float, target_price: float,
                          competitor_price: float, reason: str):
        """Уведомление о пропуске"""
        text = (
            f"⏭️ *Пропуск обновления*\n\n"
            f"Текущая: `{current_price:.4f}₽`\n"
            f"Целевая: `{target_price:.4f}₽`\n"
            f"Конкурент: `{competitor_price:.4f}₽`\n"
            f"Причина: `{reason}`"
        )
        await self.notify(text)

    async def notify_error(self, error: str):
        """Уведомление об ошибке"""
        text = f"❌ *Ошибка*\n\n`{error}`"
        await self.notify(text)

    async def notify_startup(self):
        """Уведомление о запуске"""
        competitor_urls = storage.get_competitor_urls(config.COMPETITOR_URLS)
        runtime = self._runtime()
        text = (
            f"🚀 *Auto-Pricing Bot запущен*\n\n"
            f"Товар: `{config.GGSEL_PRODUCT_ID}`\n"
            f"Конкурентов: `{len(competitor_urls)}`\n"
            f"Интервал: `{runtime.CHECK_INTERVAL}s`"
        )
        await self.notify(text)

    def run(self):
        """Запуск бота (blocking)"""
        logger.info('Запуск Telegram бота...')
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    def stop(self):
        """Остановка бота"""
        if self._app:
            try:
                # Предпочтительный способ для run_polling
                self.app.stop_running()
            except Exception:
                try:
                    self.app.stop()
                except Exception as e:
                    logger.error(f'Ошибка остановки Telegram бота: {e}')


# Глобальный экземпляр
telegram_bot: Optional[TelegramBot] = None
