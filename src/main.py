"""
Auto-Pricing Bot - точка входа
Интеграция с Telegram ботом
"""

import asyncio
import logging
import sys
import signal
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

from .config import config
from .api_client import GGSELClient
from .telegram_bot import TelegramBot
from .scheduler import Scheduler
from .storage import storage

# Глобальные компоненты
api_client: Optional[GGSELClient] = None
telegram_bot: Optional[TelegramBot] = None
scheduler: Optional[Scheduler] = None
bot_thread: Optional[threading.Thread] = None

# Флаг остановки
shutdown_event = asyncio.Event()


# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f'bot-{datetime.now().strftime("%Y-%m-%d")}.log'

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            RotatingFileHandler(
                log_file,
                encoding='utf-8',
                maxBytes=config.LOG_MAX_BYTES,
                backupCount=config.LOG_BACKUP_COUNT,
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Логгеры для httpx (тише)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)


# ============================================================================
# ОБРАБОТКА СИГНАЛОВ
# ============================================================================

def setup_signal_handlers():
    """Настройка обработки сигналов"""
    loop = asyncio.get_event_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown())
        )


async def shutdown():
    """Корректная остановка бота"""
    logger = logging.getLogger(__name__)

    if shutdown_event.is_set():
        return

    logger.info('🛑 Получен сигнал остановки, начало корректного завершения...')
    shutdown_event.set()

    # Остановка планировщика
    if scheduler:
        logger.info('Остановка планировщика...')
        scheduler.stop()

    # Остановка Telegram бота
    if telegram_bot:
        logger.info('Остановка Telegram бота...')
        telegram_bot.stop()
    if bot_thread and bot_thread.is_alive():
        logger.info('Ожидание завершения потока Telegram...')
        bot_thread.join(timeout=10)

    logger.info('✅ Бот корректно завершил работу')


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

async def main():
    """Основная функция"""
    global api_client, telegram_bot, scheduler, bot_thread

    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info('🚀 Запуск Auto-Pricing Bot...')

    # Проверка конфигурации
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error('TELEGRAM_BOT_TOKEN не указан')
        return

    if not config.GGSEL_API_KEY:
        logger.error('GGSEL_API_KEY не указан')
        return

    if not config.GGSEL_PRODUCT_ID:
        logger.error('GGSEL_PRODUCT_ID не указан')
        return

    competitor_urls = storage.get_competitor_urls(config.COMPETITOR_URLS)
    if not competitor_urls:
        logger.error('COMPETITOR_URLS не указан')
        return

    logger.info(f'Конфигурация загружена:')
    logger.info(f'  - Товар: {config.GGSEL_PRODUCT_ID}')
    logger.info(f'  - Конкурентов: {len(competitor_urls)}')
    logger.info(f'  - MIN_PRICE: {config.MIN_PRICE}')
    logger.info(f'  - MAX_PRICE: {config.MAX_PRICE}')
    logger.info(f'  - MODE: {config.MODE}')
    logger.info(f'  - Интервал: {config.CHECK_INTERVAL}s')

    # Инициализация компонентов
    logger.info('Инициализация компонентов...')

    api_client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
    )

    telegram_bot = TelegramBot(api_client=api_client)

    # Проверка связи с GGSEL
    logger.info('Проверка связи с GGSEL API...')
    api_accessible = api_client.check_api_access()

    if api_accessible:
        product = api_client.get_product(config.GGSEL_PRODUCT_ID)
        if product:
            logger.info(f'✅ Товар найден: {product.name}')
            logger.info(f'   Текущая цена: {product.price} {product.currency}')
            storage.update_state(last_price=product.price)
        else:
            logger.warning(f'⚠️ Товар {config.GGSEL_PRODUCT_ID} не найден')
    else:
        logger.warning('⚠️ GGSEL API недоступен')
        logger.warning('   Бот будет работать в режиме мониторинга (без обновления цен)')

    # Инициализация хранилища
    state = storage.get_state()
    logger.info(f'Состояние загружено: update_count={state["update_count"]}, skip_count={state["skip_count"]}')

    # Инициализируем runtime competitor_urls из .env при первом запуске
    if storage.get_runtime_setting('competitor_urls') is None and competitor_urls:
        storage.set_competitor_urls(competitor_urls)

    # Создание планировщика
    scheduler = Scheduler(api_client, telegram_bot)

    # Настройка сигналов
    setup_signal_handlers()

    # Уведомление о запуске
    await telegram_bot.notify_startup()

    # Запуск Telegram бота в отдельном потоке
    bot_thread = threading.Thread(target=telegram_bot.run, daemon=True)
    bot_thread.start()
    logger.info('Telegram бот запущен в фоне')

    # Даем боту время на старт
    await asyncio.sleep(2)

    # Запуск планировщика
    logger.info('Запуск планировщика...')

    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info('Получен сигнал остановки')
    finally:
        await shutdown()


def run():
    """Запуск бота"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.exception(f'Критическая ошибка: {e}')
        sys.exit(1)


if __name__ == '__main__':
    run()
