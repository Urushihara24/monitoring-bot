"""
Scheduler - циклический обработчик auto-pricing
Интеграция с Telegram ботом
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .config import config
from .parser import parser
from .logic import calculate_price
from .storage import storage
from .validator import validate_runtime_config

# Импортируем типы для избежания циклического импорта
if TYPE_CHECKING:
    from .api_client import GGSELClient
    from .telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Планировщик задач auto-pricing

    Цикл работы:
    1. Получить цены конкурентов (парсинг)
    2. Получить текущую цену (API)
    3. Рассчитать решение (logic)
    4. Обновить цену (API) или пропустить
    5. Сохранить состояние (storage)
    6. Отправить уведомление (Telegram)
    7. Ждать CHECK_INTERVAL
    """

    def __init__(
        self,
        api_client: 'GGSELClient',
        telegram_bot: 'TelegramBot',
    ):
        self.api_client = api_client
        self.telegram_bot = telegram_bot
        self._running = False

    async def _notify_error_throttled(self, key: str, message: str, cooldown_seconds: int = 300):
        """Отправка error-уведомления с ограничением частоты"""
        if storage.should_send_alert(key=key, cooldown_seconds=cooldown_seconds):
            await self.telegram_bot.notify_error(message)
        else:
            logger.info(f'Уведомление подавлено throttling: key={key}')

    async def _notify_skip_throttled(self, runtime, current_price: float, target_price: float,
                                     competitor_price: float, reason: str):
        """Уведомление о пропуске с ограничением частоты и runtime-флагом"""
        if not runtime.NOTIFY_SKIP:
            return
        if storage.should_send_alert(
            key='skip_notification',
            cooldown_seconds=runtime.NOTIFY_SKIP_COOLDOWN_SECONDS,
        ):
            await self.telegram_bot.notify_skip(
                current_price=current_price,
                target_price=target_price,
                competitor_price=competitor_price,
                reason=reason,
            )
        else:
            logger.info('Skip-уведомление подавлено throttling')

    async def _notify_competitor_change_if_needed(
        self,
        runtime,
        old_price: Optional[float],
        new_price: float,
        rank: Optional[int],
    ):
        """Уведомление об изменении минимальной цены конкурента"""
        if not runtime.NOTIFY_COMPETITOR_CHANGE:
            return
        if old_price is None:
            return
        delta = abs(new_price - old_price)
        if delta < runtime.COMPETITOR_CHANGE_DELTA:
            return

        if storage.should_send_alert(
            key='competitor_price_change',
            cooldown_seconds=runtime.COMPETITOR_CHANGE_COOLDOWN_SECONDS,
        ):
            await self.telegram_bot.notify_competitor_price_changed(
                old_price=old_price,
                new_price=new_price,
                delta=delta,
                rank=rank,
            )
        else:
            logger.info('Уведомление об изменении цены конкурента подавлено throttling')

    async def run_cycle(self):
        """
        Один цикл работы планировщика
        """
        logger.info('🔄 Запуск цикла pricing...')

        try:
            storage.update_state(last_cycle=datetime.now())
            runtime = storage.get_runtime_config(config)
            state = storage.get_state()

            # Загружаем cookies из env или backup файла
            cookies_str = getattr(runtime, 'COMPETITOR_COOKIES', '')
            parser.set_cookie_string(cookies_str)

            # Пытаемся загрузить из backup если env пустой
            if not cookies_str:
                backup_path = Path('data/cookies_backup.json')
                if backup_path.exists():
                    parser.set_cookies_backup_file(str(backup_path))

            parser.set_browser_config(
                use_real_profile=getattr(runtime, 'SELENIUM_USE_REAL_PROFILE', False),
                chrome_user_data_dir=getattr(runtime, 'SELENIUM_CHROME_USER_DATA_DIR', ''),
                chrome_profile_dir=getattr(runtime, 'SELENIUM_CHROME_PROFILE_DIR', 'Default'),
                selenium_headless=getattr(runtime, 'SELENIUM_HEADLESS', True),
            )

            is_valid, errors = validate_runtime_config(runtime)
            if not is_valid:
                message = 'Некорректные runtime-настройки: ' + '; '.join(errors[:5])
                logger.error(message)
                await self._notify_error_throttled(
                    key='invalid_runtime_config',
                    message=message,
                    cooldown_seconds=180,
                )
                storage.increment_skip_count()
                return

            # === PRE-CHECK: авто-режим ===
            state = storage.get_state()
            if not state.get('auto_mode', True):
                logger.info('Авто-режим выключен, цикл пропущен')
                storage.increment_skip_count()
                return

            # === ШАГ 1: Получить цены конкурентов ===
            logger.info(f'Парсинг {len(runtime.COMPETITOR_URLS)} конкурентов...')
            competitor_results = parser.parse_competitors(
                runtime.COMPETITOR_URLS,
                detect_rank=runtime.POSITION_FILTER_ENABLED,
            )
            valid_competitors = [
                r for r in competitor_results
                if r.success and r.price is not None
            ]

            if not valid_competitors:
                logger.warning('Не удалось получить цены конкурентов')
                await self._notify_error_throttled(
                    key='no_competitor_prices',
                    message='Не удалось получить цены конкурентов',
                    cooldown_seconds=180,
                )
                storage.increment_skip_count()
                return

            considered_competitors = valid_competitors
            force_weak_mode = False

            if runtime.POSITION_FILTER_ENABLED:
                strong_competitors = [
                    r for r in valid_competitors
                    if r.rank is None or r.rank <= runtime.WEAK_POSITION_THRESHOLD
                ]
                if strong_competitors:
                    considered_competitors = strong_competitors
                else:
                    # Все конкуренты "слабые" по позиции, включаем защитный режим
                    considered_competitors = valid_competitors
                    force_weak_mode = True

            selected = min(considered_competitors, key=lambda x: x.price)
            min_price = selected.price
            selected_rank = selected.rank
            competitor_prices = [r.price for r in considered_competitors if r.price is not None]

            logger.info(f'Минимальная цена конкурента: {min_price}')
            if selected_rank is not None:
                logger.info(f'Позиция целевого конкурента: #{selected_rank}')

            await self._notify_competitor_change_if_needed(
                runtime=runtime,
                old_price=state.get('last_competitor_min'),
                new_price=min_price,
                rank=selected_rank,
            )

            # Сохраняем цену конкурента
            storage.update_state(
                last_competitor_price=min_price,
                last_competitor_min=min_price,
                last_competitor_rank=selected_rank,
            )

            # === ШАГ 2: Получить текущую цену ===
            current_price = self.api_client.get_my_price(config.GGSEL_PRODUCT_ID)

            if current_price is None:
                # Используем цену из хранилища
                current_price = state.get('last_price')

                if current_price is None:
                    logger.error('Не удалось получить текущую цену')
                    await self._notify_error_throttled(
                        key='no_current_price',
                        message='Не удалось получить текущую цену',
                        cooldown_seconds=180,
                    )
                    storage.increment_skip_count()
                    return

            logger.info(f'Текущая цена: {current_price}')

            # === ШАГ 3: Получить состояние ===
            last_update = state.get('last_update')

            # === ШАГ 4: Рассчитать решение ===
            decision = calculate_price(
                competitor_prices=competitor_prices,
                current_price=current_price,
                last_update=last_update,
                config=runtime,
                target_competitor_rank=selected_rank,
                force_weak_mode=force_weak_mode,
            )

            logger.info(f'Решение: {decision.action} (причина: {decision.reason})')

            # === ШАГ 5: Выполнить решение ===
            if decision.action == 'update' and decision.price is not None:
                # Обновление цены
                success = await self._update_price(decision.price, decision)

                if success:
                    storage.increment_update_count()
                    storage.update_state(
                        last_price=decision.price,
                        last_update=datetime.now(),
                    )
                    storage.add_price_history(
                        old_price=decision.old_price,
                        new_price=decision.price,
                        competitor_price=decision.competitor_price,
                        reason=decision.reason,
                    )
                else:
                    storage.increment_skip_count()
                    await self._notify_error_throttled(
                        key='update_price_failed',
                        message='Ошибка обновления цены через GGSEL API',
                        cooldown_seconds=180,
                    )
            else:
                # Пропуск
                storage.increment_skip_count()
                await self._notify_skip_throttled(
                    runtime=runtime,
                    current_price=decision.old_price or current_price,
                    target_price=decision.price or current_price,
                    competitor_price=decision.competitor_price or min_price,
                    reason=decision.reason,
                )

        except Exception as e:
            logger.error(f'Ошибка в цикле: {e}', exc_info=True)
            storage.update_state(last_cycle=datetime.now())
            await self._notify_error_throttled(
                key='scheduler_cycle_exception',
                message=f'Ошибка в цикле: {str(e)}',
                cooldown_seconds=120,
            )

    async def _update_price(self, new_price: float, decision) -> bool:
        """
        Обновление цены через API

        Returns:
            True если успешно
        """
        logger.info(f'Обновление цены: {decision.old_price} → {new_price}')

        success = self.api_client.update_price(
            product_id=config.GGSEL_PRODUCT_ID,
            new_price=new_price,
        )

        if success:
            # Отправка уведомления через Telegram бота
            await self.telegram_bot.notify_price_updated(
                old_price=decision.old_price,
                new_price=new_price,
                competitor_price=decision.competitor_price,
                reason=decision.reason,
            )
            logger.info(f'✅ Цена обновлена: {new_price}')
        else:
            logger.error('❌ Ошибка обновления цены')

        return success

    async def run(self):
        """
        Запуск планировщика (бесконечный цикл)
        """
        self._running = True

        logger.info(f'Планировщик запущен (интервал: {config.CHECK_INTERVAL}s)')

        while self._running:
            try:
                await self.run_cycle()

            except KeyboardInterrupt:
                logger.info('Остановка планировщика...')
                break

            except Exception as e:
                logger.error(f'Критическая ошибка в планировщике: {e}', exc_info=True)

            # Ожидание следующего цикла
            logger.debug(f'Ожидание {config.CHECK_INTERVAL} секунд...')
            runtime = storage.get_runtime_config(config)
            await asyncio.sleep(runtime.CHECK_INTERVAL)

        self._running = False
        logger.info('Планировщик остановлен')

    def stop(self):
        """Остановка планировщика"""
        self._running = False


# Глобальный экземпляр (создаётся в main)
scheduler: Optional[Scheduler] = None
