from __future__ import annotations

from types import SimpleNamespace

import pytest

from src import chat_autoreply as chat_keys
from src.chat_autoreply_coordinator import ChatAutoreplyCoordinator
from src.modular_scheduler import ModularScheduler


class DisabledHost:
    def _chat_autoreply_enabled(self) -> bool:
        return False

    def __getattr__(self, name: str):
        raise AssertionError(f'unexpected access after disabled guard: {name}')


class PermissionDeniedHost:
    def __init__(self) -> None:
        self.profile_name = 'GGSEL'
        self.api_client = SimpleNamespace(get_chat_perms_status=lambda: None)
        self.meta: list[tuple[str, str]] = []
        self.warnings: list[dict[str, object]] = []
        self.errors: list[dict[str, object]] = []

    def _chat_autoreply_enabled(self) -> bool:
        return True

    def _chat_autoreply_supported(self) -> bool:
        return True

    def _should_run_chat_autoreply_now(self) -> bool:
        return True

    def _chat_meta_set(self, key: str, value: str) -> None:
        self.meta.append((key, value))

    def _chat_autoreply_require_rules(self) -> bool:
        return True

    def _chat_autoreply_allow_custom_text(self) -> bool:
        return False

    def _chat_autoreply_allow_template_fallback(self) -> bool:
        return True

    def _chat_perms_status_cached(self) -> tuple[bool, str]:
        return False, 'http_429 rate limited'

    def _log_warning_throttled(self, **kwargs) -> None:
        self.warnings.append(kwargs)

    async def _notify_error_throttled(self, **kwargs) -> None:
        self.errors.append(kwargs)


@pytest.mark.asyncio
async def test_disabled_chat_autoreply_short_circuits_before_side_effects():
    coordinator = ChatAutoreplyCoordinator(DisabledHost())

    assert await coordinator.run() is None


@pytest.mark.asyncio
async def test_rate_limited_permissions_preserve_error_policy():
    host = PermissionDeniedHost()
    coordinator = ChatAutoreplyCoordinator(host)

    await coordinator.run()

    assert host.meta[0][0] == chat_keys.KEY_LAST_RUN_AT
    assert host.meta[-1] == (
        chat_keys.KEY_LAST_ERROR,
        'Rate limit chat API для авто-инструкций: http_429 rate limited',
    )
    expected = {
        'key': 'chat_autoreply_api_rate_limited',
        'message': 'Rate limit chat API для авто-инструкций: http_429 rate limited',
        'cooldown_seconds': 900,
    }
    assert host.warnings == [expected]
    assert host.errors == [expected]


@pytest.mark.asyncio
async def test_modular_scheduler_delegates_chat_orchestration(monkeypatch):
    scheduler = ModularScheduler(
        object(),
        object(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=123,
    )
    calls: list[str] = []

    async def fake_run():
        calls.append('run')

    monkeypatch.setattr(
        scheduler._chat_autoreply_coordinator,
        'run',
        fake_run,
    )

    assert await scheduler._run_chat_autoreply() is None
    assert calls == ['run']
