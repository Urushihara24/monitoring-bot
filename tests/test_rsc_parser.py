import importlib
from src.rsc_parser import ParseResult, RSCParser

rsc_module = importlib.import_module('src.rsc_parser')


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


def test_parse_html_extracts_unit_price_from_tier_block():
    parser = RSCParser(max_retries=0)
    html = """
    <html><body>
      <div>
        <h3>Цена за 1 В-Баксов</h3>
        <ul>
          <li>от 100 В-Баксов ... 0.33 ₽</li>
          <li>от 1500 В-Баксов ... 0.31 ₽</li>
        </ul>
      </div>
    </body></html>
    """
    result = parser._parse_html(html, 'https://plati.market/itm/test')
    assert result.success
    # Берём цену для минимального порога (от 100).
    assert result.price == 0.33


def test_parse_with_stealth_ignores_recaptcha_marker_when_price_is_parsed(
    monkeypatch,
):
    parser = RSCParser(max_retries=0)

    class FakeResponse:
        status_code = 200
        text = (
            '<html><body>'
            '<script>var recaptcha = true;</script>'
            '<div><h3>Цена за 1 В-Баксов</h3>'
            '<ul><li>от 100 В-Баксов ... 0.33 ₽</li></ul>'
            '</div>'
            '</body></html>'
        )

    monkeypatch.setattr(
        rsc_module.stealth_requests,
        'get',
        lambda *args, **kwargs: FakeResponse(),
    )

    result = parser._parse_with_stealth(
        'https://plati.market/itm/test',
        timeout=3,
        cookies=None,
    )
    assert result.success
    assert result.price == 0.33
    assert result.block_reason is None


def test_parse_with_stealth_uses_plati_price_options_fallback(monkeypatch):
    parser = RSCParser(max_retries=0)

    class PageResponse:
        status_code = 200
        text = (
            '<html><body>'
            '<script>var recaptcha = true; _unit_cnt_min = 100;</script>'
            '<input type="hidden" name="product_id" value="5655506" />'
            '</body></html>'
        )

        def json(self):  # pragma: no cover
            return {}

    class PriceResponse:
        status_code = 200
        text = '{"price":"0,33","cnt":"100","amount":"33","err":"0"}'

        def json(self):
            return {
                'price': '0,33',
                'cnt': '100',
                'amount': '33',
                'err': '0',
            }

    def fake_get(url, **_kwargs):
        if 'price_options.asp' in url:
            return PriceResponse()
        return PageResponse()

    monkeypatch.setattr(rsc_module.stealth_requests, 'get', fake_get)

    result = parser._parse_with_stealth(
        'https://plati.market/itm/name/5655506',
        timeout=3,
        cookies=None,
    )

    assert result.success
    assert result.method == 'plati_price_options'
    assert result.price == 0.33


def test_parse_with_stealth_uses_plati_fallback_on_http_403(monkeypatch):
    parser = RSCParser(max_retries=0)

    class Page403:
        status_code = 403
        text = '<html><body>DDoS-Guard</body></html>'

        def json(self):  # pragma: no cover
            return {}

    class PriceResponse:
        status_code = 200
        text = '{"price":"0,33","cnt":"1","amount":"0.33","err":"1"}'

        def json(self):
            return {
                'price': '0,33',
                'cnt': '1',
                'amount': '0.33',
                'err': '1',
            }

    def fake_get(url, **_kwargs):
        if 'price_options.asp' in url:
            return PriceResponse()
        return Page403()

    monkeypatch.setattr(rsc_module.stealth_requests, 'get', fake_get)

    result = parser._parse_with_stealth(
        'https://plati.market/itm/name/5655506',
        timeout=3,
        cookies=None,
    )

    assert result.success
    assert result.method == 'plati_price_options'
    assert result.price == 0.33


def test_parse_with_stealth_retries_plati_after_http_403(monkeypatch):
    parser = RSCParser(max_retries=1)
    calls = {'page': 0, 'price': 0}

    class Page403:
        status_code = 403
        text = '<html><body>DDoS-Guard</body></html>'

        def json(self):  # pragma: no cover
            return {}

    class Page200:
        status_code = 200
        text = '<html><body><span data-testid="product-price">0.33 ₽</span></body></html>'

        def json(self):  # pragma: no cover
            return {}

    class PriceFail:
        status_code = 403
        text = ''

        def json(self):  # pragma: no cover
            return {}

    def fake_get(url, **_kwargs):
        if 'price_options.asp' in url:
            calls['price'] += 1
            return PriceFail()
        calls['page'] += 1
        if calls['page'] == 1:
            return Page403()
        return Page200()

    monkeypatch.setattr(rsc_module.stealth_requests, 'get', fake_get)
    monkeypatch.setattr(rsc_module.time, 'sleep', lambda _s: None)

    result = parser._parse_with_stealth(
        'https://plati.market/itm/name/5655506',
        timeout=3,
        cookies=None,
    )

    assert result.success
    assert result.price == 0.33
    assert calls['page'] == 2
    assert calls['price'] >= 1


def test_parse_with_plati_price_api_retries_transient_http(monkeypatch):
    parser = RSCParser(max_retries=2)
    calls = {'price': 0}

    class Price403:
        status_code = 403
        text = ''

        def json(self):  # pragma: no cover
            return {}

    class Price200:
        status_code = 200
        text = '{"price":"0,33","cnt":"100","amount":"33","err":"0"}'

        def json(self):
            return {
                'price': '0,33',
                'cnt': '100',
                'amount': '33',
                'err': '0',
            }

    def fake_get(url, **_kwargs):
        if 'price_options.asp' not in url:
            raise AssertionError('unexpected URL')  # pragma: no cover
        calls['price'] += 1
        if calls['price'] < 3:
            return Price403()
        return Price200()

    monkeypatch.setattr(rsc_module.stealth_requests, 'get', fake_get)
    monkeypatch.setattr(rsc_module.time, 'sleep', lambda _s: None)

    result = parser._parse_with_plati_price_api(
        url='https://plati.market/itm/name/5655506',
        html='<input type="hidden" name="product_id" value="5655506" />',
        timeout=3,
    )

    assert result.success
    assert result.method == 'plati_price_options'
    assert result.price == 0.33
    assert calls['price'] >= 3


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


def test_parse_url_uses_direct_plati_before_stealth(monkeypatch):
    parser = RSCParser(max_retries=0)
    calls = {'direct': 0, 'stealth': 0}

    def fake_direct(url, html, timeout):
        calls['direct'] += 1
        assert html == ''
        return ParseResult(
            success=True,
            price=0.33,
            url=url,
            method='plati_price_options',
        )

    def fake_stealth(*_args, **_kwargs):
        calls['stealth'] += 1
        return ParseResult(
            success=False,
            error='should_not_be_called',
            method='stealth_requests',
        )

    monkeypatch.setattr(parser, '_parse_with_plati_price_api', fake_direct)
    monkeypatch.setattr(parser, '_parse_with_stealth', fake_stealth)

    result = parser.parse_url('https://plati.market/itm/name/5655506', timeout=3)

    assert result.success
    assert result.method == 'plati_price_options'
    assert calls['direct'] == 1
    assert calls['stealth'] == 0


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


def test_parse_url_prioritizes_api4_for_ggsel_domain(monkeypatch):
    parser = RSCParser(max_retries=0)
    calls = {'stealth': 0}

    monkeypatch.setattr(
        parser,
        '_parse_with_goods_api',
        lambda *_a, **_kw: ParseResult(
            success=True,
            price=0.3333,
            method='api4_goods',
        ),
    )

    def fake_stealth(*_a, **_kw):
        calls['stealth'] += 1
        return ParseResult(
            success=False,
            error='should_not_call_stealth',
            method='stealth_requests',
        )

    monkeypatch.setattr(parser, '_parse_with_stealth', fake_stealth)

    result = parser.parse_url(
        'https://ggsel.net/catalog/product/item-123',
        timeout=3,
    )

    assert result.success
    assert result.method == 'api4_goods'
    assert calls['stealth'] == 0


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
