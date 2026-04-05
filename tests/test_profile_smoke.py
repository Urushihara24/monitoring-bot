from src.profile_smoke import run_profile_smoke


class FakeClient:
    def __init__(
        self,
        *,
        api_ok=True,
        read_price=0.2649,
        update_results=None,
        perms_result=None,
        perms_error=None,
        refresh_ok=True,
        refresh_error=None,
    ):
        self.api_ok = api_ok
        self.read_price = read_price
        self.update_results = list(update_results or [True])
        self.update_calls = []
        self.perms_result = perms_result
        self.perms_error = perms_error
        self.refresh_ok = refresh_ok
        self.refresh_error = refresh_error

    def check_api_access(self):
        return self.api_ok

    def get_my_price(self, _product_id):
        return self.read_price

    def update_price(self, product_id, price):
        self.update_calls.append((product_id, price))
        if not self.update_results:
            return True
        return self.update_results.pop(0)

    def get_token_perms_status(self):
        if self.perms_error:
            raise RuntimeError(self.perms_error)
        if self.perms_result is None:
            return True, 'ok'
        return self.perms_result

    def can_refresh_access_token(self):
        if self.refresh_error:
            raise RuntimeError(self.refresh_error)
        return self.refresh_ok


class FakeDigiSellerClient(FakeClient):
    def __init__(self, *, display_price=None, my_price=1.1, **kwargs):
        super().__init__(read_price=my_price, **kwargs)
        self.display_price = display_price

    def get_display_price(self, _product_id):
        return self.display_price


def test_smoke_noop_success():
    client = FakeClient(update_results=[True])

    result = run_profile_smoke(client, 123, mutate=False, verify_read=True)

    assert result.error is None
    assert result.api_access is True
    assert result.product_read_ok is True
    assert result.write_probe_ok is True
    assert result.rollback_ok is None
    assert result.current_price == 0.2649
    assert result.probe_price == 0.2649
    assert result.verify_price == 0.2649
    assert result.token_perms_ok is True
    assert result.token_perms_desc == 'ok'
    assert result.token_refresh_ok is True
    assert result.token_refresh_desc == 'available'
    assert client.update_calls == [(123, 0.2649)]


def test_smoke_mutate_and_rollback_success():
    client = FakeClient(update_results=[True, True])

    result = run_profile_smoke(client, 123, mutate=True, delta=0.0001)

    assert result.error is None
    assert result.mutated is True
    assert result.write_probe_ok is True
    assert result.rollback_ok is True
    assert len(client.update_calls) == 2
    assert client.update_calls[0][1] == 0.265
    assert client.update_calls[1][1] == 0.2649


def test_smoke_fails_when_api_inaccessible():
    client = FakeClient(api_ok=False)

    result = run_profile_smoke(client, 123)

    assert result.api_access is False
    assert result.error == 'api_access_failed'
    assert client.update_calls == []


def test_smoke_write_probe_failure():
    client = FakeClient(update_results=[False])

    result = run_profile_smoke(client, 123, mutate=False)

    assert result.api_access is True
    assert result.product_read_ok is True
    assert result.write_probe_ok is False
    assert result.error == 'write_probe_failed'


def test_smoke_read_only_skips_write_probe():
    client = FakeClient(update_results=[False])

    result = run_profile_smoke(
        client,
        123,
        mutate=False,
        verify_read=True,
        write_probe=False,
    )

    assert result.error is None
    assert result.api_access is True
    assert result.product_read_ok is True
    assert result.write_probe_ok is True
    assert result.mutated is False
    assert result.current_price == 0.2649
    assert result.probe_price == 0.2649
    assert result.verify_price == 0.2649
    assert client.update_calls == []


def test_smoke_collects_token_perms_result():
    client = FakeClient(perms_result=(True, 'products.read, products.write'))

    result = run_profile_smoke(client, 123, mutate=False)

    assert result.error is None
    assert result.token_perms_ok is True
    assert result.token_perms_desc == 'products.read, products.write'


def test_smoke_token_perms_exception_is_non_fatal():
    client = FakeClient(perms_error='boom')

    result = run_profile_smoke(client, 123, mutate=False)

    assert result.error is None
    assert result.api_access is True
    assert result.write_probe_ok is True
    assert result.token_perms_ok is False
    assert result.token_perms_desc == 'exception:boom'


def test_smoke_token_refresh_exception_is_non_fatal():
    client = FakeClient(refresh_error='refresh-boom')

    result = run_profile_smoke(client, 123, mutate=False)

    assert result.error is None
    assert result.api_access is True
    assert result.write_probe_ok is True
    assert result.token_refresh_ok is False
    assert result.token_refresh_desc == 'exception:refresh-boom'


def test_smoke_digiseller_prefers_display_over_my_price():
    client = FakeDigiSellerClient(
        display_price=0.3249,
        my_price=1.1,
        update_results=[True],
    )

    result = run_profile_smoke(
        client,
        5077639,
        mutate=False,
        verify_read=True,
        write_probe=False,
    )

    assert result.error is None
    assert result.current_price == 0.3249
    assert result.probe_price == 0.3249
    assert result.verify_price == 0.3249


def test_smoke_digiseller_does_not_fallback_to_my_price():
    client = FakeDigiSellerClient(
        display_price=None,
        my_price=1.1,
        update_results=[True],
    )

    result = run_profile_smoke(
        client,
        5077639,
        mutate=False,
        verify_read=False,
        write_probe=False,
    )

    assert result.api_access is True
    assert result.product_read_ok is False
    assert result.error == 'price_read_failed'
