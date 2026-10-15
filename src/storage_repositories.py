"""Focused persistence repositories over the existing SQLite Storage backend.

The legacy ``Storage`` object remains the database bootstrap/migration and
compatibility facade. Active runtime components can depend on narrower
repositories without changing the SQLite schema, database file, migrations or
persisted value semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .storage import DEFAULT_PROFILE, storage


class PricingStateRepository:
    """Profile pricing/runtime state and counters."""

    def __init__(self, backend: Any = storage) -> None:
        self.backend = backend

    def get_state(self, profile_id: str = DEFAULT_PROFILE) -> dict:
        return self.backend.get_state(profile_id=profile_id)

    def update_state(self, profile_id: str = DEFAULT_PROFILE, **kwargs) -> None:
        self.backend.update_state(profile_id=profile_id, **kwargs)

    def set_auto_mode(
        self,
        enabled: bool,
        *,
        profile_id: str = DEFAULT_PROFILE,
        user_id: Optional[int] = None,
        source: str = 'system',
    ) -> bool:
        return self.backend.set_auto_mode(
            enabled,
            profile_id=profile_id,
            user_id=user_id,
            source=source,
        )

    def increment_update_count(self, profile_id: str = DEFAULT_PROFILE) -> None:
        self.backend.increment_update_count(profile_id=profile_id)

    def increment_skip_count(self, profile_id: str = DEFAULT_PROFILE) -> None:
        self.backend.increment_skip_count(profile_id=profile_id)


class RuntimeSettingsRepository:
    """Runtime configuration, tracked products and alert throttling."""

    def __init__(self, backend: Any = storage) -> None:
        self.backend = backend

    def get_runtime_setting(
        self,
        key: str,
        default: Optional[str] = None,
        profile_id: str = DEFAULT_PROFILE,
        *,
        inherit_parent: bool = True,
    ) -> Optional[str]:
        return self.backend.get_runtime_setting(
            key,
            default=default,
            profile_id=profile_id,
            inherit_parent=inherit_parent,
        )

    def set_runtime_setting(
        self,
        key: str,
        value: str,
        user_id: Optional[int] = None,
        source: str = 'system',
        profile_id: str = DEFAULT_PROFILE,
    ) -> None:
        self.backend.set_runtime_setting(
            key,
            value,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def delete_runtime_setting(
        self,
        key: str,
        *,
        user_id: Optional[int] = None,
        source: str = 'system',
        profile_id: str = DEFAULT_PROFILE,
    ) -> bool:
        return self.backend.delete_runtime_setting(
            key,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def list_runtime_settings(
        self,
        *,
        profile_id: str = DEFAULT_PROFILE,
        key_prefix: Optional[str] = None,
        limit: int = 10000,
    ) -> list[dict]:
        return self.backend.list_runtime_settings(
            profile_id=profile_id,
            key_prefix=key_prefix,
            limit=limit,
        )

    def list_runtime_settings_with_last_change(
        self,
        *,
        profile_id: str = DEFAULT_PROFILE,
        key_prefix: Optional[str] = None,
        limit: int = 10000,
    ) -> list[dict]:
        return self.backend.list_runtime_settings_with_last_change(
            profile_id=profile_id,
            key_prefix=key_prefix,
            limit=limit,
        )

    def get_runtime_config(
        self,
        base_config,
        profile_id: str = DEFAULT_PROFILE,
        default_urls: Optional[list] = None,
    ):
        return self.backend.get_runtime_config(
            base_config,
            profile_id=profile_id,
            default_urls=default_urls,
        )

    def normalize_competitor_urls(self, urls: list) -> list:
        return self.backend.normalize_competitor_urls(urls)

    def get_competitor_urls(
        self,
        default_urls: list,
        profile_id: str = DEFAULT_PROFILE,
    ) -> list:
        return self.backend.get_competitor_urls(
            default_urls,
            profile_id=profile_id,
        )

    def set_competitor_urls(
        self,
        urls: list,
        user_id: Optional[int] = None,
        source: str = 'system',
        profile_id: str = DEFAULT_PROFILE,
    ) -> None:
        self.backend.set_competitor_urls(
            urls,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def list_tracked_products(self, **kwargs) -> list[dict]:
        return self.backend.list_tracked_products(**kwargs)

    def upsert_tracked_product(self, **kwargs) -> None:
        self.backend.upsert_tracked_product(**kwargs)

    def remove_tracked_product(self, **kwargs) -> bool:
        return self.backend.remove_tracked_product(**kwargs)

    def clear_tracked_products(self, **kwargs) -> list[int]:
        return self.backend.clear_tracked_products(**kwargs)

    def purge_product_runtime_data(self, **kwargs) -> dict[str, int]:
        return self.backend.purge_product_runtime_data(**kwargs)

    def should_send_alert(
        self,
        key: str,
        cooldown_seconds: int,
        profile_id: str = DEFAULT_PROFILE,
    ) -> bool:
        return self.backend.should_send_alert(
            key=key,
            cooldown_seconds=cooldown_seconds,
            profile_id=profile_id,
        )


class ChatMetadataRepository:
    """Namespaced chat metadata stored in the existing runtime_settings table."""

    def __init__(self, backend: Any = storage) -> None:
        self.backend = backend

    def get(self, key: str, *, profile_id: str) -> Optional[str]:
        return self.backend.get_runtime_setting(key, profile_id=profile_id)

    def set(
        self,
        key: str,
        value: str,
        *,
        profile_id: str,
        user_id: Optional[int] = None,
        source: str = 'chat_autoreply',
    ) -> None:
        self.backend.set_runtime_setting(
            key,
            value,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def delete(
        self,
        key: str,
        *,
        profile_id: str,
        user_id: Optional[int] = None,
        source: str = 'chat_autoreply',
    ) -> bool:
        return self.backend.delete_runtime_setting(
            key,
            user_id=user_id,
            source=source,
            profile_id=profile_id,
        )

    def increment(
        self,
        key: str,
        *,
        profile_id: str,
        delta: int = 1,
        source: str = 'chat_autoreply',
    ) -> int:
        raw = self.get(key, profile_id=profile_id)
        try:
            current = int(float(raw or 0))
        except (TypeError, ValueError):
            current = 0
        updated = max(0, current + int(delta))
        self.set(
            key,
            str(updated),
            profile_id=profile_id,
            source=source,
        )
        return updated

    def list_with_last_change(
        self,
        *,
        profile_id: str,
        key_prefix: Optional[str] = None,
        limit: int = 10000,
    ) -> list[dict]:
        return self.backend.list_runtime_settings_with_last_change(
            profile_id=profile_id,
            key_prefix=key_prefix,
            limit=limit,
        )


class HistoryRepository:
    """Price and settings audit history."""

    def __init__(self, backend: Any = storage) -> None:
        self.backend = backend

    def add_price_history(
        self,
        old_price: float,
        new_price: float,
        competitor_price: float,
        reason: str,
        profile_id: str = DEFAULT_PROFILE,
    ) -> None:
        self.backend.add_price_history(
            old_price=old_price,
            new_price=new_price,
            competitor_price=competitor_price,
            reason=reason,
            profile_id=profile_id,
        )

    def get_settings_history(
        self,
        limit: int = 20,
        profile_id: str = DEFAULT_PROFILE,
    ) -> list[dict]:
        return self.backend.get_settings_history(
            limit=limit,
            profile_id=profile_id,
        )

    def get_last_setting_change(
        self,
        key: str,
        profile_id: str = DEFAULT_PROFILE,
    ) -> Optional[dict]:
        return self.backend.get_last_setting_change(
            key,
            profile_id=profile_id,
        )


@dataclass(frozen=True)
class StorageRepositories:
    pricing: PricingStateRepository
    runtime: RuntimeSettingsRepository
    chat: ChatMetadataRepository
    history: HistoryRepository

    @classmethod
    def from_backend(cls, backend: Any) -> 'StorageRepositories':
        return cls(
            pricing=PricingStateRepository(backend),
            runtime=RuntimeSettingsRepository(backend),
            chat=ChatMetadataRepository(backend),
            history=HistoryRepository(backend),
        )


repositories = StorageRepositories.from_backend(storage)
