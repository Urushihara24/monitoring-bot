"""Тесты для src/api_client.py"""

from __future__ import annotations

from typing import Any, Optional

import requests

from src.api_client import GGSELClient


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data: Optional[dict] = None, json_exc: Optional[Exception] = None, ok: Optional[bool] = None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self._json_exc = json_exc
        self.ok = (status_code < 400) if ok is None else ok

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._json_data


def make_client() -> GGSELClient:
    return GGSELClient(
        api_key='token-123',
        seller_id=8175,
        base_url='https://seller.ggsel.com/api_sellers/api',
        lang='ru-RU',
        access_token='token-123',
    )


def test_base_url_is_normalized_without_trailing_slash():
    client = GGSELClient(
        api_key='token-123',
        seller_id=8175,
        base_url='https://seller.ggsel.com/api_sellers/api/',
        lang='ru-RU',
        access_token='token-123',
    )
    assert client.base_url == 'https://seller.ggsel.com/api_sellers/api'


def test_get_product_info_success(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(200, {'retval': 0, 'product': {'price': 1.23, 'name': 'X'}}),
    )
    info = client.get_product_info(123)
    assert info == {'price': 1.23, 'name': 'X'}


def test_get_product_info_accepts_retval_camel_case(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(
            200,
            {'retVal': 0, 'product': {'price': 2.34, 'name': 'Y'}},
        ),
    )
    info = client.get_product_info(123)
    assert info == {'price': 2.34, 'name': 'Y'}


def test_get_product_info_invalid_json_returns_none(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(200, json_exc=ValueError('bad json')),
    )
    assert client.get_product_info(123) is None


def test_get_product_info_bad_retval_returns_none(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'retval': 1}))
    assert client.get_product_info(123) is None


def test_get_product_success(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        'get_product_info',
        lambda product_id, timeout=10: {
            'name': 'Item',
            'price': 0.44,
            'currency': 'RUB',
            'num_in_stock': 5,
            'is_available': 1,
        },
    )
    p = client.get_product(999)
    assert p is not None
    assert p.id == 999
    assert p.price == 0.44


def test_get_product_not_found_returns_none(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, 'get_product_info', lambda product_id, timeout=10: None)
    assert client.get_product(999) is None


def test_get_my_price_success(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, 'get_product_info', lambda product_id, timeout=10: {'price': '0.9876'})
    assert client.get_my_price(111) == 0.9876


def test_get_my_price_when_no_info_returns_none(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, 'get_product_info', lambda product_id, timeout=10: None)
    assert client.get_my_price(111) is None


def test_get_public_price_from_unit_amount(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(
            200,
            {
                'data': {
                    'prices_unit': {'unit_amount': '0.2549'},
                    'price': 0.25,
                }
            },
        ),
    )
    assert client.get_public_price(111) == 0.2549


def test_get_public_price_falls_back_to_price(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(
            200,
            {
                'data': {
                    'prices_unit': {},
                    'price': 0.2711,
                }
            },
        ),
    )
    assert client.get_public_price(111) == 0.2711


def test_get_display_price_prefers_public(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, 'get_public_price', lambda product_id, timeout=10: 0.2549)
    monkeypatch.setattr(client, 'get_my_price', lambda product_id, timeout=10: 0.25)
    assert client.get_display_price(111) == 0.2549


def test_get_update_task_status_success(monkeypatch):
    client = make_client()
    captured: dict[str, Any] = {}

    def fake_request(method, url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return FakeResponse(200, {'Status': 2, 'SuccessCount': 1})

    monkeypatch.setattr(client, '_request_with_retry', fake_request)
    result = client.get_update_task_status('task-1')

    assert result['Status'] == 2
    assert captured['url'].endswith('/product/edit/UpdateProductsTaskStatus')
    assert captured['params']['taskId'] == 'task-1'
    assert captured['params']['token'] == 'token-123'


def test_get_update_task_status_invalid_json(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, json_exc=ValueError('bad')))
    assert client.get_update_task_status('task-1') is None


def test_update_price_request_failure_returns_false(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: None)
    assert client.update_price(1, 0.3) is False


def test_update_price_404_returns_false(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(404, {}))
    assert client.update_price(1, 0.3) is False


def test_update_price_async_status_2_success(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'taskId': 'abc'}))
    monkeypatch.setattr(
        client,
        'get_update_task_status',
        lambda task_id, timeout=10: {'Status': 2, 'SuccessCount': 1, 'ErrorCount': 0, 'TotalCount': 1},
    )
    assert client.update_price(1, 0.3) is True


def test_update_price_async_status_2_with_errors(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'taskId': 'abc'}))
    monkeypatch.setattr(
        client,
        'get_update_task_status',
        lambda task_id, timeout=10: {'Status': 2, 'SuccessCount': 0, 'ErrorCount': 1, 'TotalCount': 1},
    )
    assert client.update_price(1, 0.3) is False


def test_update_price_async_status_3_returns_false(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'taskId': 'abc'}))
    monkeypatch.setattr(client, 'get_update_task_status', lambda task_id, timeout=10: {'Status': 3})
    assert client.update_price(1, 0.3) is False


def test_update_price_async_timeout(monkeypatch):
    client = make_client()
    client.task_poll_timeout = 0.01
    client.task_poll_interval = 0
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'taskId': 'abc'}))
    monkeypatch.setattr(client, 'get_update_task_status', lambda task_id, timeout=10: {'Status': 1})
    assert client.update_price(1, 0.3) is False


def test_update_price_sync_fallback_success(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'retval': 0}, ok=True))
    assert client.update_price(1, 0.3) is True


def test_update_price_sync_fallback_success_with_retval_camel(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(200, {'retVal': 0}, ok=True),
    )
    assert client.update_price(1, 0.3) is True


def test_update_price_sync_fallback_fail(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(200, {'retval': 1}, ok=True))
    assert client.update_price(1, 0.3) is False


def test_check_api_access_none_false(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: None)
    assert client.check_api_access() is False


def test_check_api_access_404_false(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(404, {}))
    assert client.check_api_access() is False


def test_check_api_access_401_false(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, '_request_with_retry', lambda *a, **k: FakeResponse(401, {}))
    assert client.check_api_access() is False


def test_check_api_access_ok_true(monkeypatch):
    client = make_client()
    captured: dict[str, Any] = {}

    def fake_request(method, url, **kwargs):
        captured['method'] = method
        captured['url'] = url
        captured.update(kwargs)
        return FakeResponse(200, {'retval': 0})

    monkeypatch.setattr(client, '_request_with_retry', fake_request)
    assert client.check_api_access() is True
    assert captured['method'] == 'GET'
    assert captured['url'].endswith('/products/list')
    assert captured['params']['token'] == 'token-123'
    assert captured['headers']['lang'] == 'ru-RU'


def test_request_with_retry_retries_5xx_and_then_success(monkeypatch):
    client = make_client()
    calls = {'n': 0}

    def fake_request(method, url, timeout=10, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return FakeResponse(500, {})
        return FakeResponse(200, {'ok': True})

    monkeypatch.setattr(client.session, 'request', fake_request)
    monkeypatch.setattr('src.api_client.time.sleep', lambda *_: None)

    response = client._request_with_retry('GET', 'https://x.test', max_retries=3)
    assert response is not None
    assert response.status_code == 200
    assert calls['n'] == 2


def test_request_with_retry_404_no_retries(monkeypatch):
    client = make_client()
    calls = {'n': 0}

    def fake_request(method, url, timeout=10, **kwargs):
        calls['n'] += 1
        return FakeResponse(404, {})

    monkeypatch.setattr(client.session, 'request', fake_request)

    response = client._request_with_retry('GET', 'https://x.test', max_retries=3)
    assert response is not None
    assert response.status_code == 404
    assert calls['n'] == 1


def test_request_with_retry_timeout_exhausted(monkeypatch):
    client = make_client()
    calls = {'n': 0}

    def fake_request(method, url, timeout=10, **kwargs):
        calls['n'] += 1
        raise requests.Timeout('timeout')

    monkeypatch.setattr(client.session, 'request', fake_request)
    monkeypatch.setattr('src.api_client.time.sleep', lambda *_: None)

    response = client._request_with_retry('GET', 'https://x.test', max_retries=3)
    assert response is None
    assert calls['n'] == 3


def test_refresh_access_token_via_apilogin(monkeypatch):
    client = GGSELClient(
        api_key='secret-abc',
        seller_id=8175,
        base_url='https://seller.ggsel.com/api_sellers/api',
        lang='ru-RU',
    )
    captured: dict[str, Any] = {}

    def fake_request(method, url, **kwargs):
        captured['method'] = method
        captured['url'] = url
        captured.update(kwargs)
        return FakeResponse(
            200,
            {
                'retval': 0,
                'token': 'issued-token-1',
                'valid_thru': '2030-01-01T00:00:00Z',
            },
        )

    monkeypatch.setattr(client, '_request_with_retry', fake_request)

    ok = client._refresh_access_token()
    assert ok is True
    assert client.access_token == 'issued-token-1'
    assert captured['method'] == 'POST'
    assert captured['url'].endswith('/apilogin')
    assert captured['json']['seller_id'] == 8175
    assert 'timestamp' in captured['json']
    assert len(captured['json']['sign']) == 64


def test_refresh_access_token_accepts_retval_camel(monkeypatch):
    client = GGSELClient(
        api_key='secret-abc',
        seller_id=8175,
        base_url='https://seller.ggsel.com/api_sellers/api',
        lang='ru-RU',
    )

    monkeypatch.setattr(
        client,
        '_request_with_retry',
        lambda *a, **k: FakeResponse(
            200,
            {
                'retVal': 0,
                'token': 'issued-token-2',
                'valid_thru': '2030-01-01T00:00:00Z',
            },
        ),
    )

    ok = client._refresh_access_token()
    assert ok is True
    assert client.access_token == 'issued-token-2'


def test_authorized_request_retries_once_after_401(monkeypatch):
    client = GGSELClient(
        api_key='secret-abc',
        seller_id=8175,
        base_url='https://seller.ggsel.com/api_sellers/api',
        lang='ru-RU',
    )
    monkeypatch.setattr(
        client,
        '_get_access_token',
        lambda force_refresh=False, timeout=10: 'token-2' if force_refresh else 'token-1',
    )

    calls = {'n': 0}

    def fake_request(method, url, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return FakeResponse(401, {'retval': -1})
        return FakeResponse(200, {'retval': 0})

    monkeypatch.setattr(client, '_request_with_retry', fake_request)

    resp = client._authorized_request(
        'GET',
        'https://seller.ggsel.com/api_sellers/api/products/list',
        params={'page': 1, 'count': 1},
    )
    assert resp is not None
    assert resp.status_code == 200
    assert calls['n'] == 2
