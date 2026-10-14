from src.preflight import (
    normalize_boolean_environment,
    normalize_id_environment,
)


def test_preflight_normalizes_missing_and_empty_ids_to_zero():
    env = {
        'GGSEL_SELLER_ID': '',
        'GGSEL_PRODUCT_ID': '  ',
    }

    errors = normalize_id_environment(env)

    assert errors == []
    assert env['GGSEL_SELLER_ID'] == '0'
    assert env['GGSEL_PRODUCT_ID'] == '0'
    assert env['DIGISELLER_SELLER_ID'] == '0'
    assert env['DIGISELLER_PRODUCT_ID'] == '0'


def test_preflight_rejects_non_integer_and_negative_ids():
    env = {
        'GGSEL_SELLER_ID': 'seller-123',
        'GGSEL_PRODUCT_ID': '-1',
        'DIGISELLER_SELLER_ID': '42',
        'DIGISELLER_PRODUCT_ID': '7',
    }

    errors = normalize_id_environment(env)

    assert errors == [
        "GGSEL_SELLER_ID must be an integer, got 'seller-123'",
        'GGSEL_PRODUCT_ID must be >= 0, got -1',
    ]
    assert env['DIGISELLER_SELLER_ID'] == '42'
    assert env['DIGISELLER_PRODUCT_ID'] == '7'


def test_preflight_canonicalizes_integer_values():
    env = {
        'GGSEL_SELLER_ID': ' 00123 ',
        'GGSEL_PRODUCT_ID': '456',
        'DIGISELLER_SELLER_ID': '0',
        'DIGISELLER_PRODUCT_ID': '0009',
    }

    errors = normalize_id_environment(env)

    assert errors == []
    assert env == {
        'GGSEL_SELLER_ID': '123',
        'GGSEL_PRODUCT_ID': '456',
        'DIGISELLER_SELLER_ID': '0',
        'DIGISELLER_PRODUCT_ID': '9',
    }


def test_preflight_canonicalizes_dry_run_boolean():
    env = {'DRY_RUN': ' YES '}

    errors = normalize_boolean_environment(env)

    assert errors == []
    assert env['DRY_RUN'] == 'true'


def test_preflight_rejects_invalid_dry_run_value():
    env = {'DRY_RUN': 'treu'}

    errors = normalize_boolean_environment(env)

    assert errors == [
        "DRY_RUN must be one of true/false, 1/0, yes/no, on/off; got 'treu'"
    ]
