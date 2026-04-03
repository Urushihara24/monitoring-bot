from types import SimpleNamespace

from src.profile_defaults import (
    build_profile_runtime_defaults,
    seed_profile_runtime_defaults,
)


class FakeStorage:
    def __init__(self):
        self.data = {}
        self.set_calls = []

    def get_runtime_setting(self, key, profile_id='ggsel'):
        return self.data.get((profile_id, key))

    def set_runtime_setting(
        self,
        key,
        value,
        user_id=None,
        source='system',
        profile_id='ggsel',
    ):
        self.data[(profile_id, key)] = value
        self.set_calls.append((profile_id, key, value, source))


def test_build_profile_runtime_defaults_for_digiseller():
    cfg = SimpleNamespace(
        DIGISELLER_MIN_PRICE=0.11,
        DIGISELLER_MAX_PRICE=0.88,
        DIGISELLER_DESIRED_PRICE=0.55,
        DIGISELLER_UNDERCUT_VALUE=0.0051,
        DIGISELLER_MODE='step_up',
        DIGISELLER_FIXED_PRICE=0.6,
        DIGISELLER_STEP_UP_VALUE=0.07,
        DIGISELLER_CHECK_INTERVAL=45,
        DIGISELLER_COOLDOWN_SECONDS=20,
    )

    defaults = build_profile_runtime_defaults(cfg, 'digiseller')

    assert defaults['MIN_PRICE'] == '0.11'
    assert defaults['MAX_PRICE'] == '0.88'
    assert defaults['DESIRED_PRICE'] == '0.55'
    assert defaults['UNDERCUT_VALUE'] == '0.0051'
    assert defaults['MODE'] == 'STEP_UP'
    assert defaults['FIXED_PRICE'] == '0.6'
    assert defaults['STEP_UP_VALUE'] == '0.07'
    assert defaults['CHECK_INTERVAL'] == '45'
    assert defaults['COOLDOWN_SECONDS'] == '20'


def test_build_profile_runtime_defaults_non_digiseller_empty():
    cfg = SimpleNamespace()
    assert build_profile_runtime_defaults(cfg, 'ggsel') == {}


def test_seed_profile_runtime_defaults_sets_only_missing():
    storage = FakeStorage()
    storage.data[('digiseller', 'MIN_PRICE')] = '0.22'
    defaults = {
        'MIN_PRICE': '0.11',
        'MAX_PRICE': '0.88',
    }

    seeded = seed_profile_runtime_defaults(storage, 'digiseller', defaults)

    assert seeded == {'MAX_PRICE': '0.88'}
    assert storage.data[('digiseller', 'MIN_PRICE')] == '0.22'
    assert storage.data[('digiseller', 'MAX_PRICE')] == '0.88'
