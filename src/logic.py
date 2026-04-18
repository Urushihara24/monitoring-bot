"""
Ядро бизнес-логики auto-pricing

Строго следует ТЗ:
1. Базовая формула: my_price = competitor_price - 0.0051
2. Режим цены: базовый демпинг / следование за ценой конкурента
3. Нижний порог / защита от убыточной цены
4. Множество конкурентов: min(competitor_prices)
5. Фильтр слабого конкурента: только при слабой позиции (force_weak_mode)
6. Cooldown: не чаще COOLDOWN_SECONDS
7. Ignore delta: если |new - current| < 0.001 → skip
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
SHOWCASE_PRECISION = Decimal('0.01')
DUMPING_OFFSET = Decimal('0.0051')
RAISE_OFFSET = Decimal('0.0049')


def _d(value: float) -> Decimal:
    return Decimal(str(value))


def _to_price(value: Decimal) -> float:
    return float(value.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP))


def _round_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (
        (value / step).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * step
    )


def _normalize_pricing_mode(mode: object) -> str:
    normalized = str(mode or '').strip().upper()
    aliases = {
        'FOLLOW_EXACT': 'FOLLOW',
        'FOLLOW_PLUS': 'RAISE',
        'FIXED': 'DUMPING',
        'STEP_UP': 'DUMPING',
        'СЛЕДОВАНИЕ': 'FOLLOW',
        'ДЕМПИНГ': 'DUMPING',
        'ПОВЫШЕНИЕ': 'RAISE',
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {'FOLLOW', 'DUMPING', 'RAISE'} else 'DUMPING'


def _is_legacy_limit_mode(mode: object) -> bool:
    raw = str(mode or '').strip().upper()
    return raw in {'FIX', 'FIXED', 'STEP', 'STEP_UP', 'ФИКС', 'ШАГ'}


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
    2. Проверить режим слабой позиции (force_weak_mode)
    3. Применить special logic (фильтр слабого конкурента)
    4. Рассчитать цену по режиму (base/follow)
    5. Проверить MIN_PRICE
    6. Применить защиту от убыточной цены
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
    
    # === ШАГ 2: Проверить слабую позицию ===
    weak_by_position = bool(force_weak_mode)

    if weak_by_position:
        logger.info(f'Конкурент в слабой позиции (rank={target_competitor_rank})')

        # === ШАГ 3: Применить special logic (фильтр слабого конкурента) ===
        if min_competitor_price < config.WEAK_PRICE_CEIL_LIMIT:
            # Пример: конкурент 0.26 -> ceil до 0.3 -> 0.3 - 0.0051 = 0.2949
            ceil_price = _d(math.ceil(min_competitor_price * 10) / 10)
            new_price_d = ceil_price - undercut_value_d
            new_price = _to_price(new_price_d)
            reason = (
                f'weak_position_ceil({min_competitor_price}→'
                f'{_to_price(ceil_price)}-{config.UNDERCUT_VALUE})'
            )
            logger.info(
                f'Слабый конкурент (<{config.WEAK_PRICE_CEIL_LIMIT}): '
                f'ceil={_to_price(ceil_price)}, цена={new_price}'
            )
        else:
            new_price = _to_price(_d(config.DESIRED_PRICE))
            reason = f'weak_position_desired({config.DESIRED_PRICE})'
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
    
    # === ШАГ 4: Рассчитать целевую цену по выбранному режиму ===
    raw_mode = getattr(config, 'MODE', 'DUMPING')
    mode = _normalize_pricing_mode(raw_mode)
    if mode == 'FOLLOW':
        new_price = _to_price(min_competitor_price_d)
        reason = 'follow'
        logger.info(
            'Режим FOLLOW: цена конкурента %s -> %s',
            min_competitor_price,
            new_price,
        )
    elif mode == 'RAISE':
        round_step = _d(max(getattr(config, 'SHOWCASE_ROUND_STEP', 0.01), 0.0))
        showcase_anchor = (
            _round_to_step(min_competitor_price_d, round_step)
            if round_step > 0
            else min_competitor_price_d
        )
        raise_value_d = _d(getattr(config, 'RAISE_VALUE', float(RAISE_OFFSET)))
        new_price = _to_price(showcase_anchor + raise_value_d)
        reason = (
            'raise_showcase('
            f'{float(showcase_anchor)}+'
            f'{float(raise_value_d)})'
        )
        logger.info(
            'Режим RAISE: база %s + %s = %s (round_step=%s)',
            float(showcase_anchor),
            float(raise_value_d),
            new_price,
            float(round_step),
        )
    else:
        round_step = _d(max(getattr(config, 'SHOWCASE_ROUND_STEP', 0.01), 0.0))
        showcase_anchor = (
            _round_to_step(min_competitor_price_d, round_step)
            if round_step > 0
            else min_competitor_price_d
        )
        undercut_value_d = _d(config.UNDERCUT_VALUE)
        new_price = _to_price(showcase_anchor - undercut_value_d)
        reason = (
            'dumping_showcase('
            f'{float(showcase_anchor)}-'
            f'{float(undercut_value_d)})'
        )
        logger.info(
            'Режим DUMPING: база %s - %s = %s (round_step=%s)',
            float(showcase_anchor),
            float(undercut_value_d),
            new_price,
            float(round_step),
        )

    # === ШАГ 5: Применить пороги / отскок / защиту ===
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
            if getattr(config, 'REBOUND_TO_DESIRED_ON_MIN', False):
                desired_price = _d(getattr(config, 'DESIRED_PRICE', config.MIN_PRICE))
                rebound_candidate = desired_price
                if rebound_candidate < min_price:
                    rebound_candidate = min_price
                max_price = _d(config.MAX_PRICE)
                if rebound_candidate > max_price:
                    rebound_candidate = max_price
                candidate = rebound_candidate
                reason_out += (
                    f'_rebound_to_desired({float(rebound_candidate)})'
                )
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
