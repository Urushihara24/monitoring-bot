import importlib

rsc_module = importlib.import_module('src.rsc_parser')
from src.rsc_parser import ParseResult, RSCParser


def test_parse_html_extracts_unit_price():
    parser = RSCParser(max_retries=0)
    html = """
    <html><body>
      <input name="unitsToPay" value="70" />
      <input name="unitsToGet" value="200" />
    </body></html>
    """
    result = parser._parse_html(html, 'https://example.com')
    assert result.success
    assert result.price == 0.35


def test_parse_html_fallback_selector():
    parser = RSCParser(max_retries=0)
    html = """
    <html><body>
      <span data-testid="product-price">70 ₽</span>
    </body></html>
    """
    result = parser._parse_html(html, 'https://example.com')
    assert result.success
    assert result.price == 70.0


def test_parse_html_extracts_price_from_json_ld_offers():
    parser = RSCParser(max_retries=0)
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "offers": {
          "@type": "Offer",
          "price": "0.3349",
          "priceCurrency": "RUB"
        }
      }
      </script>
    </head><body></body></html>
    """
    result = parser._parse_html(html, 'https://example.com')
    assert result.success
    assert result.price == 0.3349


def test_parse_html_extracts_price_from_meta_amount():
    parser = RSCParser(max_retries=0)
    html = """
    <html><head>
      <meta property="product:price:amount" content="0.2711" />
    </head><body></body></html>
    """
    result = parser._parse_html(html, 'https://example.com')
    assert result.success
    assert result.price == 0.2711


def test_parse_url_success_uses_stealth(monkeypatch):
    parser = RSCParser(max_retries=0)
    monkeypatch.setattr(
        parser,
        '_parse_with_stealth',
        lambda *_a, **_kw: ParseResult(
            success=True,
            price=0.3349,
            method='stealth_requests',
        ),
    )
    result = parser.parse_url('https://example.com', timeout=3)
    assert result.success
    assert result.method == 'stealth_requests'


def test_parse_url_uses_api_fallback(monkeypatch):
    parser = RSCParser(max_retries=0)
    monkeypatch.setattr(
        parser,
        '_parse_with_stealth',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='HTTP 401',
            method='stealth_requests',
            cookies_expired=True,
            block_reason='http_401',
            status_code=401,
        ),
    )
    monkeypatch.setattr(
        parser,
        '_parse_with_goods_api',
        lambda *_a, **_kw: ParseResult(
            success=True,
            price=0.3311,
            method='api4_goods',
        ),
    )
    result = parser.parse_url(
        'https://ggsel.net/catalog/product/item-123',
        timeout=3,
    )
    assert result.success
    assert result.price == 0.3311
    assert result.method == 'api4_goods'


def test_parse_url_failed_preserves_reason(monkeypatch):
    parser = RSCParser(max_retries=0)
    monkeypatch.setattr(
        parser,
        '_parse_with_stealth',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='HTTP 403',
            method='stealth_requests',
            cookies_expired=True,
            block_reason='http_403',
            status_code=403,
        ),
    )
    monkeypatch.setattr(
        parser,
        '_parse_with_goods_api',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='API fallback HTTP 503',
            method='api4_goods',
            status_code=503,
        ),
    )
    result = parser.parse_url(
        'https://ggsel.net/catalog/product/item-123',
        timeout=3,
    )
    assert not result.success
    assert result.cookies_expired
    assert result.block_reason == 'http_403'
    assert result.status_code == 403
    assert 'HTTP 403' in (result.error or '')


def test_parse_url_skips_goods_api_for_non_ggsel_domain(monkeypatch):
    parser = RSCParser(max_retries=0)
    monkeypatch.setattr(
        parser,
        '_parse_with_stealth',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='HTTP 403',
            method='stealth_requests',
            cookies_expired=True,
            block_reason='http_403',
            status_code=403,
        ),
    )
    fallback_called = {'value': False}

    def fake_goods_api(*_a, **_kw):
        fallback_called['value'] = True
        return ParseResult(success=True, price=0.25, method='api4_goods')

    monkeypatch.setattr(parser, '_parse_with_goods_api', fake_goods_api)

    result = parser.parse_url('https://example.com/product/123', timeout=3)

    assert not result.success
    assert fallback_called['value'] is False


def test_parse_with_stealth_retries_on_429_then_succeeds(monkeypatch):
    parser = RSCParser(max_retries=1)

    class FakeResponse:
        def __init__(self, status_code, text=''):
            self.status_code = status_code
            self.text = text

    responses = iter(
        [
            FakeResponse(429, ''),
            FakeResponse(200, '<span data-testid="product-price">70 ₽</span>'),
        ]
    )
    sleep_calls = []

    monkeypatch.setattr(
        rsc_module.stealth_requests,
        'get',
        lambda *_a, **_kw: next(responses),
    )
    monkeypatch.setattr(rsc_module.time, 'sleep', lambda value: sleep_calls.append(value))

    result = parser._parse_with_stealth(
        'https://example.com/item',
        timeout=3,
        cookies='a=1',
    )

    assert result.success is True
    assert result.price == 70.0
    assert result.status_code == 200
    assert result.method == 'stealth_requests'
    assert sleep_calls == [1]


def test_parse_with_stealth_429_exhausted_returns_block(monkeypatch):
    parser = RSCParser(max_retries=1)

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = ''

    monkeypatch.setattr(
        rsc_module.stealth_requests,
        'get',
        lambda *_a, **_kw: FakeResponse(429),
    )
    monkeypatch.setattr(rsc_module.time, 'sleep', lambda *_a, **_kw: None)

    result = parser._parse_with_stealth(
        'https://example.com/item',
        timeout=3,
        cookies='a=1',
    )

    assert result.success is False
    assert result.status_code == 429
    assert result.block_reason == 'http_429'
    assert result.cookies_expired is False


def test_parse_with_goods_api_prefers_unit_amount(monkeypatch):
    parser = RSCParser(max_retries=0)

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    payload = {
        'success': True,
        'data': {
            'price': 70,
            'prices_unit': {
                'unit_amount': '0.3500',
            },
        },
    }
    monkeypatch.setattr(
        rsc_module.stealth_requests,
        'get',
        lambda *_a, **_kw: FakeResponse(200, payload),
    )

    result = parser._parse_with_goods_api(
        'https://ggsel.net/catalog/product/item-123',
        timeout=3,
    )

    assert result.success is True
    assert result.price == 0.35
    assert result.method == 'api4_goods'


def test_parse_with_goods_api_falls_back_to_price(monkeypatch):
    parser = RSCParser(max_retries=0)

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    payload = {
        'success': True,
        'data': {
            'price': 0.2649,
            'prices_unit': {},
        },
    }
    monkeypatch.setattr(
        rsc_module.stealth_requests,
        'get',
        lambda *_a, **_kw: FakeResponse(200, payload),
    )

    result = parser._parse_with_goods_api(
        'https://ggsel.net/catalog/product/item-123',
        timeout=3,
    )

    assert result.success is True
    assert result.price == 0.2649
