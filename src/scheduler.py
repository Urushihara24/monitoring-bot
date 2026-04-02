"""
Scheduler - циклический обработчик auto-pricing.
Поддерживает профильный режим (GGSEL / DigiSeller).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from dotenv import dotenv_values

from .config import config
from .distill_parser import init_distill_parser
from .logic import calculate_price
from .rsc_parser import ParseResult, rsc_parser
from .storage import DEFAULT_PROFILE, storage
from .validator import validate_runtime_config

if TYPE_CHECKING:
    from .api_client import GGSELClient
    from .telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Планировщик задач auto-pricing.

    Цикл:
    1. Парсим цены конкурентов
    2. Получаем текущую цену товара
    3. Рассчитываем целевую цену
    4. Обновляем цену через API (или skip)
    5. Сохраняем state/историю
    6. Отправляем уведомления
    """

    def __init__(
        self,
        api_client: 'GGSELClient',
        telegram_bot: 'TelegramBot',
        *,
        profile_id: str = DEFAULT_PROFILE,
        profile_name: str = 'GGSEL',
        product_id: Optional[int] = None,
        competitor_urls: Optional[list] = None,
    ):
        self.api_client = api_client
        self.telegram_bot = telegram_bot
        self.profile_id = (profile_id or DEFAULT_PROFILE).strip().lower()
        self.profile_name = profile_name
        self.product_id = int(product_id or 0)
        self.default_competitor_urls = competitor_urls or []
        self._running = False
        self._cookies_last_update: Optional[datetime] = None
        self.distill = init_distill_parser(config)

    def _runtime(self):
        return storage.get_runtime_config(
            config,
            profile_id=self.profile_id,
            default_urls=self.default_competitor_urls,
        )

    def _state(self):
        return storage.get_state(profile_id=self.profile_id)

    def _tag(self, message: str) -> str:
        return f'[{self.profile_name}] {message}'

    async def _notify_error_throttled(
        self,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
    ):
        if storage.should_send_alert(
            key=key,
            cooldown_seconds=cooldown_seconds,
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_error(self._tag(message))
        else:
            logger.info(
                '[%s] Уведомление подавлено throttling: key=%s',
                self.profile_name,
                key,
            )

    async def _notify_skip_throttled(
        self,
        runtime,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
    ):
        if not getattr(runtime, 'NOTIFY_SKIP', False):
            return
        if storage.should_send_alert(
            key='skip_notification',
            cooldown_seconds=getattr(runtime, 'NOTIFY_SKIP_COOLDOWN_SECONDS', 300),
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_skip(
                current_price=current_price,
                target_price=target_price,
                competitor_price=competitor_price,
                reason=reason,
                profile_name=self.profile_name,
            )
        else:
            logger.info('[%s] Skip-уведомление подавлено', self.profile_name)

    async def _notify_competitor_change_if_needed(
        self,
        runtime,
        old_price: Optional[float],
        new_price: float,
        rank: Optional[int],
        url: Optional[str],
    ):
        if not getattr(runtime, 'NOTIFY_COMPETITOR_CHANGE', True):
            return
        if old_price is None:
            return
        delta = abs(new_price - old_price)
        if delta < getattr(runtime, 'COMPETITOR_CHANGE_DELTA', 0.0001):
            return
        if storage.should_send_alert(
            key='competitor_price_change',
            cooldown_seconds=getattr(
                runtime,
                'COMPETITOR_CHANGE_COOLDOWN_SECONDS',
                60,
            ),
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_competitor_price_changed(
                old_price=old_price,
                new_price=new_price,
                delta=delta,
                rank=rank,
                url=url,
                profile_name=self.profile_name,
            )

    async def _notify_parser_issue_if_needed(
        self,
        runtime,
        url: str,
        result: ParseResult,
    ):
        if not getattr(runtime, 'NOTIFY_PARSER_ISSUES', True):
            return
        reason = (
            result.block_reason
            or (f'http_{result.status_code}' if result.status_code else None)
            or 'parse_failed'
        )
        key = f'parser_issue:{reason}'
        if not storage.should_send_alert(
            key=key,
            cooldown_seconds=getattr(
                runtime,
                'PARSER_ISSUE_COOLDOWN_SECONDS',
                300,
            ),
            profile_id=self.profile_id,
        ):
            return
        await self.telegram_bot.notify_parser_issue(
            url=url,
            method=result.method,
            reason=reason,
            error=result.error or 'unknown',
            status_code=result.status_code,
            profile_name=self.profile_name,
        )

    async def _check_and_update_cookies(self) -> bool:
        """
        Проверка cookies на протухание и автообновление.
        """
        if not config.AUTO_UPDATE_COOKIES:
            return True

        cookies_backup_path = Path(config.COMPETITOR_COOKIES_BACKUP_PATH)
        if not cookies_backup_path.exists():
            logger.warning(
                '[%s] Файл cookies_backup.json не найден, пропускаю проверку',
                self.profile_name,
            )
            return True

        file_mtime = datetime.fromtimestamp(cookies_backup_path.stat().st_mtime)
        age_seconds = (datetime.now() - file_mtime).total_seconds()
        if age_seconds < config.COOKIES_EXPIRE_SECONDS:
            logger.debug(
                '[%s] Cookies актуальны (возраст: %ss)',
                self.profile_name,
                int(age_seconds),
            )
            return True

        logger.warning(
            '[%s] Cookies протухли по таймеру (%ss > %ss), запускаю обновление...',
            self.profile_name,
            int(age_seconds),
            config.COOKIES_EXPIRE_SECONDS,
        )
        return await self._update_cookies_now()

    async def _update_cookies_now(self) -> bool:
        script_path = Path(config.COOKIES_UPDATE_SCRIPT)
        if not script_path.exists():
            logger.error(
                '[%s] Скрипт обновления cookies не найден: %s',
                self.profile_name,
                script_path,
            )
            return False

        try:
            result = subprocess.run(
                ['bash', str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error(
                    '[%s] Ошибка обновления cookies (code=%s). stderr=%s stdout=%s',
                    self.profile_name,
                    result.returncode,
                    (result.stderr or '').strip(),
                    (result.stdout or '').strip(),
                )
                return False

            logger.info('[%s] ✅ Cookies успешно обновлены', self.profile_name)
            if result.stdout:
                logger.debug(
                    '[%s] stdout скрипта cookies: %s',
                    self.profile_name,
                    result.stdout.strip(),
                )
            self._cookies_last_update = datetime.now()
            env_loaded = await self._sync_cookies_from_env()
            backup_loaded = await self._reload_cookies_from_backup()
            if not env_loaded and not backup_loaded:
                logger.error(
                    '[%s] Не удалось загрузить cookies в runtime '
                    'ни из .env, ни из backup',
                    self.profile_name,
                )
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error('[%s] Таймаут обновления cookies', self.profile_name)
            return False
        except Exception as e:
            logger.error(
                '[%s] Ошибка выполнения скрипта cookies: %s',
                self.profile_name,
                e,
            )
            return False

    async def _sync_cookies_from_env(self) -> bool:
        """
        Подтягивает COMPETITOR_COOKIES из .env в runtime settings.
        """
        env_path = Path('.env')
        if not env_path.exists():
            return False
        try:
            env_data = dotenv_values(str(env_path))
            env_cookies = str(env_data.get('COMPETITOR_COOKIES') or '').strip()
            if not env_cookies:
                return False
            current = storage.get_runtime_setting(
                'COMPETITOR_COOKIES',
                profile_id=self.profile_id,
            )
            if current != env_cookies:
                storage.set_runtime_setting(
                    'COMPETITOR_COOKIES',
                    env_cookies,
                    source='env_sync',
                    profile_id=self.profile_id,
                )
                logger.info(
                    '[%s] Cookies синхронизированы из .env (%s символов)',
                    self.profile_name,
                    len(env_cookies),
                )
            return True
        except Exception as e:
            logger.error(
                '[%s] Ошибка синхронизации cookies из .env: %s',
                self.profile_name,
                e,
            )
            return False

    async def _reload_cookies_from_backup(self) -> bool:
        cookies_backup_path = Path(config.COMPETITOR_COOKIES_BACKUP_PATH)
        if not cookies_backup_path.exists():
            return False
        try:
            import json

            with open(cookies_backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cookies_list = data.get('cookies', [])
            cookie_parts = []
            for cookie in cookies_list:
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                if name and value:
                    cookie_parts.append(f'{name}={value}')
            if not cookie_parts:
                return False
            cookie_string = '; '.join(cookie_parts)
            current = storage.get_runtime_setting(
                'COMPETITOR_COOKIES',
                profile_id=self.profile_id,
            )
            if current != cookie_string:
                storage.set_runtime_setting(
                    'COMPETITOR_COOKIES',
                    cookie_string,
                    source='backup_sync',
                    profile_id=self.profile_id,
                )
            logger.info(
                '[%s] Cookies перезагружены в runtime (%s cookies)',
                self.profile_name,
                len(cookie_parts),
            )
            return True
        except Exception as e:
            logger.error(
                '[%s] Ошибка перезагрузки cookies: %s',
                self.profile_name,
                e,
            )
            return False

    async def _parse_competitor_price(
        self,
        url: str,
        runtime,
        timeout: int = 15,
    ) -> ParseResult:
        """
        Каскадный парсинг:
        RSC (stealth->playwright->selenium) -> Distill.
        """
        logger.info('[%s] 🔍 Парсинг цены: %s', self.profile_name, url)
        cookies = runtime.COMPETITOR_COOKIES or config.COMPETITOR_COOKIES or None

        result = rsc_parser.parse_url(
            url,
            timeout=timeout,
            cookies=cookies,
            use_playwright=getattr(runtime, 'RSC_USE_PLAYWRIGHT', True),
            use_selenium_fallback=getattr(
                runtime,
                'RSC_USE_SELENIUM_FALLBACK',
                True,
            ),
            selenium_use_real_profile=getattr(
                runtime,
                'SELENIUM_USE_REAL_PROFILE',
                False,
            ),
            selenium_user_data_dir=getattr(
                runtime,
                'SELENIUM_CHROME_USER_DATA_DIR',
                '',
            ),
            selenium_profile_dir=getattr(
                runtime,
                'SELENIUM_CHROME_PROFILE_DIR',
                'Default',
            ),
            selenium_headless=getattr(runtime, 'SELENIUM_HEADLESS', True),
        )
        if result.success:
            return result

        # Важно: при cookies_expired пробуем обновить и сразу повторить парсинг.
        if result.cookies_expired and config.AUTO_UPDATE_COOKIES:
            logger.warning(
                '[%s] Cookies протухли для %s, запускаю refresh...',
                self.profile_name,
                url,
            )
            refreshed = await self._update_cookies_now()
            if refreshed:
                refreshed_runtime = self._runtime()
                refreshed_cookies = (
                    refreshed_runtime.COMPETITOR_COOKIES
                    or config.COMPETITOR_COOKIES
                    or None
                )
                retry_result = rsc_parser.parse_url(
                    url,
                    timeout=timeout,
                    cookies=refreshed_cookies,
                    use_playwright=getattr(
                        refreshed_runtime,
                        'RSC_USE_PLAYWRIGHT',
                        True,
                    ),
                    use_selenium_fallback=(
                        getattr(
                            refreshed_runtime,
                            'RSC_USE_SELENIUM_FALLBACK',
                            True,
                        )
                    ),
                    selenium_use_real_profile=(
                        getattr(
                            refreshed_runtime,
                            'SELENIUM_USE_REAL_PROFILE',
                            False,
                        )
                    ),
                    selenium_user_data_dir=(
                        getattr(
                            refreshed_runtime,
                            'SELENIUM_CHROME_USER_DATA_DIR',
                            '',
                        )
                    ),
                    selenium_profile_dir=(
                        getattr(
                            refreshed_runtime,
                            'SELENIUM_CHROME_PROFILE_DIR',
                            'Default',
                        )
                    ),
                    selenium_headless=getattr(
                        refreshed_runtime,
                        'SELENIUM_HEADLESS',
                        True,
                    ),
                )
                if retry_result.success:
                    return retry_result
                result = retry_result

        # Distill fallback.
        if self.distill and (self.distill.api_key or self.distill.local_data_dir):
            logger.info('[%s] Пробуем Distill fallback: %s', self.profile_name, url)
            distill_result = self.distill.get_price(url, timeout=timeout)
            if distill_result.success:
                return ParseResult(
                    success=True,
                    price=distill_result.price,
                    url=url,
                    method=f'distill_{distill_result.method}',
                )

        return result

    async def run_cycle(self):
        logger.info('[%s] 🔄 Запуск цикла pricing...', self.profile_name)
        try:
            storage.update_state(
                profile_id=self.profile_id,
                last_cycle=datetime.now(),
            )
            # На каждом цикле подтягиваем свежие cookies из .env,
            # чтобы не требовать перезапуска процесса после обновления.
            await self._sync_cookies_from_env()
            runtime = self._runtime()
            state = self._state()

            is_valid, errors = validate_runtime_config(runtime)
            if not is_valid:
                message = 'Некорректные runtime-настройки: ' + '; '.join(errors[:5])
                logger.error('[%s] %s', self.profile_name, message)
                await self._notify_error_throttled(
                    key='invalid_runtime_config',
                    message=message,
                    cooldown_seconds=180,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            if runtime.COMPETITOR_COOKIES or config.AUTO_UPDATE_COOKIES:
                cookies_ok = await self._check_and_update_cookies()
                if not cookies_ok:
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

            logger.info(
                '[%s] Парсинг %s конкурентов...',
                self.profile_name,
                len(runtime.COMPETITOR_URLS),
            )
            competitor_results = await asyncio.gather(*[
                self._parse_competitor_price(url, runtime=runtime, timeout=15)
                for url in runtime.COMPETITOR_URLS
            ])

            for idx, parsed in enumerate(competitor_results):
                if parsed.success:
                    continue
                source_url = (
                    runtime.COMPETITOR_URLS[idx]
                    if idx < len(runtime.COMPETITOR_URLS) else parsed.url
                )
                await self._notify_parser_issue_if_needed(
                    runtime=runtime,
                    url=source_url,
                    result=parsed,
                )

            valid_competitors = [
                (runtime.COMPETITOR_URLS[i], r)
                for i, r in enumerate(competitor_results)
                if r.success and r.price is not None
            ]

            state = self._state()
            auto_mode = state.get('auto_mode', True)
            if not auto_mode:
                if valid_competitors:
                    _, best = min(valid_competitors, key=lambda item: item[1].price)
                    storage.update_state(
                        profile_id=self.profile_id,
                        last_competitor_price=best.price,
                        last_competitor_min=best.price,
                        last_competitor_rank=best.rank,
                        last_competitor_url=best.url,
                        last_competitor_parse_at=datetime.now(),
                        last_competitor_method=best.method,
                        last_competitor_error=None,
                        last_competitor_block_reason=None,
                        last_competitor_status_code=best.status_code,
                    )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            if not valid_competitors:
                first_error = next(
                    (r for r in competitor_results if not r.success),
                    None,
                )
                storage.update_state(
                    profile_id=self.profile_id,
                    last_competitor_error=first_error.error if first_error else None,
                    last_competitor_block_reason=(
                        first_error.block_reason if first_error else None
                    ),
                    last_competitor_status_code=(
                        first_error.status_code if first_error else None
                    ),
                )
                await self._notify_error_throttled(
                    key='no_competitor_prices',
                    message='Не удалось получить цены конкурентов',
                    cooldown_seconds=3600,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            considered = valid_competitors
            force_weak_mode = False
            if runtime.POSITION_FILTER_ENABLED:
                strong = [
                    item for item in valid_competitors
                    if item[1].rank is None
                    or item[1].rank <= runtime.WEAK_POSITION_THRESHOLD
                ]
                if strong:
                    considered = strong
                else:
                    considered = valid_competitors
                    force_weak_mode = True

            selected_url, selected = min(considered, key=lambda item: item[1].price)
            min_price = selected.price
            selected_rank = selected.rank
            competitor_prices = [item[1].price for item in considered]

            previous_min = state.get('last_competitor_min')
            competitor_rebound = (
                previous_min is not None
                and (min_price - previous_min) >= getattr(
                    runtime,
                    'FAST_REBOUND_DELTA',
                    0.01,
                )
            )

            await self._notify_competitor_change_if_needed(
                runtime=runtime,
                old_price=previous_min,
                new_price=min_price,
                rank=selected_rank,
                url=selected_url,
            )
            storage.update_state(
                profile_id=self.profile_id,
                last_competitor_price=min_price,
                last_competitor_min=min_price,
                last_competitor_rank=selected_rank,
                last_competitor_url=selected_url,
                last_competitor_parse_at=datetime.now(),
                last_competitor_method=selected.method,
                last_competitor_error=None,
                last_competitor_block_reason=None,
                last_competitor_status_code=selected.status_code,
            )

            current_price = self.api_client.get_my_price(self.product_id)
            if current_price is None:
                current_price = state.get('last_price')
            if current_price is None:
                await self._notify_error_throttled(
                    key='no_current_price',
                    message='Не удалось получить текущую цену',
                    cooldown_seconds=180,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            decision = calculate_price(
                competitor_prices=competitor_prices,
                current_price=current_price,
                last_update=state.get('last_update'),
                config=runtime,
                target_competitor_rank=selected_rank,
                force_weak_mode=force_weak_mode,
                allow_fast_rebound=(
                    competitor_rebound
                    and getattr(
                        runtime,
                        'FAST_REBOUND_BYPASS_COOLDOWN',
                        True,
                    )
                ),
            )
            logger.info(
                '[%s] Решение: %s (%s)',
                self.profile_name,
                decision.action,
                decision.reason,
            )

            if decision.action == 'update' and decision.price is not None:
                success = await self._update_price(decision.price, decision)
                if success:
                    storage.increment_update_count(profile_id=self.profile_id)
                    storage.update_state(
                        profile_id=self.profile_id,
                        last_price=decision.price,
                        last_update=datetime.now(),
                    )
                    storage.add_price_history(
                        old_price=decision.old_price,
                        new_price=decision.price,
                        competitor_price=decision.competitor_price,
                        reason=decision.reason,
                        profile_id=self.profile_id,
                    )
                else:
                    storage.increment_skip_count(profile_id=self.profile_id)
                    await self._notify_error_throttled(
                        key='update_price_failed',
                        message='Ошибка обновления цены через API',
                        cooldown_seconds=180,
                    )
                return

            storage.increment_skip_count(profile_id=self.profile_id)
            await self._notify_skip_throttled(
                runtime=runtime,
                current_price=decision.old_price or current_price,
                target_price=decision.price or current_price,
                competitor_price=decision.competitor_price or min_price,
                reason=decision.reason,
            )
        except Exception as e:
            logger.error(
                '[%s] Ошибка в цикле: %s',
                self.profile_name,
                e,
                exc_info=True,
            )
            storage.update_state(
                profile_id=self.profile_id,
                last_cycle=datetime.now(),
            )
            await self._notify_error_throttled(
                key='scheduler_cycle_exception',
                message=f'Ошибка в цикле: {e}',
                cooldown_seconds=120,
            )

    async def _update_price(self, new_price: float, decision) -> bool:
        logger.info(
            '[%s] Обновление цены: %s -> %s',
            self.profile_name,
            decision.old_price,
            new_price,
        )
        success = self.api_client.update_price(
            product_id=self.product_id,
            new_price=new_price,
        )
        if success:
            await self.telegram_bot.notify_price_updated(
                old_price=decision.old_price,
                new_price=new_price,
                competitor_price=decision.competitor_price,
                reason=decision.reason,
                profile_name=self.profile_name,
            )
        return success

    async def run(self):
        self._running = True
        runtime = self._runtime()
        logger.info(
            '[%s] Планировщик запущен (интервал: %ss)',
            self.profile_name,
            runtime.CHECK_INTERVAL,
        )
        while self._running:
            try:
                await self.run_cycle()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(
                    '[%s] Критическая ошибка планировщика: %s',
                    self.profile_name,
                    e,
                    exc_info=True,
                )
            runtime = self._runtime()
            await asyncio.sleep(runtime.CHECK_INTERVAL)
        self._running = False
        logger.info('[%s] Планировщик остановлен', self.profile_name)

    def stop(self):
        self._running = False


scheduler: Optional[Scheduler] = None
