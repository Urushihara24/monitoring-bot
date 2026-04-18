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

_PRODUCT_RUNTIME_MIGRATION_KEYS = (
    'MIN_PRICE',
    'MAX_PRICE',
    'DESIRED_PRICE',
    'UNDERCUT_VALUE',
    'RAISE_VALUE',
    'SHOWCASE_ROUND_STEP',
    'REBOUND_TO_DESIRED_ON_MIN',
    'MODE',
    'FIXED_PRICE',
    'STEP_UP_VALUE',
    'WEAK_PRICE_CEIL_LIMIT',
    'POSITION_FILTER_ENABLED',
    'WEAK_POSITION_THRESHOLD',
    'WEAK_UNKNOWN_RANK_ENABLED',
    'WEAK_UNKNOWN_RANK_ABS_GAP',
    'WEAK_UNKNOWN_RANK_REL_GAP',
    'COOLDOWN_SECONDS',
    'IGNORE_DELTA',
    'CHECK_INTERVAL',
    'FAST_CHECK_INTERVAL_MIN',
    'FAST_CHECK_INTERVAL_MAX',
    'COMPETITOR_COOKIES',
    'NOTIFY_SKIP',
    'NOTIFY_SKIP_COOLDOWN_SECONDS',
    'NOTIFY_COMPETITOR_CHANGE',
    'COMPETITOR_CHANGE_DELTA',
    'COMPETITOR_CHANGE_COOLDOWN_SECONDS',
    'UPDATE_ONLY_ON_COMPETITOR_CHANGE',
    'NOTIFY_PARSER_ISSUES',
    'NOTIFY_ERRORS',
    'PARSER_ISSUE_COOLDOWN_SECONDS',
    'HARD_FLOOR_ENABLED',
    'MAX_DOWN_STEP',
    'FAST_REBOUND_DELTA',
    'FAST_REBOUND_BYPASS_COOLDOWN',
    'competitor_urls',
)


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


def _resolve_startup_prices(
    *,
    profile_id: str,
    client,
    product_id: int,
    product,
) -> tuple[float, str, Optional[float]]:
    """
    Возвращает цены для логирования и seed в state:
    (log_price, log_currency, state_seed_price).

    Для DigiSeller при недоступной публичной unit-цене не seed-им last_price,
    чтобы не подмешивать seller-цену (может быть не unit/RUB).
    """
    log_price = float(product.price)
    log_currency = str(product.currency)
    state_seed_price: Optional[float] = float(product.price)

    get_display_price = getattr(client, 'get_display_price', None)
    if callable(get_display_price):
        try:
            resolved = get_display_price(product_id)
            if resolved is not None:
                display_price = float(resolved)
                return display_price, 'RUB', display_price
        except Exception:
            pass

    if profile_id == 'digiseller':
        state_seed_price = None

    return log_price, log_currency, state_seed_price


def _product_runtime_profile_id(profile_id: str, product_id: int) -> str:
    normalized_profile_id = (profile_id or '').strip().lower()
    normalized_product_id = int(product_id or 0)
    if normalized_product_id <= 0:
        return normalized_profile_id
    return f'{normalized_profile_id}:{normalized_product_id}'


def _has_meaningful_state(state: dict) -> bool:
    if not isinstance(state, dict):
        return False
    if (state.get('update_count') or 0) > 0:
        return True
    if (state.get('skip_count') or 0) > 0:
        return True
    return any(
        state.get(field) is not None
        for field in (
            'last_price',
            'last_update',
            'last_cycle',
            'last_target_price',
            'last_target_competitor_min',
            'last_competitor_price',
            'last_competitor_min',
            'last_competitor_rank',
            'last_competitor_url',
            'last_competitor_parse_at',
            'last_competitor_method',
            'last_competitor_error',
            'last_competitor_block_reason',
            'last_competitor_status_code',
        )
    )


def _migrate_primary_product_namespace(
    logger: logging.Logger,
    *,
    profile_id: str,
    product_id: int,
) -> None:
    runtime_profile_id = _product_runtime_profile_id(profile_id, product_id)
    if runtime_profile_id == profile_id:
        return

    migrated_runtime_keys: list[str] = []
    for key in _PRODUCT_RUNTIME_MIGRATION_KEYS:
        existing = storage.get_runtime_setting(
            key,
            profile_id=runtime_profile_id,
            inherit_parent=False,
        )
        if existing is not None:
            continue
        parent_value = storage.get_runtime_setting(
            key,
            profile_id=profile_id,
            inherit_parent=False,
        )
        if parent_value is None:
            continue
        storage.set_runtime_setting(
            key,
            parent_value,
            source='startup_primary_migration',
            profile_id=runtime_profile_id,
        )
        migrated_runtime_keys.append(key)

    child_state = storage.get_state(profile_id=runtime_profile_id)
    parent_state = storage.get_state(profile_id=profile_id)
    if not _has_meaningful_state(child_state) and _has_meaningful_state(parent_state):
        migrated_state = {
            key: parent_state.get(key)
            for key in (
                'last_price',
                'last_update',
                'last_cycle',
                'last_target_price',
                'last_target_competitor_min',
                'last_competitor_price',
                'last_competitor_min',
                'last_competitor_rank',
                'last_competitor_url',
                'last_competitor_parse_at',
                'last_competitor_method',
                'last_competitor_error',
                'last_competitor_block_reason',
                'last_competitor_status_code',
                'auto_mode',
                'update_count',
                'skip_count',
            )
            if parent_state.get(key) is not None
        }
        if migrated_state:
            storage.update_state(
                profile_id=runtime_profile_id,
                **migrated_state,
            )
            logger.info(
                '[%s] Миграция legacy profile_state -> %s завершена',
                profile_id.upper(),
                runtime_profile_id,
            )

    if migrated_runtime_keys:
        logger.info(
            '[%s] Миграция runtime ключей в %s: %s',
            profile_id.upper(),
            runtime_profile_id,
            ', '.join(migrated_runtime_keys),
        )


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
            ggsel_tracked_products = storage.list_tracked_products(
                profile_id='ggsel',
                default_product_id=config.GGSEL_PRODUCT_ID,
                default_urls=ggsel_urls,
            )
            if not ggsel_tracked_products:
                logger.warning(
                    '[GGSEL] Нет товаров в tracked_products '
                    '(и fallback GGSEL_PRODUCT_ID пуст)'
                )
                ggsel_tracked_products = []
            primary = (
                next(
                    (
                        item for item in ggsel_tracked_products
                        if item['product_id'] == config.GGSEL_PRODUCT_ID
                    ),
                    None,
                ) or (ggsel_tracked_products[0] if ggsel_tracked_products else None)
            )
            if not primary:
                primary_product_id = int(config.GGSEL_PRODUCT_ID or 0)
                primary_urls = []
                logger.warning(
                    '[GGSEL] Нет товаров в мониторинге, профиль запущен в '
                    'режиме управления (без scheduler до добавления товара)'
                )
            else:
                primary_product_id = int(primary['product_id'])
                primary_urls = list(primary.get('competitor_urls', []))
            profiles.append(
                {
                    'id': 'ggsel',
                    'name': 'GGSEL',
                    'product_id': primary_product_id,
                    'competitor_urls': primary_urls,
                    'tracked_products': ggsel_tracked_products,
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
            digi_tracked_products = storage.list_tracked_products(
                profile_id='digiseller',
                default_product_id=config.DIGISELLER_PRODUCT_ID,
                default_urls=digi_urls,
            )
            if not digi_tracked_products:
                logger.warning(
                    '[DIGISELLER] Нет товаров в tracked_products '
                    '(и fallback DIGISELLER_PRODUCT_ID пуст)'
                )
                digi_tracked_products = []
            primary = (
                next(
                    (
                        item for item in digi_tracked_products
                        if item['product_id'] == config.DIGISELLER_PRODUCT_ID
                    ),
                    None,
                ) or (digi_tracked_products[0] if digi_tracked_products else None)
            )
            if not primary:
                primary_product_id = int(config.DIGISELLER_PRODUCT_ID or 0)
                primary_urls = []
                logger.warning(
                    '[DIGISELLER] Нет товаров в мониторинге, профиль запущен в '
                    'режиме управления (без scheduler до добавления товара)'
                )
            else:
                primary_product_id = int(primary['product_id'])
                primary_urls = list(primary.get('competitor_urls', []))
            profiles.append(
                {
                    'id': 'digiseller',
                    'name': 'DIGISELLER',
                    'product_id': primary_product_id,
                    'competitor_urls': primary_urls,
                    'tracked_products': digi_tracked_products,
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
        tracked_products = p.get('tracked_products', [])
        tracked_count = len(tracked_products)
        tracked_competitors = sum(
            len(item.get('competitor_urls', []))
            for item in tracked_products
        )
        logger.info(
            '[%s] Основной товар=%s, Товаров=%s, Конкурентов=%s',
            p['name'],
            p['product_id'],
            tracked_count,
            tracked_competitors,
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
                display_price, display_currency, seed_price = _resolve_startup_prices(
                    profile_id=pid,
                    client=client,
                    product_id=product_id,
                    product=product,
                )
                if pid == 'digiseller' and seed_price is None:
                    logger.warning(
                        '[%s] Публичная unit-цена недоступна на старте; '
                        'seed last_price пропущен',
                        pname,
                    )
                logger.info(
                    '[%s] Товар найден: %s (цена=%s %s)',
                    pname,
                    product.name,
                    display_price,
                    display_currency,
                )
                state = storage.get_state(profile_id=pid)
                if state.get('last_target_price') is not None:
                    # Не перетираем целевую цену округлённым чтением API.
                    storage.update_state(
                        profile_id=pid,
                        last_price=state.get('last_target_price'),
                    )
                elif state.get('last_price') is None and seed_price is not None:
                    storage.update_state(
                        profile_id=pid,
                        last_price=seed_price,
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

        # runtime init для competitor_urls per product scheduler key.
        tracked_products = profile.get('tracked_products', [])
        primary_product_id = int(profile.get('product_id') or 0)
        for tracked in tracked_products:
            tracked_product_id = int(tracked.get('product_id') or 0)
            if tracked_product_id <= 0:
                continue
            tracked_urls = list(tracked.get('competitor_urls', []))
            runtime_profile_id = _product_runtime_profile_id(
                pid,
                tracked_product_id,
            )
            if tracked_product_id == primary_product_id:
                _migrate_primary_product_namespace(
                    logger,
                    profile_id=pid,
                    product_id=tracked_product_id,
                )
            if storage.get_runtime_setting(
                'competitor_urls',
                profile_id=runtime_profile_id,
                inherit_parent=False,
            ) is None and tracked_urls:
                storage.set_competitor_urls(
                    tracked_urls,
                    profile_id=runtime_profile_id,
                )
            if tracked_product_id != primary_product_id:
                auto_mode_change = storage.get_last_setting_change(
                    'auto_mode',
                    profile_id=runtime_profile_id,
                )
                if auto_mode_change is None:
                    storage.set_auto_mode(
                        False,
                        profile_id=runtime_profile_id,
                        source='startup_safe_default',
                    )
                    logger.info(
                        '[%s] Safe default: автоцена выключена для товара %s',
                        pname,
                        tracked_product_id,
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

    schedulers = []
    for profile in profiles:
        pid = profile['id']
        pname = profile['name']
        primary_product_id = int(profile.get('product_id') or 0)
        tracked_products = profile.get('tracked_products', [])
        for tracked in tracked_products:
            tracked_product_id = int(tracked.get('product_id') or 0)
            if tracked_product_id <= 0:
                continue
            runtime_profile_id = _product_runtime_profile_id(
                pid,
                tracked_product_id,
            )
            sched_profile_name = (
                pname
                if tracked_product_id == primary_product_id
                else f'{pname} [{tracked_product_id}]'
            )
            schedulers.append(
                Scheduler(
                    profile['client'],
                    telegram_bot,
                    profile_id=runtime_profile_id,
                    base_profile_id=pid,
                    profile_name=sched_profile_name,
                    product_id=tracked_product_id,
                    competitor_urls=tracked.get('competitor_urls', []),
                    chat_autoreply_enabled=(
                        tracked_product_id == primary_product_id
                    ),
                )
            )

    setup_signal_handlers()

    await telegram_bot.start()
    logger.info('Telegram бот запущен')
    for profile in profiles:
        tracked_products = profile.get('tracked_products', [])
        tracked_count = len(tracked_products)
        tracked_competitors = sum(
            len(item.get('competitor_urls', []))
            for item in tracked_products
        )
        await telegram_bot.notify(
            (
                f"🚀 *Auto-Pricing Bot запущен*\n\n"
                f"Профиль: `{profile['name']}`\n"
                f"Основной товар: `{profile['product_id']}`\n"
                f"Товаров: `{tracked_count}`\n"
                f"Конкурентов: `{tracked_competitors}`"
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
