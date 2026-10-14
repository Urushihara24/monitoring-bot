from src.marketplace import FakeMarketplaceClient


def test_fake_marketplace_product_read_is_isolated_by_product_id():
    client = FakeMarketplaceClient(
        product_id=42,
        price=1.2345,
        name='Fixture product',
        stock=3,
    )

    product = client.get_product(42)

    assert product is not None
    assert product.id == 42
    assert product.name == 'Fixture product'
    assert product.price == 1.2345
    assert product.stock == 3
    assert client.get_product(999) is None
    assert client.get_my_price(999) is None
