from src.rsc_parser import ParseResult, RSCParser, rsc_parser


def test_rsc_parser_singleton_exists():
    assert isinstance(rsc_parser, RSCParser)


def test_parse_html_reads_unit_price_per_vbucks():
    parser = RSCParser(max_retries=0)
    html = """
    <html><body>
      <input name="unitsToPay" value="70" />
      <input name="unitsToGet" value="200" />
    </body></html>
    """
    result = parser._parse_html(html, 'https://example.com/product')
    assert result.success is True
    assert result.price == 0.35


def test_parse_url_returns_stealth_result(monkeypatch):
    parser = RSCParser(max_retries=0)
    expected = ParseResult(
        success=True,
        price=0.2649,
        method='stealth_requests',
    )
    monkeypatch.setattr(parser, '_parse_with_stealth', lambda *_a, **_kw: expected)
    result = parser.parse_url('https://example.com/item', timeout=3)
    assert result.success is True
    assert result.price == 0.2649
    assert result.method == 'stealth_requests'


def test_parse_url_uses_goods_api_only_for_ggsel_domains(monkeypatch):
    parser = RSCParser(max_retries=0)

    monkeypatch.setattr(
        parser,
        '_parse_with_stealth',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='HTTP 403',
            method='stealth_requests',
            status_code=403,
            block_reason='http_403',
        ),
    )
    called = {'goods': False}

    def fake_goods_api(*_a, **_kw):
        called['goods'] = True
        return ParseResult(success=True, price=0.3311, method='api4_goods')

    monkeypatch.setattr(parser, '_parse_with_goods_api', fake_goods_api)

    parser.parse_url('https://example.com/item', timeout=3)
    assert called['goods'] is False

    parser.parse_url('https://ggsel.net/catalog/product/item-1', timeout=3)
    assert called['goods'] is True
