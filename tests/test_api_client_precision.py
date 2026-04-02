from src.api_client import GGSELClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def make_client():
    return GGSELClient(
        api_key='secret',
        seller_id=1,
        base_url='https://seller.ggsel.com/api_sellers/api',
        access_token='token',
    )


def test_format_price_4dp_keeps_fixed_precision():
    client = make_client()
    assert client._format_price_4dp(0.26) == '0.2600'
    assert client._format_price_4dp(0.2649) == '0.2649'


def test_update_price_sends_string_with_4dp(monkeypatch):
    client = make_client()
    captured = {}

    def fake_authorized_request(*_args, **kwargs):
        captured['json'] = kwargs.get('json')
        return FakeResponse({'retval': 0}, status_code=200)

    monkeypatch.setattr(client, '_authorized_request', fake_authorized_request)

    ok = client.update_price(product_id=123, new_price=0.2649)

    assert ok is True
    assert captured['json'][0]['product_id'] == 123
    assert captured['json'][0]['price'] == '0.2649'
