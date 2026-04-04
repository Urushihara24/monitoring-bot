#!/usr/bin/env python3
"""
Health check для контейнера/сервиса.
Проверяет heartbeat и API доступность активных профилей.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.api_client import GGSELClient
from src import chat_autoreply as chat_keys
from src.config import config
from src.digiseller_client import DigiSellerClient
from src.storage import Storage

DB_PATH = os.getenv('HEALTHCHECK_DB_PATH', 'data/state.db')
storage = Storage(DB_PATH)


def _parse_runtime_iso(value: str | None):
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        normalized = raw.replace('Z', '+00:00')
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def check_profile_cycle(profile_id: str, max_age_seconds: int) -> bool:
    state = storage.get_state(profile_id=profile_id)
    last_cycle = state.get('last_cycle')
    if not last_cycle:
        print(f'[{profile_id}] ⚠ last_cycle: нет данных')
        return True
    age = (datetime.now() - last_cycle).total_seconds()
    if age > max_age_seconds:
        print(
            f'[{profile_id}] ⚠ last_cycle устарел: '
            f'{int(age)}s > {max_age_seconds}s'
        )
        return False
    print(f'[{profile_id}] ✅ heartbeat {int(age)}s')
    return True


def check_ggsel_api() -> bool:
    if not config.GGSEL_ENABLED:
        return True
    if not config.GGSEL_API_KEY and not config.GGSEL_ACCESS_TOKEN:
        print('[ggsel] ⚠ credentials не заданы')
        return False
    client = GGSELClient(
        api_key=config.GGSEL_API_KEY or '',
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
        access_token=config.GGSEL_ACCESS_TOKEN or '',
    )
    ok = client.check_api_access()
    print(f'[ggsel] {"✅" if ok else "❌"} api_access={ok}')
    return ok


def check_digiseller_api() -> bool:
    if not config.DIGISELLER_ENABLED:
        return True
    if not config.DIGISELLER_API_KEY and not config.DIGISELLER_ACCESS_TOKEN:
        print('[digiseller] ⚠ credentials не заданы')
        return False
    client = DigiSellerClient(
        api_key=config.DIGISELLER_API_KEY or '',
        seller_id=config.DIGISELLER_SELLER_ID,
        base_url=config.DIGISELLER_BASE_URL,
        lang=config.DIGISELLER_LANG,
        access_token=config.DIGISELLER_ACCESS_TOKEN or '',
        default_product_id=config.DIGISELLER_PRODUCT_ID,
    )
    ok = client.check_api_access()
    print(f'[digiseller] {"✅" if ok else "❌"} api_access={ok}')
    return ok


def check_digiseller_chat_autoreply(
    *,
    max_age_seconds: int,
    fail_on_error: bool,
) -> bool:
    if not config.DIGISELLER_ENABLED:
        return True
    if not bool(getattr(config, 'DIGISELLER_CHAT_AUTOREPLY_ENABLED', False)):
        return True

    last_run_raw = storage.get_runtime_setting(
        chat_keys.KEY_LAST_RUN_AT,
        profile_id='digiseller',
    )
    last_error = (
        storage.get_runtime_setting(
            chat_keys.KEY_LAST_ERROR,
            profile_id='digiseller',
        ) or ''
    ).strip()
    last_run = _parse_runtime_iso(last_run_raw)
    if not last_run:
        print('[digiseller] ⚠ chat_autoreply: нет last_run')
    else:
        age = int((datetime.now() - last_run).total_seconds())
        if age > max_age_seconds:
            print(
                '[digiseller] ⚠ chat_autoreply last_run устарел: '
                f'{age}s > {max_age_seconds}s'
            )
            return False
        print(f'[digiseller] ✅ chat_autoreply heartbeat {age}s')
    if fail_on_error and last_error:
        print(f'[digiseller] ❌ chat_autoreply last_error: {last_error}')
        return False
    if last_error:
        print(f'[digiseller] ⚠ chat_autoreply last_error: {last_error}')
    return True


def main() -> int:
    max_age_seconds = int(os.getenv('HEALTHCHECK_MAX_AGE_SECONDS', '300'))
    chat_max_age_seconds = int(
        os.getenv(
            'HEALTHCHECK_CHAT_AUTOREPLY_MAX_AGE_SECONDS',
            str(max_age_seconds * 2),
        )
    )
    fail_on_chat_error = (
        os.getenv('HEALTHCHECK_FAIL_ON_CHAT_AUTOREPLY_ERROR', 'false')
        .strip()
        .lower() in {'1', 'true', 'yes', 'on'}
    )
    print(f'Healthcheck @ {datetime.now().isoformat()}')
    active_profiles = []
    if config.GGSEL_ENABLED:
        active_profiles.append('ggsel')
    if config.DIGISELLER_ENABLED:
        active_profiles.append('digiseller')

    if not active_profiles:
        print('⚠ Нет активных профилей (GGSEL_ENABLED/DIGISELLER_ENABLED)')
        print('UNHEALTHY')
        return 1

    results = []
    for profile_id in active_profiles:
        results.append(check_profile_cycle(profile_id, max_age_seconds))

    if 'ggsel' in active_profiles:
        results.append(check_ggsel_api())
    if 'digiseller' in active_profiles:
        results.append(check_digiseller_api())
        results.append(
            check_digiseller_chat_autoreply(
                max_age_seconds=chat_max_age_seconds,
                fail_on_error=fail_on_chat_error,
            )
        )

    healthy = all(results)
    print('HEALTHY' if healthy else 'UNHEALTHY')
    return 0 if healthy else 1


if __name__ == '__main__':
    raise SystemExit(main())
