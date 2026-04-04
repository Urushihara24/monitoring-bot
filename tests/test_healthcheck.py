import healthcheck as hc


def test_main_unhealthy_when_no_profiles_enabled(monkeypatch):
    monkeypatch.setattr(hc.config, 'GGSEL_ENABLED', False)
    monkeypatch.setattr(hc.config, 'DIGISELLER_ENABLED', False)
    assert hc.main() == 1


def test_main_healthy_for_enabled_ggsel_profile(monkeypatch):
    monkeypatch.setattr(hc.config, 'GGSEL_ENABLED', True)
    monkeypatch.setattr(hc.config, 'DIGISELLER_ENABLED', False)

    calls = []

    def fake_cycle(profile_id, max_age):
        calls.append(('cycle', profile_id, max_age))
        return True

    def fake_ggsel_api():
        calls.append(('api', 'ggsel'))
        return True

    monkeypatch.setattr(hc, 'check_profile_cycle', fake_cycle)
    monkeypatch.setattr(hc, 'check_ggsel_api', fake_ggsel_api)

    assert hc.main() == 0
    assert ('cycle', 'ggsel', 300) in calls
    assert ('api', 'ggsel') in calls


def test_main_unhealthy_when_enabled_profile_api_fails(monkeypatch):
    monkeypatch.setattr(hc.config, 'GGSEL_ENABLED', True)
    monkeypatch.setattr(hc.config, 'DIGISELLER_ENABLED', False)
    monkeypatch.setattr(hc, 'check_profile_cycle', lambda *_args, **_kw: True)
    monkeypatch.setattr(hc, 'check_ggsel_api', lambda: False)

    assert hc.main() == 1


def test_main_checks_digiseller_chat_autoreply(monkeypatch):
    monkeypatch.setattr(hc.config, 'GGSEL_ENABLED', False)
    monkeypatch.setattr(hc.config, 'DIGISELLER_ENABLED', True)

    calls = []

    monkeypatch.setattr(
        hc,
        'check_profile_cycle',
        lambda profile_id, max_age: (
            calls.append(('cycle', profile_id, max_age)) or True
        ),
    )
    monkeypatch.setattr(
        hc,
        'check_digiseller_api',
        lambda: (calls.append(('api', 'digiseller')) or True),
    )
    monkeypatch.setattr(
        hc,
        'check_digiseller_chat_autoreply',
        lambda **kwargs: (calls.append(('chat', kwargs)) or True),
    )

    assert hc.main() == 0
    assert ('api', 'digiseller') in calls
    assert any(item[0] == 'chat' for item in calls)


def test_check_digiseller_chat_autoreply_fails_on_stale_run(monkeypatch):
    monkeypatch.setattr(hc.config, 'DIGISELLER_ENABLED', True)
    monkeypatch.setattr(hc.config, 'DIGISELLER_CHAT_AUTOREPLY_ENABLED', True)

    def fake_get_runtime_setting(key, default=None, profile_id='ggsel'):
        if key == 'CHAT_AUTOREPLY_LAST_RUN_AT':
            return '2000-01-01T00:00:00'
        if key == 'CHAT_AUTOREPLY_LAST_ERROR':
            return ''
        return default

    monkeypatch.setattr(hc.storage, 'get_runtime_setting', fake_get_runtime_setting)

    ok = hc.check_digiseller_chat_autoreply(
        max_age_seconds=60,
        fail_on_error=False,
    )
    assert ok is False
