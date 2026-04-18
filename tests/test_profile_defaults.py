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
        DIGISELLER_RAISE_VALUE=0.0049,
        DIGISELLER_SHOWCASE_ROUND_STEP=0.01,
        DIGISELLER_REBOUND_TO_DESIRED_ON_MIN=True,
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
    assert defaults['RAISE_VALUE'] == '0.0049'
    assert defaults['SHOWCASE_ROUND_STEP'] == '0.01'
    assert defaults['REBOUND_TO_DESIRED_ON_MIN'] == 'true'
    assert defaults['MODE'] == 'DUMPING'
    assert defaults['FIXED_PRICE'] == '0.6'
    assert defaults['STEP_UP_VALUE'] == '0.07'
    assert defaults['CHECK_INTERVAL'] == '45'
    assert defaults['COOLDOWN_SECONDS'] == '20'


def test_build_profile_runtime_defaults_formats_bool_and_extended_keys():
    cfg = SimpleNamespace(
        DIGISELLER_POSITION_FILTER_ENABLED=True,
        DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED=False,
        DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP=0.05,
        DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP=0.11,
        DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE=False,
        DIGISELLER_NOTIFY_COMPETITOR_CHANGE=True,
        DIGISELLER_FAST_CHECK_INTERVAL_MIN=20,
        DIGISELLER_FAST_CHECK_INTERVAL_MAX=60,
        DIGISELLER_MAX_DOWN_STEP=0.03,
    )

    defaults = build_profile_runtime_defaults(cfg, 'digiseller')

    assert defaults['POSITION_FILTER_ENABLED'] == 'true'
    assert defaults['WEAK_UNKNOWN_RANK_ENABLED'] == 'false'
    assert defaults['WEAK_UNKNOWN_RANK_ABS_GAP'] == '0.05'
    assert defaults['WEAK_UNKNOWN_RANK_REL_GAP'] == '0.11'
    assert defaults['UPDATE_ONLY_ON_COMPETITOR_CHANGE'] == 'false'
    assert defaults['NOTIFY_COMPETITOR_CHANGE'] == 'true'
    assert defaults['FAST_CHECK_INTERVAL_MIN'] == '20'
    assert defaults['FAST_CHECK_INTERVAL_MAX'] == '60'
    assert defaults['MAX_DOWN_STEP'] == '0.03'


def test_build_profile_runtime_defaults_reads_missing_attrs_from_env(monkeypatch):
    cfg = SimpleNamespace()
    monkeypatch.setenv('DIGISELLER_IGNORE_DELTA', '0.001')
    monkeypatch.setenv('DIGISELLER_HARD_FLOOR_ENABLED', 'false')
    monkeypatch.setenv('DIGISELLER_WEAK_POSITION_THRESHOLD', '25')
    monkeypatch.setenv('DIGISELLER_SHOWCASE_ROUND_STEP', '0')
    monkeypatch.setenv('DIGISELLER_MODE', 'fixed')

    defaults = build_profile_runtime_defaults(cfg, 'digiseller')

    assert defaults['IGNORE_DELTA'] == '0.001'
    assert defaults['HARD_FLOOR_ENABLED'] == 'false'
    assert defaults['WEAK_POSITION_THRESHOLD'] == '25'
    assert defaults['SHOWCASE_ROUND_STEP'] == '0.0'
    assert defaults['MODE'] == 'DUMPING'


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
