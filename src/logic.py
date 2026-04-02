"""
Ядро бизнес-логики auto-pricing

Строго следует ТЗ:
1. Базовая формула: my_price = competitor_price - 0.0051
2. Нижний порог: MIN_PRICE + MODE (FIXED/STEP_UP)
3. Множество конкурентов: min(competitor_prices)
4. Фильтр слабого конкурента: LOW_PRICE_THRESHOLD
5. Cooldown: не чаще COOLDOWN_SECONDS
6. Ignore delta: если |new - current| < 0.001 → skip
"""

import logging
import math
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .config import Config

logger = logging.getLogger(__name__)
PRICE_PRECISION = Decimal('0.0001')


def _d(value: float) -> Decimal:
    return Decimal(str(value))


def _to_price(value: Decimal) -> float:
    return float(value.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP))


@dataclass
class PriceDecision:
    """Решение о цене"""
    action: str  # "update" или "skip"
    price: Optional[float]
    reason: str
    old_price: Optional[float] = None
    competitor_price: Optional[float] = None


def calculate_price(
    competitor_prices: List[float],
    current_price: Optional[float],
    last_update: Optional[datetime],
    config: Config,
    target_competitor_rank: Optional[int] = None,
    force_weak_mode: bool = False,
    allow_fast_rebound: bool = False,
) -> PriceDecision:
    """
    Расчёт целевой цены согласно бизнес-логике
    
    Приоритет выполнения:
    1. Получить min цену конкурента
    2. Проверить LOW_PRICE_THRESHOLD
    3. Применить special logic (фильтр слабого конкурента)
    4. Применить базовую формулу (-0.0051)
    5. Проверить MIN_PRICE
    6. Применить MODE (FIXED/STEP_UP)
    7. Проверить MAX_PRICE
    8. Проверить cooldown
    9. Проверить ignore delta
    10. Вернуть решение
    
    Returns:
        PriceDecision с action, price, reason
    """
    now = datetime.now()
    
    # === ШАГ 0: Проверка входных данных ===
    if not competitor_prices:
        logger.warning('Нет цен конкурентов для расчёта')
        return PriceDecision(
            action='skip',
            price=None,
            reason='no_competitor_prices',
        )
    
    # === ШАГ 1: Получить min цену конкурента ===
    min_competitor_price = min(competitor_prices)
    min_competitor_price_d = _d(min_competitor_price)
    undercut_value_d = _d(config.UNDERCUT_VALUE)
    logger.info(f'Минимальная цена конкурента: {min_competitor_price}')
    
    # === ШАГ 2: Проверить LOW_PRICE_THRESHOLD / слабую позицию ===
    weak_by_price = config.LOW_PRICE_THRESHOLD > 0 and min_competitor_price < config.LOW_PRICE_THRESHOLD
    weak_by_position = bool(force_weak_mode)

    if weak_by_price or weak_by_position:
        if weak_by_price:
            logger.info(f'Конкурент ниже порога {config.LOW_PRICE_THRESHOLD}')
        if weak_by_position:
            logger.info(f'Конкурент в слабой позиции (rank={target_competitor_rank})')

        # === ШАГ 3: Применить special logic (фильтр слабого конкурента) ===
        if min_competitor_price < config.WEAK_PRICE_CEIL_LIMIT:
            # Пример: конкурент 0.26 -> ceil до 0.3 -> 0.3 - 0.0051 = 0.2949
            ceil_price = _d(math.ceil(min_competitor_price * 10) / 10)
            new_price_d = ceil_price - undercut_value_d
            new_price = _to_price(new_price_d)
            reason_prefix = 'weak_position' if weak_by_position else 'weak_competitor'
            reason = (
                f'{reason_prefix}_ceil({min_competitor_price}→'
                f'{_to_price(ceil_price)}-{config.UNDERCUT_VALUE})'
            )
            logger.info(
                f'Слабый конкурент (<{config.WEAK_PRICE_CEIL_LIMIT}): '
                f'ceil={_to_price(ceil_price)}, цена={new_price}'
            )
        else:
            new_price = _to_price(_d(config.DESIRED_PRICE))
            reason_prefix = 'weak_position' if weak_by_position else 'weak_competitor'
            reason = f'{reason_prefix}_desired({config.DESIRED_PRICE})'
            logger.info(
                f'Слабый конкурент (>={config.WEAK_PRICE_CEIL_LIMIT}): '
                f'desired={config.DESIRED_PRICE}'
            )
        
        # === ШАГ 8: Проверить MAX_PRICE ===
        if new_price > config.MAX_PRICE:
            new_price = config.MAX_PRICE
            reason += f'_max_capped({config.MAX_PRICE})'
            logger.info(f'Цена ограничена MAX_PRICE: {config.MAX_PRICE}')

        # === ШАГ 9: Применить hard floor / max-down-step ===
        new_price, reason = _apply_loss_protection(
            new_price=new_price,
            current_price=current_price,
            reason=reason,
            config=config,
        )

        # === ШАГ 10: Проверить cooldown ===
        if last_update and (now - last_update).total_seconds() < config.COOLDOWN_SECONDS:
            if not (
                allow_fast_rebound
                and current_price is not None
                and new_price > current_price
            ):
                logger.info(f'Cooldown активен ({config.COOLDOWN_SECONDS}s)')
                return PriceDecision(
                    action='skip',
                    price=new_price,
                    reason=f'cooldown_active_{reason}',
                    old_price=current_price,
                    competitor_price=min_competitor_price,
                )
            reason = f'fast_rebound_{reason}'
            logger.info('Cooldown bypass для быстрого отката вверх')
        
        # === ШАГ 11: Проверить ignore delta ===
        if current_price is not None:
            delta = abs(new_price - current_price)
            if delta < config.IGNORE_DELTA:
                logger.info(f'Delta {delta} < {config.IGNORE_DELTA} → skip')
                return PriceDecision(
                    action='skip',
                    price=new_price,
                    reason=f'ignore_delta_{reason}',
                    old_price=current_price,
                    competitor_price=min_competitor_price,
                )
        
        return PriceDecision(
            action='update',
            price=new_price,
            reason=reason,
            old_price=current_price,
            competitor_price=min_competitor_price,
        )
    
    # === ШАГ 4: Применить базовую формулу (-0.0051) ===
    new_price = _to_price(min_competitor_price_d - undercut_value_d)
    reason = 'base_formula'
    logger.info(
        f'Базовая формула: {min_competitor_price} - {config.UNDERCUT_VALUE} = {new_price}'
    )
    
    # === ШАГ 5: Проверить MAX_PRICE ===
    if new_price > config.MAX_PRICE:
        new_price = _to_price(_d(config.MAX_PRICE))
        reason += f'_max_capped({config.MAX_PRICE})'
        logger.info(f'Цена ограничена MAX_PRICE: {config.MAX_PRICE}')

    # === ШАГ 6: Применить hard floor / max-down-step ===
    new_price, reason = _apply_loss_protection(
        new_price=new_price,
        current_price=current_price,
        reason=reason,
        config=config,
    )

    # === ШАГ 7: Проверить cooldown ===
    if last_update and (now - last_update).total_seconds() < config.COOLDOWN_SECONDS:
        if not (
            allow_fast_rebound
            and current_price is not None
            and new_price > current_price
        ):
            logger.info(f'Cooldown активен ({config.COOLDOWN_SECONDS}s)')
            return PriceDecision(
                action='skip',
                price=new_price,
                reason=f'cooldown_active_{reason}',
                old_price=current_price,
                competitor_price=min_competitor_price,
            )
        reason = f'fast_rebound_{reason}'
        logger.info('Cooldown bypass для быстрого отката вверх')
    
    # === ШАГ 8: Проверить ignore delta ===
    if current_price is not None:
        delta = abs(new_price - current_price)
        if delta < config.IGNORE_DELTA:
            logger.info(f'Delta {delta} < {config.IGNORE_DELTA} → skip')
            return PriceDecision(
                action='skip',
                price=new_price,
                reason=f'ignore_delta_{reason}',
                old_price=current_price,
                competitor_price=min_competitor_price,
            )

    # === ШАГ 9: Вернуть решение ===
    return PriceDecision(
        action='update',
        price=new_price,
        reason=reason,
        old_price=current_price,
        competitor_price=min_competitor_price,
    )


# Глобальная функция для удобства
def calculate(
    competitor_prices: List[float],
    current_price: Optional[float],
    last_update: Optional[datetime],
) -> PriceDecision:
    """Обёртка для calculate_price с глобальным config"""
    return calculate_price(competitor_prices, current_price, last_update, config)


def _apply_loss_protection(
    *,
    new_price: float,
    current_price: Optional[float],
    reason: str,
    config: Config,
) -> tuple[float, str]:
    """
    Применяет ограничения на убыточные/слишком резкие движения цены.
    """
    candidate = _d(new_price)
    reason_out = reason

    # Hard floor: цена не может уйти ниже MIN_PRICE.
    if getattr(config, 'HARD_FLOOR_ENABLED', True):
        min_price = _d(config.MIN_PRICE)
        if candidate < min_price:
            if config.MODE == 'FIXED':
                fixed_target = max(_d(config.FIXED_PRICE), min_price)
                candidate = fixed_target
                reason_out += f'_hard_floor_fixed({float(candidate)})'
            elif config.MODE == 'STEP_UP' and current_price is not None:
                step_target = max(_d(current_price) + _d(config.STEP_UP_VALUE), min_price)
                candidate = step_target
                reason_out += f'_hard_floor_step_up({float(candidate)})'
            else:
                candidate = min_price
                reason_out += f'_hard_floor_min({config.MIN_PRICE})'

    # Ограничение резкого снижения за цикл.
    max_down_step = max(getattr(config, 'MAX_DOWN_STEP', 0.0), 0.0)
    if (
        max_down_step > 0
        and current_price is not None
        and candidate < _d(current_price)
    ):
        max_allowed = _d(current_price) - _d(max_down_step)
        if candidate < max_allowed:
            candidate = max_allowed
            reason_out += f'_max_down_step({max_down_step})'

    # Дополнительный контроль MAX_PRICE после модификаций.
    if candidate > _d(config.MAX_PRICE):
        candidate = _d(config.MAX_PRICE)
        reason_out += f'_max_capped({config.MAX_PRICE})'

    return _to_price(candidate), reason_out
