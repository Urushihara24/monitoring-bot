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


def test_config_optional_bool_is_none_on_empty(monkeypatch):
    monkeypatch.setenv('DIGISELLER_NOTIFY_PARSER_ISSUES', '')
    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()
    assert cfg.DIGISELLER_NOTIFY_PARSER_ISSUES is None


def test_config_parses_digiseller_chat_autoreply_fields(monkeypatch):
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_ENABLED', '1')
    monkeypatch.setenv(
        'DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS',
        '5077639, 5104800, bad',
    )
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE', '30')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES', '3')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES', '0')
    monkeypatch.setenv('DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES', '77')
    monkeypatch.setenv(
        'DIGISELLER_CHAT_TEMPLATE_RU_ALREADY',
        'RU already',
    )

    cfg_mod = _reload_config_module()
    cfg = cfg_mod.Config()

    assert cfg.DIGISELLER_CHAT_AUTOREPLY_ENABLED is True
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS == [5077639, 5104800]
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE == 30
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES == 3
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES is False
    assert cfg.DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES == 77
    assert cfg.DIGISELLER_CHAT_TEMPLATE_RU_ALREADY == 'RU already'
