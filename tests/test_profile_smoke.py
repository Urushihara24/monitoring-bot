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
    ):
        self.api_ok = api_ok
        self.read_price = read_price
        self.update_results = list(update_results or [True])
        self.update_calls = []
        self.perms_result = perms_result
        self.perms_error = perms_error

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
