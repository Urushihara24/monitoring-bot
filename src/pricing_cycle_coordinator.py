"""Pricing-cycle orchestration for the modular scheduler runtime.

The coordinator owns cycle control-flow and write-result handling while
reusing the scheduler host's parser, notification, price-read and write
boundaries. Pricing formulas, DRY_RUN interception and storage semantics are
kept unchanged during the staged extraction.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from .logic import calculate_price
from .pricing_mode import normalize_pricing_mode
from .storage import storage
from .validator import validate_runtime_config

logger = logging.getLogger(__name__)


class PricingCycleCoordinator:
    """Coordinate one complete pricing cycle through existing host boundaries."""

    def __init__(self, host: Any) -> None:
        self._host = host

    def __getattr__(self, name: str) -> Any:
        return getattr(self._host, name)

    async def run(self, *, include_chat_autoreply: bool = True) -> None:
        logger.info('[%s] 🔄 Запуск цикла pricing...', self.profile_name)
        if not self._is_tracked_product_active():
            logger.info(
                '[%s] Товар %s удалён из tracked_products, '
                'pricing-цикл пропущен',
                self.profile_name,
                self.product_id,
            )
            return
        if not self._is_pair_enabled():
            logger.info(
                '[%s] Пара %s отключена (PAIR_ENABLED=false), '
                'pricing-цикл пропущен',
                self.profile_name,
                self.product_id,
            )
            return
        try:
            storage.update_state(
                profile_id=self.profile_id,
                last_cycle=datetime.now(),
            )
            synced_from_env = await self._sync_cookies_from_env()
            if not synced_from_env:
                await self._reload_cookies_from_backup()
            runtime = self._runtime()
            state = self._state()

            if include_chat_autoreply and self.chat_autoreply_enabled:
                await self._run_chat_autoreply()

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

            logger.info(
                '[%s] Парсинг %s конкурентов...',
                self.profile_name,
                len(runtime.COMPETITOR_URLS),
            )
            if not runtime.COMPETITOR_URLS:
                logger.info(
                    '[%s] Конкуренты не заданы, цикл мониторинга пропущен',
                    self.profile_name,
                )
                storage.update_state(
                    profile_id=self.profile_id,
                    last_competitor_error='no_competitor_urls',
                    last_competitor_block_reason=None,
                    last_competitor_status_code=None,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return
            if self.product_id <= 0:
                message = (
                    'Некорректный product_id для профиля '
                    f'{self.profile_name}: {self.product_id}'
                )
                logger.error('[%s] %s', self.profile_name, message)
                await self._notify_error_throttled(
                    key='invalid_product_id',
                    message=message,
                    cooldown_seconds=300,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return
            competitor_results = await asyncio.gather(*[
                self._parse_competitor_price(url, runtime=runtime, timeout=15)
                for url in runtime.COMPETITOR_URLS
            ])

            valid_competitors = [
                (runtime.COMPETITOR_URLS[i], r)
                for i, r in enumerate(competitor_results)
                if r.success and r.price is not None
            ]
            if valid_competitors:
                fail_streak_raw = storage.get_runtime_setting(
                    'PARSER_FAIL_STREAK',
                    profile_id=self.profile_id,
                )
                if fail_streak_raw not in (None, '', '0', 0):
                    storage.set_runtime_setting(
                        'PARSER_FAIL_STREAK',
                        '0',
                        source='runtime',
                        profile_id=self.profile_id,
                    )
                    logger.info(
                        '[%s] Parser fail streak сброшен после успешного цикла',
                        self.profile_name,
                    )

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
                fail_streak_raw = storage.get_runtime_setting(
                    'PARSER_FAIL_STREAK',
                    profile_id=self.profile_id,
                )
                try:
                    fail_streak = int(float(fail_streak_raw or 0)) + 1
                except (TypeError, ValueError):
                    fail_streak = 1
                storage.set_runtime_setting(
                    'PARSER_FAIL_STREAK',
                    str(fail_streak),
                    source='runtime',
                    profile_id=self.profile_id,
                )
                failed_items = []
                for idx, parsed in enumerate(competitor_results):
                    if parsed.success:
                        continue
                    source_url = (
                        runtime.COMPETITOR_URLS[idx]
                        if idx < len(runtime.COMPETITOR_URLS)
                        else parsed.url
                    )
                    failed_items.append((source_url, parsed))

                if failed_items:
                    details = []
                    for source_url, parsed in failed_items:
                        reason = (
                            parsed.block_reason
                            or (
                                f'http_{parsed.status_code}'
                                if parsed.status_code else 'parse_failed'
                            )
                        )
                        err = parsed.error or 'unknown'
                        details.append(
                            f'{source_url} (reason={reason}, error={err})'
                        )
                    logger.warning(
                        '[%s] Не удалось получить цены конкурентов '
                        '(fail_streak=%s): %s',
                        self.profile_name,
                        fail_streak,
                        ' | '.join(details),
                    )

                for source_url, parsed in failed_items:
                    await self._notify_parser_issue_if_needed(
                        runtime=runtime,
                        url=source_url,
                        result=parsed,
                        fail_streak=fail_streak,
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
                if getattr(runtime, 'NOTIFY_PARSER_ISSUES', True):
                    await self._notify_error_throttled(
                        key='no_competitor_prices',
                        message='Не удалось получить цены конкурентов',
                        cooldown_seconds=3600,
                    )
                else:
                    logger.info(
                        '[%s] Уведомление no_competitor_prices отключено '
                        '(NOTIFY_PARSER_ISSUES=false)',
                        self.profile_name,
                    )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            considered = valid_competitors
            force_weak_mode = False
            if runtime.POSITION_FILTER_ENABLED:
                ranked = [
                    item for item in valid_competitors
                    if item[1].rank is not None
                ]
                if ranked:
                    strong = [
                        item for item in ranked
                        if item[1].rank <= runtime.WEAK_POSITION_THRESHOLD
                    ]
                    if strong:
                        considered = strong
                    else:
                        considered = valid_competitors
                        force_weak_mode = True
                else:
                    considered = valid_competitors
                    force_weak_mode = (
                        self._should_force_weak_mode_by_unknown_rank(
                            valid_competitors,
                            runtime,
                        )
                    )

            selected_url, selected = min(considered, key=lambda item: item[1].price)
            min_price = selected.price
            selected_rank = selected.rank
            competitor_prices = [item[1].price for item in considered]

            previous_min = state.get('last_competitor_min')
            competitor_changed = (
                previous_min is None
                or abs(min_price - previous_min) >= getattr(
                    runtime,
                    'COMPETITOR_CHANGE_DELTA',
                    0.0001,
                )
            )
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

            current_price = self._read_current_price(runtime=runtime)
            if current_price is None:
                current_price = state.get('last_price')
            if current_price is not None:
                try:
                    current_price = float(current_price)
                except Exception as e:
                    logger.error(
                        '[%s] Некорректное значение текущей цены: %r (%s)',
                        self.profile_name,
                        current_price,
                        e,
                    )
                    current_price = None
            if current_price is None:
                await self._notify_error_throttled(
                    key='no_current_price',
                    message='Не удалось получить текущую цену',
                    cooldown_seconds=180,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return
            state_last_price_raw = state.get('last_price')
            state_last_price = None
            if state_last_price_raw is not None:
                try:
                    state_last_price = float(state_last_price_raw)
                except Exception:
                    state_last_price = None
            ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
            if (
                state_last_price is None
                or abs(current_price - state_last_price) >= ignore_delta
            ):
                storage.update_state(
                    profile_id=self.profile_id,
                    last_price=current_price,
                )
                state['last_price'] = current_price

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

            if (
                getattr(runtime, 'UPDATE_ONLY_ON_COMPETITOR_CHANGE', True)
                and not competitor_changed
            ):
                mode = normalize_pricing_mode(getattr(runtime, 'MODE', 'DUMPING'))
                if (
                    mode == 'SHOWCASE_CYCLE'
                    and self.base_profile_id == 'ggsel'
                    and decision.action == 'update'
                ):
                    ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
                    desired_price = float(
                        getattr(runtime, 'DESIRED_PRICE', decision.price or 0.0)
                        or 0.0
                    )
                    if (
                        desired_price > 0
                        and current_price is not None
                        and current_price < (desired_price - ignore_delta)
                    ):
                        decision.price = desired_price
                        decision.reason = 'showcase_cycle_restore_desired'
                        logger.info(
                            '[%s] Витринный цикл: конкурент не изменился, '
                            'откат к рекомендуемой %.4f',
                            self.profile_name,
                            desired_price,
                        )
                    else:
                        logger.info(
                            '[%s] Витринный цикл: откат не требуется '
                            '(current=%.4f, desired=%.4f)',
                            self.profile_name,
                            float(current_price or 0.0),
                            desired_price,
                        )
                        storage.increment_skip_count(profile_id=self.profile_id)
                        return

                ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
                change_delta = getattr(runtime, 'COMPETITOR_CHANGE_DELTA', 0.0001)
                if decision.action != 'update' or decision.price is None:
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'обновление не требуется',
                        self.profile_name,
                        min_price,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                last_target_price = state.get('last_target_price')
                last_target_comp = state.get('last_target_competitor_min')
                if (
                    last_target_price is not None
                    and last_target_comp is not None
                    and abs(decision.price - last_target_price) < ignore_delta
                    and abs(min_price - last_target_comp) < change_delta
                ):
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'целевая цена %.4f уже применена',
                        self.profile_name,
                        min_price,
                        decision.price,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                last_requested = state.get('last_price')
                if (
                    last_requested is not None
                    and abs(decision.price - last_requested) < ignore_delta
                ):
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'целевая цена %.4f уже была выставлена ранее',
                        self.profile_name,
                        min_price,
                        decision.price,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                drift = abs(decision.price - current_price)
                if drift < ignore_delta:
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'текущая цена уже целевая (drift=%.4f)',
                        self.profile_name,
                        min_price,
                        drift,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                decision.reason = f'reconcile_{decision.reason}'
                logger.info(
                    '[%s] Цена конкурента не изменилась, '
                    'но есть дрейф %.4f -> синхронизирую цену',
                    self.profile_name,
                    drift,
                )

            logger.info(
                '[%s] Итоговое решение: %s (%s)',
                self.profile_name,
                decision.action,
                decision.reason,
            )

            if decision.action == 'update' and decision.price is not None:
                if not self._is_tracked_product_active():
                    logger.info(
                        '[%s] Пара удалена во время цикла, update отменён',
                        self.profile_name,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return
                if not self._is_pair_enabled():
                    logger.info(
                        '[%s] Пара выключена во время цикла, update отменён',
                        self.profile_name,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return
                ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
                last_target_raw = state.get('last_target_price')
                last_update_at = state.get('last_update')
                if (
                    last_target_raw is not None
                    and isinstance(last_update_at, datetime)
                ):
                    try:
                        last_target_price = float(last_target_raw)
                    except Exception:
                        last_target_price = None
                    if last_target_price is not None and (
                        abs(decision.price - last_target_price) < ignore_delta
                    ):
                        recent_window_seconds = max(
                            int(getattr(runtime, 'CHECK_INTERVAL', 60)) * 2,
                            60,
                        )
                        age_seconds = (
                            datetime.now() - last_update_at
                        ).total_seconds()
                        if age_seconds < recent_window_seconds:
                            logger.info(
                                '[%s] Пропуск повторного update: '
                                'целевая %.4f уже выставлялась %.1fs назад',
                                self.profile_name,
                                decision.price,
                                age_seconds,
                            )
                            storage.increment_skip_count(
                                profile_id=self.profile_id,
                            )
                            return
                success = await self._update_price(decision.price, decision)
                if success:
                    applied_price = decision.price
                    verification_price: Optional[float] = None
                    try:
                        verified_price_precise = self._read_current_price(
                            runtime=runtime,
                            allow_low_precision_fallback=False,
                        )
                        if verified_price_precise is not None:
                            verified_precise_value = round(
                                float(verified_price_precise),
                                4,
                            )
                            applied_price = verified_precise_value
                            verification_price = verified_precise_value
                        else:
                            verified_price_fallback = self._read_current_price(
                                runtime=runtime,
                                allow_low_precision_fallback=True,
                            )
                            if verified_price_fallback is not None:
                                verification_price = round(
                                    float(verified_price_fallback),
                                    4,
                                )
                    except Exception as e:
                        logger.warning(
                            '[%s] Не удалось перечитать цену после update: %s',
                            self.profile_name,
                            e,
                        )
                    requested_price = decision.price
                    previous_price = (
                        decision.old_price
                        if decision.old_price is not None
                        else current_price
                    )
                    if (
                        previous_price is not None
                        and verification_price is not None
                        and abs(float(requested_price) - float(previous_price))
                        >= ignore_delta
                        and abs(float(verification_price) - float(previous_price))
                        < ignore_delta
                    ):
                        logger.warning(
                            '[%s] API подтвердил update, но цена не изменилась: '
                            'было=%.4f, запрос=%.4f, стало=%.4f',
                            self.profile_name,
                            float(previous_price),
                            float(requested_price),
                            float(verification_price),
                        )
                        storage.update_state(
                            profile_id=self.profile_id,
                            last_price=verification_price,
                        )
                        storage.increment_skip_count(profile_id=self.profile_id)
                        await self._notify_error_throttled(
                            key='update_price_no_effect',
                            message=(
                                'API подтвердил обновление, но фактическая '
                                'цена не изменилась'
                            ),
                            cooldown_seconds=180,
                        )
                        return

                    storage.increment_update_count(profile_id=self.profile_id)
                    storage.update_state(
                        profile_id=self.profile_id,
                        last_price=applied_price,
                        last_update=datetime.now(),
                        last_target_price=decision.price,
                        last_target_competitor_min=decision.competitor_price,
                    )
                    storage.add_price_history(
                        old_price=decision.old_price,
                        new_price=applied_price,
                        competitor_price=decision.competitor_price,
                        reason=decision.reason,
                        profile_id=self.profile_id,
                    )
                    await self.telegram_bot.notify_price_updated(
                        old_price=decision.old_price,
                        new_price=applied_price,
                        competitor_price=decision.competitor_price,
                        reason=decision.reason,
                        profile_name=self.profile_name,
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
