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
        
        # === ШАГ 9: Проверить cooldown ===
        if last_update and (now - last_update).total_seconds() < config.COOLDOWN_SECONDS:
            logger.info(f'Cooldown активен ({config.COOLDOWN_SECONDS}s)')
            return PriceDecision(
                action='skip',
                price=new_price,
                reason=f'cooldown_active_{reason}',
                old_price=current_price,
                competitor_price=min_competitor_price,
            )
        
        # === ШАГ 10: Проверить ignore delta ===
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

    # === ШАГ 6: Проверить cooldown ===
    if last_update and (now - last_update).total_seconds() < config.COOLDOWN_SECONDS:
        logger.info(f'Cooldown активен ({config.COOLDOWN_SECONDS}s)')
        return PriceDecision(
            action='skip',
            price=new_price,
            reason=f'cooldown_active_{reason}',
            old_price=current_price,
            competitor_price=min_competitor_price,
        )
    
    # === ШАГ 7: Проверить ignore delta ===
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

    # === ШАГ 8: Вернуть решение ===
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
