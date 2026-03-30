"""
Тесты для logic.py (бизнес-логика)
"""

import pytest
from datetime import datetime, timedelta
from src.logic import calculate_price, PriceDecision
from src.config import Config


class TestLogicBaseFormula:
    """Тесты базовой формулы демпинга"""

    def test_base_demping_formula(self):
        """Должен рассчитывать цену как competitor_price - 0.0051"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.MAX_PRICE = 10.0
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[0.30],
            current_price=0.28,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert abs(decision.price - 0.2949) < 0.0001
        assert 'base_formula' in decision.reason

    def test_no_competitor_prices(self):
        """Должен пропускать если нет цен конкурентов"""
        config = Config()

        decision = calculate_price(
            competitor_prices=[],
            current_price=0.28,
            last_update=None,
            config=config,
        )

        assert decision.action == 'skip'
        assert decision.reason == 'no_competitor_prices'


class TestMinPrice:
    """Тесты нижнего порога"""

    def test_price_below_min_fixed_mode(self):
        """MODE=FIXED: должен устанавливать FIXED_PRICE при цене ниже MIN_PRICE"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.MODE = 'FIXED'
        config.FIXED_PRICE = 0.35
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[0.20],  # Ниже MIN_PRICE
            current_price=0.28,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert decision.price == 0.35  # FIXED_PRICE
        assert 'min_price_fixed' in decision.reason

    def test_price_below_min_step_up_mode(self):
        """MODE=STEP_UP: должен повышать на STEP_UP_VALUE"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.MODE = 'STEP_UP'
        config.STEP_UP_VALUE = 0.05
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[0.20],
            current_price=0.25,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert decision.price == 0.30  # 0.25 + 0.05
        assert 'min_price_step_up' in decision.reason


class TestMultipleCompetitors:
    """Тесты множества конкурентов"""

    def test_use_min_competitor_price(self):
        """Должен использовать минимальную цену конкурента"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[0.35, 0.30, 0.32],  # Минимум: 0.30
            current_price=0.28,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert abs(decision.price - 0.2949) < 0.0001  # 0.30 - 0.0051


class TestWeakCompetitor:
    """Тесты фильтра слабого конкурента"""

    def test_weak_competitor_below_threshold(self):
        """Конкурент ниже LOW_PRICE_THRESHOLD и < 0.3"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.LOW_PRICE_THRESHOLD = 0.5
        config.DESIRED_PRICE = 0.35

        decision = calculate_price(
            competitor_prices=[0.20],  # < 0.3 и < 0.5
            current_price=0.28,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        # ceil(0.20 * 10) / 10 - 0.0051 = 0.2 - 0.0051 = 0.1949
        assert abs(decision.price - 0.1949) < 0.0001
        assert 'weak_competitor_ceil' in decision.reason

    def test_weak_competitor_above_0_3(self):
        """Конкурент ниже LOW_PRICE_THRESHOLD но >= 0.3"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.LOW_PRICE_THRESHOLD = 0.5
        config.DESIRED_PRICE = 0.35

        decision = calculate_price(
            competitor_prices=[0.40],  # >= 0.3 но < 0.5
            current_price=0.28,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert decision.price == 0.35  # DESIRED_PRICE
        assert 'weak_competitor_desired' in decision.reason


class TestCooldown:
    """Тесты cooldown"""

    def test_cooldown_active(self):
        """Должен пропускать если cooldown активен"""
        config = Config()
        config.COOLDOWN_SECONDS = 30
        config.MIN_PRICE = 0.25
        config.LOW_PRICE_THRESHOLD = 0

        # Последнее обновление 10 секунд назад
        last_update = datetime.now() - timedelta(seconds=10)

        decision = calculate_price(
            competitor_prices=[0.30],
            current_price=0.28,
            last_update=last_update,
            config=config,
        )

        assert decision.action == 'skip'
        assert 'cooldown_active' in decision.reason

    def test_cooldown_expired(self):
        """Должен обновлять если cooldown истёк"""
        config = Config()
        config.COOLDOWN_SECONDS = 30
        config.MIN_PRICE = 0.25
        config.LOW_PRICE_THRESHOLD = 0

        # Последнее обновление 60 секунд назад
        last_update = datetime.now() - timedelta(seconds=60)

        decision = calculate_price(
            competitor_prices=[0.30],
            current_price=0.28,
            last_update=last_update,
            config=config,
        )

        assert decision.action == 'update'


class TestIgnoreDelta:
    """Тесты ignore delta"""

    def test_ignore_delta_small_difference(self):
        """Должен пропускать если разница меньше IGNORE_DELTA"""
        config = Config()
        config.IGNORE_DELTA = 0.001
        config.MIN_PRICE = 0.25
        config.LOW_PRICE_THRESHOLD = 0

        # Целевая цена 0.2949, текущая 0.2945 (разница 0.0004 < 0.001)
        decision = calculate_price(
            competitor_prices=[0.30],
            current_price=0.2945,
            last_update=None,
            config=config,
        )

        assert decision.action == 'skip'
        assert 'ignore_delta' in decision.reason


class TestMaxPrice:
    """Тесты максимального порога"""

    def test_max_price_cap(self):
        """Должен ограничивать цену сверху MAX_PRICE"""
        config = Config()
        config.MIN_PRICE = 0.25
        config.MAX_PRICE = 0.50
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[1.00],  # 1.00 - 0.0051 = 0.9949 > 0.50
            current_price=0.40,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert decision.price == 0.50  # MAX_PRICE
        assert 'max_capped' in decision.reason


class TestEdgeCases:
    """Тесты пограничных случаев"""

    def test_very_small_prices(self):
        """Должен работать с очень маленькими ценами"""
        config = Config()
        config.MIN_PRICE = 0.01
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[0.015],
            current_price=0.012,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert decision.price >= 0.01

    def test_very_large_prices(self):
        """Должен работать с большими ценами"""
        config = Config()
        config.MIN_PRICE = 100
        config.MAX_PRICE = 1000
        config.LOW_PRICE_THRESHOLD = 0

        decision = calculate_price(
            competitor_prices=[150],
            current_price=120,
            last_update=None,
            config=config,
        )

        assert decision.action == 'update'
        assert abs(decision.price - 149.9949) < 0.001  # 150 - 0.0051


class TestWeakPosition:
    """Тесты фильтра слабой позиции конкурента"""

    def test_weak_position_ceil_logic(self):
        """При слабой позиции и цене < WEAK_PRICE_CEIL_LIMIT применяется ceil-логика"""
        config = Config()
        config.WEAK_PRICE_CEIL_LIMIT = 0.3
        config.DESIRED_PRICE = 0.35
        config.UNDERCUT_VALUE = 0.0051

        decision = calculate_price(
            competitor_prices=[0.26],
            current_price=0.35,
            last_update=None,
            config=config,
            target_competitor_rank=35,
            force_weak_mode=True,
        )

        assert decision.action == 'update'
        assert abs(decision.price - 0.2949) < 0.0001
        assert 'weak_position_ceil' in decision.reason

    def test_weak_position_desired_logic(self):
        """При слабой позиции и цене >= WEAK_PRICE_CEIL_LIMIT ставим DESIRED_PRICE"""
        config = Config()
        config.WEAK_PRICE_CEIL_LIMIT = 0.3
        config.DESIRED_PRICE = 0.35

        decision = calculate_price(
            competitor_prices=[0.30],
            current_price=0.32,
            last_update=None,
            config=config,
            target_competitor_rank=40,
            force_weak_mode=True,
        )

        assert decision.action == 'update'
        assert decision.price == 0.35
        assert 'weak_position_desired' in decision.reason
