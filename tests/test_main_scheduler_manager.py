import asyncio

import pytest

import src.main as main_module


@pytest.mark.asyncio
async def test_scheduler_manager_builds_desired_specs_from_tracked_products(
    monkeypatch,
):
    profile = {
        'id': 'ggsel',
        'name': 'GGSEL',
        'product_id': 111,
        'competitor_urls': ['https://fallback.example'],
        'client': object(),
    }

    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **_kwargs: [
            {
                'product_id': 111,
                'competitor_urls': ['https://a.example/item'],
                'enabled': True,
            },
            {
                'product_id': 222,
                'competitor_urls': ['https://b.example/item'],
                'enabled': True,
            },
        ],
    )

    manager = main_module.SchedulerManager(
        logger=main_module.logging.getLogger('test'),
        profiles=[profile],
        telegram_bot=object(),  # не используется в _desired_specs
    )

    specs = manager._desired_specs()

    assert set(specs) == {'ggsel:111', 'ggsel:222'}
    assert specs['ggsel:111']['chat_autoreply_enabled'] is True
    assert specs['ggsel:222']['chat_autoreply_enabled'] is False


@pytest.mark.asyncio
async def test_scheduler_manager_sync_adds_and_removes_runtime_schedulers(
    monkeypatch,
):
    tracked_state = {
        'items': [
            {
                'product_id': 111,
                'competitor_urls': ['https://a.example/item'],
                'enabled': True,
            }
        ]
    }

    monkeypatch.setattr(
        main_module.storage,
        'list_tracked_products',
        lambda **_kwargs: list(tracked_state['items']),
    )

    class FakeScheduler:
        def __init__(
            self,
            _client,
            _telegram_bot,
            *,
            profile_id,
            base_profile_id,
            profile_name,
            product_id,
            competitor_urls,
            chat_autoreply_enabled,
        ):
            self.profile_id = profile_id
            self.base_profile_id = base_profile_id
            self.profile_name = profile_name
            self.product_id = product_id
            self.default_competitor_urls = list(competitor_urls)
            self.chat_autoreply_enabled = bool(chat_autoreply_enabled)
            self._running = False

        async def run(self):
            self._running = True
            while self._running:
                await asyncio.sleep(0)

        def stop(self):
            self._running = False

    monkeypatch.setattr(main_module, 'Scheduler', FakeScheduler)

    profile = {
        'id': 'ggsel',
        'name': 'GGSEL',
        'product_id': 111,
        'competitor_urls': ['https://fallback.example'],
        'client': object(),
    }
    manager = main_module.SchedulerManager(
        logger=main_module.logging.getLogger('test'),
        profiles=[profile],
        telegram_bot=object(),
    )

    await manager.sync_once()
    assert set(manager.schedulers) == {'ggsel:111'}

    tracked_state['items'] = [
        {
            'product_id': 222,
            'competitor_urls': ['https://b.example/item'],
            'enabled': True,
        }
    ]
    await manager.sync_once()
    assert set(manager.schedulers) == {'ggsel:222'}

    await manager.stop()
    assert manager.schedulers == {}
    assert manager.tasks == {}
