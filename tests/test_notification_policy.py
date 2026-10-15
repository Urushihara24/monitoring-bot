from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.notification_policy import NotificationPolicy
from src.rsc_parser import ParseResult


class FakeStorage:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[dict[str, object]] = []

    def should_send_alert(
        self,
        *,
        key: str,
        cooldown_seconds: int,
        profile_id: str,
    ) -> bool:
        self.calls.append(
            {
                'key': key,
                'cooldown_seconds': cooldown_seconds,
                'profile_id': profile_id,
            }
        )
        return self.allowed


class FakeTelegram:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.skips: list[dict[str, object]] = []
        self.competitor_changes: list[dict[str, object]] = []
        self.parser_issues: list[dict[str, object]] = []

    async def notify_error(self, message: str) -> None:
        self.errors.append(message)

    async def notify_skip(self, **kwargs) -> None:
        self.skips.append(kwargs)

    async def notify_competitor_price_changed(self, **kwargs) -> None:
        self.competitor_changes.append(kwargs)

    async def notify_parser_issue(self, **kwargs) -> None:
        self.parser_issues.append(kwargs)


def _policy(*, profile_id='ggsel', allowed=True):
    storage = FakeStorage(allowed=allowed)
    telegram = FakeTelegram()
    runtime = SimpleNamespace(NOTIFY_ERRORS=True)
    policy = NotificationPolicy(
        profile_id=profile_id,
        profile_name=profile_id.upper(),
        telegram_bot=telegram,
        runtime_loader=lambda: runtime,
        runtime_storage=storage,
    )
    return policy, storage, telegram, runtime


@pytest.mark.asyncio
async def test_error_notification_respects_global_mute():
    policy, storage, telegram, runtime = _policy()
    runtime.NOTIFY_ERRORS = False

    await policy.notify_error_throttled(
        key='boom',
        message='something failed',
        cooldown_seconds=15,
        runtime=runtime,
    )

    assert telegram.errors == []
    assert storage.calls == [
        {
            'key': 'notify_errors_muted:boom',
            'cooldown_seconds': 60,
            'profile_id': 'ggsel',
        }
    ]


@pytest.mark.asyncio
async def test_error_notification_is_tagged_and_throttled():
    policy, storage, telegram, runtime = _policy()

    await policy.notify_error_throttled(
        key='boom',
        message='something failed',
        cooldown_seconds=120,
        runtime=runtime,
    )

    assert telegram.errors == ['[GGSEL] something failed']
    assert storage.calls[-1] == {
        'key': 'boom',
        'cooldown_seconds': 120,
        'profile_id': 'ggsel',
    }


@pytest.mark.asyncio
async def test_skip_notification_preserves_payload():
    policy, storage, telegram, _runtime = _policy()
    runtime = SimpleNamespace(
        NOTIFY_SKIP=True,
        NOTIFY_SKIP_COOLDOWN_SECONDS=77,
    )

    await policy.notify_skip_throttled(
        runtime=runtime,
        current_price=1.0,
        target_price=0.9,
        competitor_price=0.95,
        reason='cooldown',
    )

    assert storage.calls[-1]['key'] == 'skip_notification'
    assert telegram.skips == [
        {
            'current_price': 1.0,
            'target_price': 0.9,
            'competitor_price': 0.95,
            'reason': 'cooldown',
            'profile_name': 'GGSEL',
        }
    ]


@pytest.mark.asyncio
async def test_digiseller_transient_parser_issue_requires_three_failures():
    policy, storage, telegram, _runtime = _policy(profile_id='digiseller')
    runtime = SimpleNamespace(
        NOTIFY_PARSER_ISSUES=True,
        PARSER_ISSUE_COOLDOWN_SECONDS=300,
    )
    result = ParseResult(
        success=False,
        error='blocked',
        block_reason='http_403',
        method='fixture',
        status_code=403,
    )

    await policy.notify_parser_issue_if_needed(
        runtime=runtime,
        url='https://plati.market/itm/example/1',
        result=result,
        fail_streak=2,
    )

    assert storage.calls == []
    assert telegram.parser_issues == []

    await policy.notify_parser_issue_if_needed(
        runtime=runtime,
        url='https://plati.market/itm/example/1',
        result=result,
        fail_streak=3,
    )

    assert storage.calls[-1]['key'] == 'parser_issue:http_403'
    assert telegram.parser_issues == [
        {
            'url': 'https://plati.market/itm/example/1',
            'method': 'fixture',
            'reason': 'http_403',
            'error': 'blocked',
            'status_code': 403,
            'profile_name': 'DIGISELLER',
        }
    ]
