"""Offline regression coverage for minimal storefront HTML fixtures."""

import importlib
from pathlib import Path

import pytest

from src.rsc_parser import RSCParser


FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures' / 'rsc_parser'
PRODUCT_URL = 'https://example.com/product'


@pytest.fixture
def offline_parser(monkeypatch):
    def reject_request(*args, **kwargs):
        pytest.fail('HTML fixture tests must not make HTTP requests')

    module = importlib.import_module('src.rsc_parser')
    monkeypatch.setattr(module.stealth_requests, 'get', reject_request)
    return RSCParser(max_retries=0)


def test_visible_product_price_fixture(offline_parser):
    html = (FIXTURE_DIR / 'visible_product_price.html').read_text(encoding='utf-8')

    result = offline_parser._parse_html(html, PRODUCT_URL)

    assert result.success is True
    assert result.price == pytest.approx(149.90)
    assert result.error is None
    assert result.url == PRODUCT_URL
    assert len(result.offers) == 1
    assert result.offers[0].price == pytest.approx(149.90)


def test_partial_product_price_fixture_fails_safely(offline_parser):
    html = (FIXTURE_DIR / 'partial_product_price.html').read_text(encoding='utf-8')

    result = offline_parser._parse_html(html, PRODUCT_URL)

    assert result.success is False
    assert result.price is None
    assert result.offers == []
    assert result.error == 'Цена не найдена в HTML'
    assert result.url == PRODUCT_URL
