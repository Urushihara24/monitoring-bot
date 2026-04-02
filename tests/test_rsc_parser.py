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


def test_parse_url_uses_playwright_fallback(monkeypatch):
    parser = RSCParser(max_retries=0)
    monkeypatch.setattr(
        parser,
        '_parse_with_stealth',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='blocked',
            method='stealth_requests',
            cookies_expired=True,
        ),
    )
    monkeypatch.setattr(
        parser,
        '_parse_with_playwright',
        lambda *_a, **_kw: ParseResult(
            success=True,
            price=0.3349,
            method='playwright',
        ),
    )
    result = parser.parse_url(
        'https://example.com',
        timeout=3,
        use_playwright=True,
        use_selenium_fallback=False,
    )
    assert result.success
    assert result.method == 'playwright'


def test_parse_url_all_failed_collects_reason(monkeypatch):
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
        '_parse_with_playwright',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='captcha',
            method='playwright',
            cookies_expired=True,
            block_reason='captcha',
        ),
    )
    monkeypatch.setattr(
        parser,
        '_parse_with_selenium',
        lambda *_a, **_kw: ParseResult(
            success=False,
            error='timeout',
            method='selenium',
        ),
    )

    result = parser.parse_url(
        'https://example.com',
        timeout=3,
        use_playwright=True,
        use_selenium_fallback=True,
    )
    assert not result.success
    assert result.cookies_expired
    assert result.block_reason in {'http_403', 'captcha'}
    assert 'stealth_requests' in (result.error or '')
