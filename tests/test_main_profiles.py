import logging

from src.api_client import GGSELClient
from src.digiseller_client import DigiSellerClient
from src.main import _build_profiles


def _set_profile_config(monkeypatch):
    import src.main as main_module

    monkeypatch.setattr(main_module.config, 'GGSEL_ENABLED', True)
    monkeypatch.setattr(main_module.config, 'GGSEL_API_KEY', 'gg_key')
    monkeypatch.setattr(main_module.config, 'GGSEL_API_SECRET', '')
    monkeypatch.setattr(main_module.config, 'GGSEL_ACCESS_TOKEN', '')
    monkeypatch.setattr(main_module.config, 'GGSEL_SELLER_ID', 100)
    monkeypatch.setattr(main_module.config, 'GGSEL_PRODUCT_ID', 1111)
    monkeypatch.setattr(
        main_module.config,
        'GGSEL_BASE_URL',
        'https://seller.ggsel.com/api_sellers/api',
    )
    monkeypatch.setattr(main_module.config, 'GGSEL_LANG', 'ru-RU')
    monkeypatch.setattr(main_module.config, 'GGSEL_REQUIRE_API_ON_START', False)
    monkeypatch.setattr(main_module.config, 'COMPETITOR_URLS', ['https://gg.example'])
    monkeypatch.setattr(
        main_module.config,
        'GGSEL_COMPETITOR_URLS',
        ['https://gg.example'],
    )

    monkeypatch.setattr(main_module.config, 'DIGISELLER_ENABLED', True)
    monkeypatch.setattr(main_module.config, 'DIGISELLER_API_KEY', 'dg_key')
    monkeypatch.setattr(main_module.config, 'DIGISELLER_API_SECRET', '')
    monkeypatch.setattr(main_module.config, 'DIGISELLER_ACCESS_TOKEN', '')
    monkeypatch.setattr(main_module.config, 'DIGISELLER_SELLER_ID', 200)
    monkeypatch.setattr(main_module.config, 'DIGISELLER_PRODUCT_ID', 2222)
    monkeypatch.setattr(
        main_module.config,
        'DIGISELLER_BASE_URL',
        'https://api.digiseller.com/api',
    )
    monkeypatch.setattr(main_module.config, 'DIGISELLER_LANG', 'ru-RU')
    monkeypatch.setattr(
        main_module.config,
        'DIGISELLER_REQUIRE_API_ON_START',
        False,
    )
    monkeypatch.setattr(
        main_module.config,
        'DIGISELLER_COMPETITOR_URLS',
        ['https://dg.example'],
    )


def test_build_profiles_returns_both_profiles(monkeypatch):
    import src.main as main_module

    _set_profile_config(monkeypatch)

    def fake_get_competitor_urls(default_urls, profile_id='ggsel'):
        if profile_id == 'digiseller':
            return ['https://digiseller.example/item']
        return default_urls

    monkeypatch.setattr(
        main_module.storage,
        'get_competitor_urls',
        fake_get_competitor_urls,
    )
    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': kwargs['default_product_id'],
                'competitor_urls': kwargs.get('default_urls', []),
                'enabled': True,
            }
        ],
    )

    profiles = _build_profiles(logging.getLogger('test-main'))
    assert len(profiles) == 2
    by_id = {profile['id']: profile for profile in profiles}

    assert 'ggsel' in by_id
    assert by_id['ggsel']['name'] == 'GGSEL'
    assert by_id['ggsel']['product_id'] == 1111
    assert by_id['ggsel']['competitor_urls'] == ['https://gg.example']
    assert isinstance(by_id['ggsel']['client'], GGSELClient)

    assert 'digiseller' in by_id
    assert by_id['digiseller']['name'] == 'DIGISELLER'
    assert by_id['digiseller']['product_id'] == 2222
    assert by_id['digiseller']['competitor_urls'] == [
        'https://digiseller.example/item'
    ]
    assert isinstance(by_id['digiseller']['client'], DigiSellerClient)


def test_build_profiles_skips_digiseller_without_credentials(monkeypatch):
    import src.main as main_module

    _set_profile_config(monkeypatch)
    monkeypatch.setattr(main_module.config, 'DIGISELLER_API_KEY', '')
    monkeypatch.setattr(main_module.config, 'DIGISELLER_ACCESS_TOKEN', '')

    monkeypatch.setattr(
        main_module.storage,
        'get_competitor_urls',
        lambda default_urls, profile_id='ggsel': default_urls,
    )
    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': kwargs['default_product_id'],
                'competitor_urls': kwargs.get('default_urls', []),
                'enabled': True,
            }
        ],
    )

    profiles = _build_profiles(logging.getLogger('test-main'))
    ids = [profile['id'] for profile in profiles]
    assert ids == ['ggsel']


def test_build_profiles_skips_digiseller_without_product_id(monkeypatch):
    import src.main as main_module

    _set_profile_config(monkeypatch)
    monkeypatch.setattr(main_module.config, 'DIGISELLER_PRODUCT_ID', 0)

    monkeypatch.setattr(
        main_module.storage,
        'get_competitor_urls',
        lambda default_urls, profile_id='ggsel': default_urls,
    )
    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **kwargs: (
            [
                {
                    'product_id': kwargs['default_product_id'],
                    'competitor_urls': kwargs.get('default_urls', []),
                    'enabled': True,
                }
            ]
            if kwargs.get('default_product_id')
            else []
        ),
    )

    profiles = _build_profiles(logging.getLogger('test-main'))
    ids = [profile['id'] for profile in profiles]
    assert ids == ['ggsel']


def test_build_profiles_skips_ggsel_without_product_id(monkeypatch):
    import src.main as main_module

    _set_profile_config(monkeypatch)
    monkeypatch.setattr(main_module.config, 'GGSEL_PRODUCT_ID', 0)

    monkeypatch.setattr(
        main_module.storage,
        'get_competitor_urls',
        lambda default_urls, profile_id='ggsel': default_urls,
    )
    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **kwargs: (
            [
                {
                    'product_id': kwargs['default_product_id'],
                    'competitor_urls': kwargs.get('default_urls', []),
                    'enabled': True,
                }
            ]
            if kwargs.get('default_product_id')
            else []
        ),
    )

    profiles = _build_profiles(logging.getLogger('test-main'))
    ids = [profile['id'] for profile in profiles]
    assert ids == ['digiseller']


def test_build_profiles_prefers_ggsel_profile_urls(monkeypatch):
    import src.main as main_module

    _set_profile_config(monkeypatch)
    monkeypatch.setattr(
        main_module.config,
        'COMPETITOR_URLS',
        ['https://global.example/item'],
    )
    monkeypatch.setattr(
        main_module.config,
        'GGSEL_COMPETITOR_URLS',
        ['https://ggsel.example/item'],
    )

    monkeypatch.setattr(
        main_module.storage,
        'get_competitor_urls',
        lambda default_urls, profile_id='ggsel': default_urls,
    )
    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **kwargs: [
            {
                'product_id': kwargs['default_product_id'],
                'competitor_urls': kwargs.get('default_urls', []),
                'enabled': True,
            }
        ],
    )

    profiles = _build_profiles(logging.getLogger('test-main'))
    by_id = {profile['id']: profile for profile in profiles}

    assert by_id['ggsel']['competitor_urls'] == ['https://ggsel.example/item']


def test_build_profiles_keeps_profile_when_tracked_products_empty(monkeypatch):
    import src.main as main_module

    _set_profile_config(monkeypatch)
    monkeypatch.setattr(
        main_module.storage,
        'get_competitor_urls',
        lambda default_urls, profile_id='ggsel': default_urls,
    )
    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **_kwargs: [],
    )

    profiles = _build_profiles(logging.getLogger('test-main'))
    by_id = {profile['id']: profile for profile in profiles}

    assert by_id['ggsel']['tracked_products'] == []
    assert by_id['ggsel']['product_id'] == 1111
    assert by_id['ggsel']['competitor_urls'] == []
    assert by_id['digiseller']['tracked_products'] == []
    assert by_id['digiseller']['product_id'] == 2222
    assert by_id['digiseller']['competitor_urls'] == []
