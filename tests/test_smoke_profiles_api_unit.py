from scripts import smoke_profiles_api as script
from src.profile_smoke import SmokeResult


def _base_result(**overrides):
    payload = dict(
        api_access=True,
        product_read_ok=True,
        current_price=0.33,
        write_probe_ok=True,
        rollback_ok=None,
        mutated=False,
        probe_price=0.33,
        verify_price=0.33,
        token_perms_ok=True,
        token_perms_desc='ok',
        error=None,
        token_refresh_ok=True,
        token_refresh_desc='available',
    )
    payload.update(overrides)
    return SmokeResult(**payload)


def test_print_result_allows_transient_digiseller_read_fail():
    result = _base_result(
        product_read_ok=False,
        current_price=None,
        write_probe_ok=False,
        probe_price=None,
        verify_price=None,
        error='price_read_failed',
    )
    assert script._print_result(
        'digiseller',
        result,
        allow_transient_read_fail=True,
    ) is True


def test_print_result_strict_mode_blocks_transient_read_fail():
    result = _base_result(
        product_read_ok=False,
        current_price=None,
        write_probe_ok=False,
        probe_price=None,
        verify_price=None,
        error='price_read_failed',
    )
    assert script._print_result(
        'digiseller',
        result,
        allow_transient_read_fail=False,
    ) is False


def test_print_result_ggsel_stays_strict_on_price_read_fail():
    result = _base_result(
        product_read_ok=False,
        current_price=None,
        write_probe_ok=False,
        probe_price=None,
        verify_price=None,
        error='price_read_failed',
    )
    assert script._print_result(
        'ggsel',
        result,
        allow_transient_read_fail=True,
    ) is False
