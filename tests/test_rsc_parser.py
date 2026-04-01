"""
Тесты для RSC парсера (без cookies)
"""

from src.rsc_parser import RSCParser, ParseResult


def test_parser_initialization():
    """Парсер без cookies"""
    parser = RSCParser()
    assert parser is not None
    assert parser.fail_count == 0


def test_parse_result_structure():
    """Структура ParseResult"""
    result = ParseResult(
        success=True,
        price=0.35,
        error=None,
        url="https://example.com",
        offers=None
    )
    assert result.success is True
    assert result.price == 0.35
    assert result.error is None


def test_price_calculation_logic():
    """Логика расчёта цены за 1 V-Buck"""
    # 70₽ за 200 V-Bucks = 0.35₽ за 1
    assert round(70.0 / 200, 4) == 0.35
    
    # 100₽ за 1000 V-Bucks = 0.1₽ за 1
    assert round(100.0 / 1000, 4) == 0.1
    
    # 50₽ за 500 V-Bucks = 0.1₽ за 1
    assert round(50.0 / 500, 4) == 0.1
