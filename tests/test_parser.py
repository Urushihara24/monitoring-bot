from src.parser import CompetitorParser


def test_extract_price_per_vbucks_from_product_block():
    html = '''
    <div>
      <h1>Fortnite 200 V-Bucks</h1>
      <span data-testid="product-price">70 ₽</span>
    </div>
    '''
    parser = CompetitorParser()
    price = parser._extract_price(html, 'https://ggsel.net/catalog/product/x')
    assert price == 0.35


def test_extract_price_without_vbucks_keeps_total():
    html = '<span data-testid="product-price">70 ₽</span>'
    parser = CompetitorParser()
    price = parser._extract_price(html, 'https://ggsel.net/catalog/product/x')
    assert price == 70.0
