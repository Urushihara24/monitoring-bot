from __future__ import annotations

import sqlite3

from src import pricing_cycle_coordinator as pricing_cycle_module
from src.modular_scheduler import ModularScheduler
from src.storage import Storage
from src.storage_repositories import (
    RepositoryStorageFacade,
    StorageRepositories,
    TelegramSettingsPersistenceFacade,
    repositories,
    repository_storage,
)


def test_repositories_preserve_existing_sqlite_schema_and_state_semantics(tmp_path):
    db_path = tmp_path / 'state.db'
    backend = Storage(str(db_path))
    repos = StorageRepositories.from_backend(backend)

    repos.pricing.update_state(
        profile_id='ggsel:101',
        last_price=0.34567,
        last_competitor_min=0.45678,
    )
    repos.pricing.increment_update_count(profile_id='ggsel:101')
    repos.pricing.increment_skip_count(profile_id='ggsel:101')

    state = backend.get_state(profile_id='ggsel:101')
    assert state['last_price'] == 0.3457
    assert state['last_competitor_min'] == 0.4568
    assert state['update_count'] == 1
    assert state['skip_count'] == 1

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert {
        'profile_state',
        'price_history',
        'runtime_settings',
        'tracked_products',
        'settings_history',
        'alert_state',
    }.issubset(tables)
    assert not any(name.endswith('_repository') for name in tables)


def test_runtime_repository_preserves_parent_inheritance_and_history(tmp_path):
    backend = Storage(str(tmp_path / 'state.db'))
    repos = StorageRepositories.from_backend(backend)

    repos.runtime.set_runtime_setting(
        'MODE',
        'FOLLOW',
        user_id=77,
        source='test',
        profile_id='ggsel',
    )

    assert (
        repos.runtime.get_runtime_setting(
            'MODE',
            profile_id='ggsel:123',
        )
        == 'FOLLOW'
    )
    change = repos.history.get_last_setting_change(
        'MODE',
        profile_id='ggsel',
    )
    assert change is not None
    assert change['new_value'] == 'FOLLOW'
    assert change['user_id'] == 77
    assert change['source'] == 'test'


def test_chat_metadata_repository_uses_existing_runtime_settings_table(tmp_path):
    backend = Storage(str(tmp_path / 'state.db'))
    repos = StorageRepositories.from_backend(backend)

    repos.chat.set('CHAT_SENT_COUNT', '2', profile_id='ggsel')
    updated = repos.chat.increment(
        'CHAT_SENT_COUNT',
        profile_id='ggsel',
        delta=3,
    )

    assert updated == 5
    assert repos.chat.get('CHAT_SENT_COUNT', profile_id='ggsel') == '5'
    assert (
        backend.get_runtime_setting('CHAT_SENT_COUNT', profile_id='ggsel')
        == '5'
    )
    rows = repos.chat.list_with_last_change(
        profile_id='ggsel',
        key_prefix='CHAT_',
    )
    assert any(row['key'] == 'CHAT_SENT_COUNT' for row in rows)
    assert repos.chat.delete('CHAT_SENT_COUNT', profile_id='ggsel') is True
    assert repos.chat.get('CHAT_SENT_COUNT', profile_id='ggsel') is None


def test_history_repository_writes_existing_price_history_table(tmp_path):
    db_path = tmp_path / 'state.db'
    backend = Storage(str(db_path))
    repos = StorageRepositories.from_backend(backend)

    repos.history.add_price_history(
        old_price=0.4,
        new_price=0.39,
        competitor_price=0.395,
        reason='test',
        profile_id='ggsel:123',
    )

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            '''
            SELECT profile_id, old_price, new_price, competitor_price, reason
            FROM price_history
            ORDER BY id DESC
            LIMIT 1
            '''
        ).fetchone()

    assert row == ('ggsel:123', 0.4, 0.39, 0.395, 'test')


def test_repository_compatibility_facades_route_to_focused_repositories(tmp_path):
    backend = Storage(str(tmp_path / 'state.db'))
    repos = StorageRepositories.from_backend(backend)
    pricing_facade = RepositoryStorageFacade(repos)
    telegram_facade = TelegramSettingsPersistenceFacade(repos)

    pricing_facade.update_state(profile_id='ggsel:7', last_price=0.32109)
    pricing_facade.set_runtime_setting(
        'PARSER_FAIL_STREAK',
        '4',
        profile_id='ggsel:7',
    )
    pricing_facade.add_price_history(
        old_price=0.33,
        new_price=0.3211,
        competitor_price=0.322,
        reason='facade',
        profile_id='ggsel:7',
    )
    telegram_facade.set_auto_mode(
        True,
        profile_id='ggsel:7',
        user_id=8,
        source='telegram',
    )
    telegram_facade.set_runtime_setting(
        'PAIR_ENABLED',
        'true',
        profile_id='ggsel:7',
        user_id=8,
        source='telegram',
    )

    assert pricing_facade.get_state('ggsel:7')['last_price'] == 0.3211
    assert (
        pricing_facade.get_runtime_setting(
            'PARSER_FAIL_STREAK',
            profile_id='ggsel:7',
        )
        == '4'
    )
    assert backend.get_state(profile_id='ggsel:7')['auto_mode'] is True
    assert (
        backend.get_runtime_setting('PAIR_ENABLED', profile_id='ggsel:7')
        == 'true'
    )


def test_active_modular_scheduler_is_wired_to_repository_boundaries():
    scheduler = ModularScheduler(
        object(),
        object(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=123,
        competitor_urls=[],
    )

    assert scheduler._parser_coordinator._storage is repositories.runtime
    assert scheduler._notification_policy._storage is repositories.runtime
    assert pricing_cycle_module.storage is repository_storage
