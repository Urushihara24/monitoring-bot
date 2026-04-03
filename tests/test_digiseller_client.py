from src.digiseller_client import DigiSellerClient


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


def test_get_product_info_accepts_retval_camel_case(monkeypatch):
    client = make_client()
    payload = {'retVal': 0, 'product': {'name': 'Camel', 'price': 1.5}}
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse(payload),
    )
    info = client.get_product_info(123)
    assert info is not None
    assert info['name'] == 'Camel'


def test_get_product_info_from_content_product_list(monkeypatch):
    client = make_client()
    payload = {
        'retval': 0,
        'content': {
            'product': [
                {'name': 'ListItem', 'prices': [{'price': 2.7, 'currency': 'USD'}]}
            ]
        },
    }
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse(payload),
    )
    product = client.get_product(999)
    assert product is not None
    assert product.name == 'ListItem'
    assert product.price == 2.7
    assert product.currency == 'USD'


def test_get_product_price_from_prices_list(monkeypatch):
    client = make_client()
    payload = {
        'retval': 0,
        'product': {
            'name': 'ListPrices',
            'prices': [
                {'price': 3.14, 'currency': 'EUR'},
            ],
        },
    }
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse(payload),
    )
    product = client.get_product(101)
    assert product is not None
    assert product.price == 3.14
    assert product.currency == 'EUR'


def test_get_product_price_from_comma_string(monkeypatch):
    client = make_client()
    payload = {
        'retval': 0,
        'product': {
            'name': 'CommaPrice',
            'price': '0,2649',
            'currency': 'RUB',
        },
    }
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse(payload),
    )
    product = client.get_product(102)
    assert product is not None
    assert product.price == 0.2649


def test_check_api_access_false_on_unauthorized(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse({}, status_code=401),
    )
    assert client.check_api_access() is False


def test_check_api_access_fallback_to_product_read(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_a, **_kw: FakeResponse({}, status_code=404),
    )
    monkeypatch.setattr(
        client,
        'get_product',
        lambda *_a, **_kw: object(),
    )
    assert client.check_api_access() is True


def test_check_api_access_false_without_perms_and_product(monkeypatch):
    client = make_client()
    client.default_product_id = 0
    monkeypatch.setattr(client, '_authorized_request', lambda *_a, **_kw: None)
    assert client.check_api_access() is False


def test_update_price_payload_uses_float(monkeypatch):
    client = make_client()
    captured = {}

    def fake_authorized_request(*_args, **kwargs):
        captured['json'] = kwargs.get('json')
        return FakeResponse({'retval': 0}, status_code=200)

    monkeypatch.setattr(client, '_authorized_request', fake_authorized_request)

    ok = client.update_price(product_id=123, new_price=0.2649)

    assert ok is True
    assert captured['json'][0]['product_id'] == 123
    assert captured['json'][0]['price'] == 0.2649


def test_update_price_async_status_3_done(monkeypatch):
    client = make_client()
    client.task_poll_interval = 0.0
    client.task_poll_timeout = 0.2

    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_args, **_kwargs: FakeResponse({'taskId': 'task-1'}),
    )

    statuses = iter([
        {
            'Status': 1,
            'SuccessCount': 0,
            'ErrorCount': 0,
            'TotalCount': 1,
        },
        {
            'Status': 3,
            'SuccessCount': 1,
            'ErrorCount': 0,
            'TotalCount': 1,
        },
    ])
    monkeypatch.setattr(client, 'get_update_task_status', lambda *_a, **_k: next(statuses))

    assert client.update_price(product_id=123, new_price=0.2649) is True


def test_update_price_async_status_2_error(monkeypatch):
    client = make_client()
    client.task_poll_interval = 0.0
    client.task_poll_timeout = 0.2

    monkeypatch.setattr(
        client,
        '_authorized_request',
        lambda *_args, **_kwargs: FakeResponse({'taskId': 'task-1'}),
    )
    monkeypatch.setattr(
        client,
        'get_update_task_status',
        lambda *_a, **_k: {
            'Status': 2,
            'SuccessCount': 0,
            'ErrorCount': 1,
            'TotalCount': 1,
        },
    )

    assert client.update_price(product_id=123, new_price=0.2649) is False
