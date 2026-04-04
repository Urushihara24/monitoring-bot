"""
Auto-Pricing Bot - точка входа.
Запуск мультипрофильного контура (GGSEL + DigiSeller).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional

from .api_client import GGSELClient
from .config import config
from .digiseller_client import DigiSellerClient
from .profile_defaults import (
    build_profile_runtime_defaults,
    seed_profile_runtime_defaults,
)
from .scheduler import Scheduler
from .storage import storage
from .telegram_bot import TelegramBot

# Глобальные компоненты
api_clients: Dict[str, object] = {}
telegram_bot: Optional[TelegramBot] = None
schedulers: List[Scheduler] = []

# Флаг остановки
shutdown_event = asyncio.Event()


def setup_logging():
    """Настройка логирования."""
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
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)


def setup_signal_handlers():
    """Настройка обработки сигналов остановки."""
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))


async def shutdown():
    """Корректная остановка всех компонентов."""
    logger = logging.getLogger(__name__)
    if shutdown_event.is_set():
        return
    shutdown_event.set()
    logger.info('🛑 Получен сигнал остановки...')

    for sch in schedulers:
        sch.stop()

    if telegram_bot:
        await telegram_bot.stop()

    logger.info('✅ Бот корректно завершил работу')


def _build_profiles(logger: logging.Logger):
    """
    Собирает список включённых профилей.
    Возвращает список словарей со спецификацией профилей.
    """
    profiles = []

    if config.GGSEL_ENABLED:
        ggsel_urls = storage.get_competitor_urls(
            config.GGSEL_COMPETITOR_URLS,
            profile_id='ggsel',
        )
        if not ggsel_urls:
            logger.warning(
                '[GGSEL] Профиль включен, но нет GGSEL_COMPETITOR_URLS'
            )
        if not config.GGSEL_PRODUCT_ID:
            logger.warning('[GGSEL] Профиль включен, но GGSEL_PRODUCT_ID пуст')
        elif not config.GGSEL_API_KEY and not config.GGSEL_ACCESS_TOKEN:
            logger.warning('[GGSEL] Профиль включен, но не задан API key/token')
        else:
            profiles.append(
                {
                    'id': 'ggsel',
                    'name': 'GGSEL',
                    'product_id': config.GGSEL_PRODUCT_ID,
                    'competitor_urls': ggsel_urls,
                    'require_api_on_start': config.GGSEL_REQUIRE_API_ON_START,
                    'client': GGSELClient(
                        api_key=config.GGSEL_API_KEY,
                        api_secret=config.GGSEL_API_SECRET,
                        seller_id=config.GGSEL_SELLER_ID,
                        base_url=config.GGSEL_BASE_URL,
                        lang=config.GGSEL_LANG,
                        access_token=config.GGSEL_ACCESS_TOKEN,
                    ),
                }
            )

    if config.DIGISELLER_ENABLED:
        digi_urls = storage.get_competitor_urls(
            config.DIGISELLER_COMPETITOR_URLS,
            profile_id='digiseller',
        )
        if not digi_urls:
            logger.warning(
                '[DIGISELLER] Профиль включен, но нет DIGISELLER_COMPETITOR_URLS'
            )
        if not config.DIGISELLER_PRODUCT_ID:
            logger.warning(
                '[DIGISELLER] Профиль включен, но DIGISELLER_PRODUCT_ID пуст'
            )
        elif not config.DIGISELLER_API_KEY and not config.DIGISELLER_ACCESS_TOKEN:
            logger.warning(
                '[DIGISELLER] Профиль включен, но не задан API key/token'
            )
        else:
            profiles.append(
                {
                    'id': 'digiseller',
                    'name': 'DIGISELLER',
                    'product_id': config.DIGISELLER_PRODUCT_ID,
                    'competitor_urls': digi_urls,
                    'require_api_on_start': (
                        config.DIGISELLER_REQUIRE_API_ON_START
                    ),
                    'client': DigiSellerClient(
                        api_key=config.DIGISELLER_API_KEY,
                        api_secret=config.DIGISELLER_API_SECRET,
                        seller_id=config.DIGISELLER_SELLER_ID,
                        base_url=config.DIGISELLER_BASE_URL,
                        lang=config.DIGISELLER_LANG,
                        access_token=config.DIGISELLER_ACCESS_TOKEN,
                        default_product_id=config.DIGISELLER_PRODUCT_ID,
                    ),
                }
            )

    return profiles


async def main():
    """Основная функция запуска."""
    global api_clients, telegram_bot, schedulers

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info('🚀 Запуск Auto-Pricing Bot...')

    if not config.TELEGRAM_BOT_TOKEN:
        logger.error('TELEGRAM_BOT_TOKEN не указан')
        return

    profiles = _build_profiles(logger)
    if not profiles:
        logger.error(
            'Нет валидных профилей для запуска. '
            'Проверь GGSEL_ENABLED / DIGISELLER_ENABLED и credentials.'
        )
        return

    logger.info('Активных профилей: %s', len(profiles))
    for p in profiles:
        logger.info(
            '[%s] Товар=%s, Конкурентов=%s',
            p['name'],
            p['product_id'],
            len(p['competitor_urls']),
        )

    api_clients = {p['id']: p['client'] for p in profiles}
    profile_products = {p['id']: p['product_id'] for p in profiles}
    profile_default_urls = {p['id']: p['competitor_urls'] for p in profiles}
    profile_labels = {p['id']: p['name'] for p in profiles}

    telegram_bot = TelegramBot(
        api_clients=api_clients,
        profile_products=profile_products,
        profile_default_urls=profile_default_urls,
        profile_labels=profile_labels,
    )

    # Проверка API и первичная инициализация state по каждому профилю.
    for profile in profiles:
        pid = profile['id']
        pname = profile['name']
        client = profile['client']
        product_id = profile['product_id']
        require_api = profile['require_api_on_start']

        logger.info('[%s] Проверка API...', pname)
        api_accessible = client.check_api_access()
        if api_accessible and product_id:
            product = client.get_product(product_id)
            if product:
                logger.info(
                    '[%s] Товар найден: %s (цена=%s %s)',
                    pname,
                    product.name,
                    product.price,
                    product.currency,
                )
                state = storage.get_state(profile_id=pid)
                if state.get('last_target_price') is not None:
                    # Не перетираем целевую цену округлённым чтением API.
                    storage.update_state(
                        profile_id=pid,
                        last_price=state.get('last_target_price'),
                    )
                elif state.get('last_price') is None:
                    storage.update_state(
                        profile_id=pid,
                        last_price=product.price,
                    )
            else:
                logger.warning('[%s] Товар %s не найден', pname, product_id)
        else:
            logger.warning('[%s] API недоступен на старте', pname)
            if require_api:
                logger.error(
                    '[%s] require_api_on_start=true, остановка запуска.',
                    pname,
                )
                return

        # runtime init для competitor_urls.
        if storage.get_runtime_setting(
            'competitor_urls',
            profile_id=pid,
        ) is None and profile['competitor_urls']:
            storage.set_competitor_urls(
                profile['competitor_urls'],
                profile_id=pid,
            )

        profile_defaults = build_profile_runtime_defaults(config, pid)
        seeded = seed_profile_runtime_defaults(
            storage,
            pid,
            profile_defaults,
        )
        for key, value in seeded.items():
            logger.info(
                '[%s] Runtime default seeded: %s=%s',
                pname,
                key,
                value,
            )

    schedulers = [
        Scheduler(
            profile['client'],
            telegram_bot,
            profile_id=profile['id'],
            profile_name=profile['name'],
            product_id=profile['product_id'],
            competitor_urls=profile['competitor_urls'],
        )
        for profile in profiles
    ]

    setup_signal_handlers()

    await telegram_bot.start()
    logger.info('Telegram бот запущен')
    for profile in profiles:
        await telegram_bot.notify(
            (
                f"🚀 *Auto-Pricing Bot запущен*\n\n"
                f"Профиль: `{profile['name']}`\n"
                f"Товар: `{profile['product_id']}`\n"
                f"Конкурентов: `{len(profile['competitor_urls'])}`"
            )
        )

    scheduler_tasks = [asyncio.create_task(s.run()) for s in schedulers]
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        await shutdown()
        for task in scheduler_tasks:
            if task.done():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def run():
    """Запуск бота."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.exception('Критическая ошибка: %s', e)
        sys.exit(1)


if __name__ == '__main__':
    run()
