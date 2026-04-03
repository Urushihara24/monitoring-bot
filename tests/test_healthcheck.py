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
