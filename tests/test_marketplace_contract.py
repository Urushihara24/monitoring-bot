from src.api_client import GGSELClient
from src.digiseller_client import DigiSellerClient
from src.marketplace import FakeMarketplaceClient, MarketplaceClient


def test_fake_marketplace_implements_core_contract_and_updates_in_memory():
    client = FakeMarketplaceClient(product_id=7, price=0.36)

    assert isinstance(client, MarketplaceClient)
    assert client.check_api_access() is True
    assert client.get_my_price(7) == 0.36
    assert client.update_price(7, 0.3499) is True
    assert client.get_my_price(7) == 0.3499
    assert client.update_price(99, 1.0) is False


def test_real_marketplace_clients_match_core_protocol_structurally():
    ggsel = GGSELClient(
        api_key='',
        seller_id=0,
        base_url='https://example.invalid/api',
    )
    digiseller = DigiSellerClient(
        api_key='',
        seller_id=0,
        base_url='https://example.invalid/api',
    )

    assert isinstance(ggsel, MarketplaceClient)
    assert isinstance(digiseller, MarketplaceClient)
