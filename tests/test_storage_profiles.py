from datetime import datetime

from src.storage import Storage


def test_profile_state_isolation(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    storage.update_state(profile_id='ggsel', last_price=0.31, update_count=5)
    storage.update_state(profile_id='digiseller', last_price=0.41, update_count=2)

    gg = storage.get_state(profile_id='ggsel')
    dg = storage.get_state(profile_id='digiseller')

    assert gg['last_price'] == 0.31
    assert dg['last_price'] == 0.41
    assert gg['update_count'] == 5
    assert dg['update_count'] == 2


def test_runtime_setting_isolation(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    storage.set_runtime_setting('CHECK_INTERVAL', '20', profile_id='ggsel')
    storage.set_runtime_setting('CHECK_INTERVAL', '55', profile_id='digiseller')

    assert storage.get_runtime_setting('CHECK_INTERVAL', profile_id='ggsel') == '20'
    assert (
        storage.get_runtime_setting('CHECK_INTERVAL', profile_id='digiseller')
        == '55'
    )


def test_competitor_urls_profile_specific(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    storage.set_competitor_urls(
        ['https://a.example'],
        profile_id='ggsel',
    )
    storage.set_competitor_urls(
        ['https://b.example', 'https://c.example'],
        profile_id='digiseller',
    )

    assert storage.get_competitor_urls([], profile_id='ggsel') == ['https://a.example']
    assert storage.get_competitor_urls([], profile_id='digiseller') == [
        'https://b.example',
        'https://c.example',
    ]


def test_alert_throttle_per_profile(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))

    assert storage.should_send_alert('x', cooldown_seconds=60, profile_id='ggsel')
    assert not storage.should_send_alert('x', cooldown_seconds=60, profile_id='ggsel')

    # Другой профиль не должен быть задушен.
    assert storage.should_send_alert('x', cooldown_seconds=60, profile_id='digiseller')


def test_parser_state_fields_are_persisted(tmp_path):
    db = tmp_path / 'state.db'
    storage = Storage(db_path=str(db))
    now = datetime.now()
    storage.update_state(
        profile_id='ggsel',
        last_competitor_url='https://example.com',
        last_competitor_parse_at=now,
        last_competitor_method='playwright',
        last_competitor_error='blocked',
        last_competitor_block_reason='captcha',
        last_competitor_status_code=403,
    )
    state = storage.get_state(profile_id='ggsel')

    assert state['last_competitor_url'] == 'https://example.com'
    assert state['last_competitor_method'] == 'playwright'
    assert state['last_competitor_error'] == 'blocked'
    assert state['last_competitor_block_reason'] == 'captcha'
    assert state['last_competitor_status_code'] == 403
    assert state['last_competitor_parse_at'] is not None
