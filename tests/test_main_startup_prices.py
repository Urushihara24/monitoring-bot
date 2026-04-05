from types import SimpleNamespace

from src.main import _resolve_startup_prices


def test_resolve_startup_prices_ggsel_uses_display_when_available():
    class Client:
        def get_display_price(self, _product_id):
            return 0.3349

    product = SimpleNamespace(price=0.34, currency='RUB')
    log_price, log_currency, seed_price = _resolve_startup_prices(
        profile_id='ggsel',
        client=Client(),
        product_id=4697439,
        product=product,
    )

    assert log_price == 0.3349
    assert log_currency == 'RUB'
    assert seed_price == 0.3349


def test_resolve_startup_prices_digiseller_does_not_seed_non_public_price():
    class Client:
        def get_display_price(self, _product_id):
            return None

    product = SimpleNamespace(price=0.82, currency='USD')
    log_price, log_currency, seed_price = _resolve_startup_prices(
        profile_id='digiseller',
        client=Client(),
        product_id=5077639,
        product=product,
    )

    assert log_price == 0.82
    assert log_currency == 'USD'
    assert seed_price is None


def test_resolve_startup_prices_ggsel_seeds_fallback_price():
    class Client:
        def get_display_price(self, _product_id):
            return None

    product = SimpleNamespace(price=0.34, currency='RUB')
    log_price, log_currency, seed_price = _resolve_startup_prices(
        profile_id='ggsel',
        client=Client(),
        product_id=4697439,
        product=product,
    )

    assert log_price == 0.34
    assert log_currency == 'RUB'
    assert seed_price == 0.34
