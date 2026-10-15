from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modular_scheduler import ModularScheduler
from src.scheduler import Scheduler as LegacyScheduler
from src.scheduler_runtime_host import (
    ExtractedSchedulerMethodError,
    SchedulerRuntimeHost,
)


EXTRACTED_ASYNC_METHODS = (
    'run_cycle',
    '_parse_competitor_price',
    '_notify_error_throttled',
    '_notify_skip_throttled',
    '_notify_competitor_change_if_needed',
    '_notify_parser_issue_if_needed',
    '_run_chat_autoreply',
)


def _host():
    return SchedulerRuntimeHost(
        object(),
        object(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=123,
        competitor_urls=[],
    )


def test_runtime_host_remains_legacy_scheduler_compatible():
    host = _host()

    assert isinstance(host, LegacyScheduler)
    assert issubclass(ModularScheduler, SchedulerRuntimeHost)
    assert issubclass(ModularScheduler, LegacyScheduler)


@pytest.mark.asyncio
@pytest.mark.parametrize('method_name', EXTRACTED_ASYNC_METHODS)
async def test_runtime_host_fails_closed_for_extracted_async_methods(method_name):
    host = _host()
    method = getattr(host, method_name)

    with pytest.raises(ExtractedSchedulerMethodError, match='was extracted'):
        if method_name == 'run_cycle':
            await method()
        elif method_name == '_parse_competitor_price':
            await method('https://example.test', SimpleNamespace())
        elif method_name == '_notify_error_throttled':
            await method('key', 'message')
        elif method_name == '_notify_skip_throttled':
            await method(SimpleNamespace(), 1.0, 0.9, 0.95, 'reason')
        elif method_name == '_notify_competitor_change_if_needed':
            await method(SimpleNamespace(), 1.0, 0.9, 1, 'https://example.test')
        elif method_name == '_notify_parser_issue_if_needed':
            await method(
                SimpleNamespace(),
                'https://example.test',
                SimpleNamespace(),
            )
        else:
            await method()


def test_runtime_host_fails_closed_for_extracted_sync_notification_method():
    host = _host()

    with pytest.raises(ExtractedSchedulerMethodError, match='was extracted'):
        host._log_warning_throttled(key='key', message='message')


def test_modular_scheduler_overrides_every_extracted_runtime_method():
    method_names = (*EXTRACTED_ASYNC_METHODS, '_log_warning_throttled')

    for method_name in method_names:
        assert (
            getattr(ModularScheduler, method_name)
            is not getattr(SchedulerRuntimeHost, method_name)
        ), method_name
