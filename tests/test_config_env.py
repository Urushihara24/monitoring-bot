from src.config_env import normalize_typed_environment


def test_typed_environment_canonicalizes_valid_values():
    env = {
        'DRY_RUN': ' YES ',
        'GGSEL_SELLER_ID': '00123',
        'CHECK_INTERVAL': '30.0',
        'MIN_PRICE': '0.25',
        'MODE': 'follow_exact',
        'LOG_LEVEL': 'debug',
        'GGSEL_CHAT_AUTOREPLY_POLICY': 'first_buyer_message',
        'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS': '10, 20.0, 30',
    }

    errors = normalize_typed_environment(env)

    assert errors == []
    assert env['DRY_RUN'] == 'true'
    assert env['GGSEL_SELLER_ID'] == '123'
    assert env['CHECK_INTERVAL'] == '30'
    assert env['MIN_PRICE'] == '0.25'
    assert env['MODE'] == 'FOLLOW'
    assert env['LOG_LEVEL'] == 'DEBUG'
    assert env['GGSEL_CHAT_AUTOREPLY_POLICY'] == 'FIRST_BUYER_MESSAGE'
    assert env['GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS'] == '10,20,30'


def test_typed_environment_rejects_invalid_booleans():
    env = {
        'GGSEL_ENABLED': 'treu',
        'DIGISELLER_NOTIFY_SKIP': 'sometimes',
    }

    errors = normalize_typed_environment(env)

    assert any(error.startswith('GGSEL_ENABLED must be one of') for error in errors)
    assert any(
        error.startswith('DIGISELLER_NOTIFY_SKIP must be one of')
        for error in errors
    )


def test_typed_environment_rejects_fractional_integer_instead_of_truncating():
    env = {'DIGISELLER_CHECK_INTERVAL': '20.5'}

    errors = normalize_typed_environment(env)

    assert errors == [
        "DIGISELLER_CHECK_INTERVAL must be an integer, got '20.5'"
    ]


def test_typed_environment_rejects_nan_inf_and_negative_safety_values():
    env = {
        'MIN_PRICE': 'nan',
        'MAX_PRICE': 'inf',
        'MAX_DOWN_STEP': '-0.01',
        'LOG_BACKUP_COUNT': '-1',
    }

    errors = normalize_typed_environment(env)

    assert any('MIN_PRICE must be finite' in error for error in errors)
    assert any('MAX_PRICE must be finite' in error for error in errors)
    assert any('MAX_DOWN_STEP must be >= 0' in error for error in errors)
    assert any('LOG_BACKUP_COUNT must be >= 0' in error for error in errors)


def test_typed_environment_rejects_unknown_modes_policies_and_log_levels():
    env = {
        'MODE': 'YOLO',
        'DIGISELLER_MODE': 'random',
        'GGSEL_CHAT_AUTOREPLY_POLICY': 'SEND_ALWAYS',
        'LOG_LEVEL': 'TRACE',
    }

    errors = normalize_typed_environment(env)

    assert len(errors) == 4
    assert any(error.startswith('MODE must resolve') for error in errors)
    assert any(error.startswith('DIGISELLER_MODE must resolve') for error in errors)
    assert any('GGSEL_CHAT_AUTOREPLY_POLICY must be one of' in error for error in errors)
    assert any('LOG_LEVEL must be one of' in error for error in errors)


def test_typed_environment_rejects_bad_csv_ids_instead_of_ignoring_them():
    env = {'GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS': '123, bad, 456'}

    errors = normalize_typed_environment(env)

    assert errors == [
        "GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS must be numeric, got 'bad'"
    ]


def test_optional_empty_values_remain_empty():
    env = {
        'DIGISELLER_MIN_PRICE': '',
        'DIGISELLER_NOTIFY_SKIP': '  ',
        'DIGISELLER_MODE': '',
    }

    errors = normalize_typed_environment(env)

    assert errors == []
    assert env['DIGISELLER_MIN_PRICE'] == ''
    assert env['DIGISELLER_NOTIFY_SKIP'] == '  '
    assert env['DIGISELLER_MODE'] == ''
