from src.digiseller_client import DigiSellerClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def make_client():
    return DigiSellerClient(
        api_key='secret',
        seller_id=1,
        base_url='https://api.digiseller.com/api',
        access_token='token',
        default_product_id=123,
    )


def test_get_product_info_from_product_field(monkeypatch):
    client = make_client()
    payload = {'retval': 0, 'product': {'name': 'A', 'price': 1.23}}
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse(payload),
    )
    info = client.get_product_info(123)
    assert info['name'] == 'A'
    assert info['price'] == 1.23


def test_get_product_info_from_content_field(monkeypatch):
    client = make_client()
    payload = {
        'retval': 0,
        'content': {
            'name': 'B',
            'prices': {'default': {'price': 2.5, 'currency': 'RUB'}},
        },
    }
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse(payload),
    )
    product = client.get_product(555)
    assert product is not None
    assert product.name == 'B'
    assert product.price == 2.5
    assert product.currency == 'RUB'


def test_check_api_access_false_on_unauthorized(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse({}, status_code=401),
    )
    assert client.check_api_access() is False
