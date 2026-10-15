from pathlib import Path

from src.config import Config


def _read_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in Path('.env.example').read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
    return values


def test_env_example_ids_are_parseable_and_neutral():
    values = _read_env_example()

    for key in (
        'GGSEL_SELLER_ID',
        'GGSEL_PRODUCT_ID',
        'DIGISELLER_SELLER_ID',
        'DIGISELLER_PRODUCT_ID',
    ):
        assert key in values
        assert int(values[key]) == 0


def test_env_example_is_write_safe_by_default():
    values = _read_env_example()

    assert values['DRY_RUN'] == 'true'
    assert values['GGSEL_CHAT_AUTOREPLY_ENABLED'] == 'false'
    assert values['DIGISELLER_CHAT_AUTOREPLY_ENABLED'] == 'false'


def test_env_example_has_no_live_credentials():
    values = _read_env_example()

    assert values['GGSEL_API_KEY'] == 'your_api_key_here'
    assert values['GGSEL_API_SECRET'] == ''
    assert values['GGSEL_ACCESS_TOKEN'] == ''
    assert values['DIGISELLER_API_KEY'] == ''
    assert values['DIGISELLER_API_SECRET'] == ''
    assert values['DIGISELLER_ACCESS_TOKEN'] == ''


def test_env_example_is_valid_typed_configuration():
    cfg = Config(env=_read_env_example())

    assert cfg.GGSEL_SELLER_ID == 0
    assert cfg.GGSEL_PRODUCT_ID == 0
    assert cfg.DIGISELLER_ENABLED is False
    assert cfg.MODE == 'DUMPING'
    assert cfg.LOG_LEVEL == 'INFO'
