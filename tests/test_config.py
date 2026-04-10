import importlib

def _reload_config_module():
    module = importlib.import_module('src.config')
    return importlib.reload(module)


def test_config_parses_digiseller_optional_runtime_fields(monkeypatch):
    monkeypatch.setenv('DIGISELLER_WEAK_PRICE_CEIL_LIMIT', '0.3')
    monkeypatch.setenv('DIGISELLER_POSITION_FILTER_ENABLED', 'true')
    monkeypatch.setenv('DIGISELLER_WEAK_POSITION_THRESHOLD', '25')
    monkeypatch.setenv('DIGISELLER_FAST_CHECK_INTERVAL_MIN', '20')
    monkeypatch.setenv('DIGISELLER_FAST_CHECK_INTERVAL_MAX', '60')
    monkeypatch.setenv('DIGISELLER_NOTIFY_SKIP', 'false')
    monkeypatch.setenv('DIGISELLER_NOTIFY_COMPETITOR_CHANGE', '1')
    monkeypatch.setenv('DIGISELLER_HARD_FLOOR_ENABLED', 'yes')
    monkeypatch.setenv('DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE', 'on')
    monkeypatch.setenv('DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN', '0')
    monkeypatch.setenv('DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED', 'true')
    monkeypatch.setenv('DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP', '0.04')
    monkeypatch.setenv('DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP', '0.10')

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.DIGISELLER_WEAK_PRICE_CEIL_LIMIT == 0.3
    assert cfg.DIGISELLER_POSITION_FILTER_ENABLED is True
    assert cfg.DIGISELLER_WEAK_POSITION_THRESHOLD == 25
    assert cfg.DIGISELLER_FAST_CHECK_INTERVAL_MIN == 20
    assert cfg.DIGISELLER_FAST_CHECK_INTERVAL_MAX == 60
    assert cfg.DIGISELLER_NOTIFY_SKIP is False
    assert cfg.DIGISELLER_NOTIFY_COMPETITOR_CHANGE is True
    assert cfg.DIGISELLER_HARD_FLOOR_ENABLED is True
    assert cfg.DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE is True
    assert cfg.DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN is False
    assert cfg.DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED is True
    assert cfg.DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP == 0.04
    assert cfg.DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP == 0.10


def test_config_optional_bool_is_none_on_empty(monkeypatch):
    monkeypatch.setenv('DIGISELLER_NOTIFY_PARSER_ISSUES', '')
    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()
    assert cfg.DIGISELLER_NOTIFY_PARSER_ISSUES is None


def test_config_parses_digiseller_chat_autoreply_fields(monkeypatch):
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_ENABLED', '1')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT', '0')
    monkeypatch.setenv(
        'DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS',
        '5077639, 5104800, bad',
    )
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE', '30')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES', '3')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS', '25')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES', '0')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', '77')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES', '35')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK', '0')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS', '45')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS', '12')
    monkeypatch.setenv(
        'DIGISELLER_CHAT_TEMPLATE_RU_ALREADY',
        'RU already',
    )

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED is True
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT is False
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS == [5077639, 5104800]
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE == 30
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES == 3
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS == 25
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES is False
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES == 77
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES == 35
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK is False
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS == 45
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS == 12
    assert cfg.DIGISELLER_CHAT_TEMPLATE_RU_ALREADY == 'RU already'


def test_config_parses_ggsel_chat_autoreply_fields(monkeypatch):
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_ENABLED', '1')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT', '0')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS', '4697439, bad')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_PAGE_SIZE', '40')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_MAX_PAGES', '4')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS', '20')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES', '0')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', '15')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES', '42')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK', '1')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS', '10')
    monkeypatch.setenv('GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS', '8')
    monkeypatch.setenv('GGSEL_CHAT_TEMPLATE_EN_ADD', 'EN add')

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.GGSEL_CHAT_AUTOREPLY_ENABLED is True
    assert cfg.GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT is False
    assert cfg.GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS == [4697439]
    assert cfg.GGSEL_CHAT_AUTOREPLY_PAGE_SIZE == 40
    assert cfg.GGSEL_CHAT_AUTOREPLY_MAX_PAGES == 4
    assert cfg.GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS == 20
    assert cfg.GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES is False
    assert cfg.GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES == 15
    assert cfg.GGSEL_CHAT_AUTOREPLY_RECENT_LOOKBACK_MINUTES == 42
    assert cfg.GGSEL_CHAT_AUTOREPLY_ENABLE_RECENT_FALLBACK is True
    assert cfg.GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS == 10
    assert cfg.GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS == 8
    assert cfg.GGSEL_CHAT_TEMPLATE_EN_ADD == 'EN add'


def test_config_parses_profile_api_secrets(monkeypatch):
    monkeypatch.setenv('GGSEL_API_SECRET', 'gg-secret')
    monkeypatch.setenv('DIGISELLER_API_SECRET', 'dg-secret')

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.GGSEL_API_SECRET == 'gg-secret'
    assert cfg.DIGISELLER_API_SECRET == 'dg-secret'


def test_config_ggsel_competitor_urls_fallback_to_common(monkeypatch):
    monkeypatch.setenv(
        'COMPETITOR_URLS',
        'https://ggsel.net/catalog/product/a, https://ggsel.net/catalog/product/b',
    )
    monkeypatch.delenv('GGSEL_COMPETITOR_URLS', raising=False)

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.GGSEL_COMPETITOR_URLS == [
        'https://ggsel.net/catalog/product/a',
        'https://ggsel.net/catalog/product/b',
    ]


def test_config_ggsel_competitor_urls_override_common(monkeypatch):
    monkeypatch.setenv('COMPETITOR_URLS', 'https://global.example/item')
    monkeypatch.setenv(
        'GGSEL_COMPETITOR_URLS',
        'https://ggsel.net/catalog/product/one',
    )

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.GGSEL_COMPETITOR_URLS == [
        'https://ggsel.net/catalog/product/one',
    ]
