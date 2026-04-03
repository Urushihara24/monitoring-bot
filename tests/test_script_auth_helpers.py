from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_check_apilogin_success_with_token(monkeypatch):
    module = _load_module('check_apilogin_test_mod_success', 'scripts/check_apilogin.py')

    monkeypatch.setattr(module.config, 'GGSEL_API_KEY', 'secret-key')
    monkeypatch.setattr(module.config, 'GGSEL_SELLER_ID', 8175)
    monkeypatch.setattr(
        module.config,
        'GGSEL_BASE_URL',
        'https://seller.ggsel.com/api_sellers/api',
    )

    class Response:
        status_code = 200
        headers = {'x-request-id': 'req-1'}
        text = ''

        @staticmethod
        def json():
            return {
                'retVal': 0,
                'token': 'access-token',
                'valid_thru': '2026-05-01T00:00:00Z',
            }

    monkeypatch.setattr(module.requests, 'post', lambda *args, **kwargs: Response())

    assert module.main() == 0


def test_check_apilogin_returns_error_on_non_json(monkeypatch):
    module = _load_module('check_apilogin_test_mod_non_json', 'scripts/check_apilogin.py')

    monkeypatch.setattr(module.config, 'GGSEL_API_KEY', 'secret-key')
    monkeypatch.setattr(module.config, 'GGSEL_SELLER_ID', 8175)
    monkeypatch.setattr(
        module.config,
        'GGSEL_BASE_URL',
        'https://seller.ggsel.com/api_sellers/api',
    )

    class Response:
        status_code = 502
        headers = {'x-request-id': 'req-2'}
        text = '<html>bad gateway</html>'

        @staticmethod
        def json():
            raise ValueError('not json')

    monkeypatch.setattr(module.requests, 'post', lambda *args, **kwargs: Response())

    assert module.main() == 1


def test_check_apilogin_returns_error_on_nonzero_retval(monkeypatch):
    module = _load_module(
        'check_apilogin_test_mod_retval_error',
        'scripts/check_apilogin.py',
    )

    monkeypatch.setattr(module.config, 'GGSEL_API_KEY', 'secret-key')
    monkeypatch.setattr(module.config, 'GGSEL_SELLER_ID', 8175)
    monkeypatch.setattr(
        module.config,
        'GGSEL_BASE_URL',
        'https://seller.ggsel.com/api_sellers/api',
    )

    class Response:
        status_code = 200
        headers = {'x-request-id': 'req-3'}
        text = ''

        @staticmethod
        def json():
            return {
                'retVal': 12,
                'desc': 'invalid sign',
                'token': 'unexpected-token',
            }

    monkeypatch.setattr(module.requests, 'post', lambda *args, **kwargs: Response())

    assert module.main() == 1


def test_issue_access_token_success(monkeypatch):
    module = _load_module('issue_access_token_test_mod_success', 'scripts/issue_access_token.py')

    monkeypatch.setattr(module.config, 'GGSEL_API_KEY', 'secret-key')
    monkeypatch.setattr(module.config, 'GGSEL_SELLER_ID', 8175)
    monkeypatch.setattr(
        module.config,
        'GGSEL_BASE_URL',
        'https://seller.ggsel.com/api_sellers/api',
    )
    monkeypatch.setattr(module.config, 'GGSEL_LANG', 'ru-RU')

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.access_token = 'new-access-token'
            self.token_valid_thru = None

        def _refresh_access_token(self, timeout=20):
            return True

        def check_api_access(self):
            return True

    monkeypatch.setattr(module, 'GGSELClient', FakeClient)

    assert module.main() == 0


def test_issue_access_token_returns_1_when_refresh_fails(monkeypatch):
    module = _load_module(
        'issue_access_token_test_mod_refresh_fail',
        'scripts/issue_access_token.py',
    )

    monkeypatch.setattr(module.config, 'GGSEL_API_KEY', 'secret-key')
    monkeypatch.setattr(module.config, 'GGSEL_SELLER_ID', 8175)
    monkeypatch.setattr(
        module.config,
        'GGSEL_BASE_URL',
        'https://seller.ggsel.com/api_sellers/api',
    )
    monkeypatch.setattr(module.config, 'GGSEL_LANG', 'ru-RU')

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.access_token = ''
            self.token_valid_thru = None

        def _refresh_access_token(self, timeout=20):
            return False

        def check_api_access(self):
            return False

    monkeypatch.setattr(module, 'GGSELClient', FakeClient)

    assert module.main() == 1


def test_issue_access_token_returns_2_when_missing_env(monkeypatch):
    module = _load_module('issue_access_token_test_mod_missing', 'scripts/issue_access_token.py')

    monkeypatch.setattr(module.config, 'GGSEL_API_KEY', '')
    monkeypatch.setattr(module.config, 'GGSEL_SELLER_ID', 0)

    assert module.main() == 2
