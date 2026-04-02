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
from src.config import config
from src.digiseller_client import DigiSellerClient
from src.storage import Storage

DB_PATH = os.getenv('HEALTHCHECK_DB_PATH', 'data/state.db')
storage = Storage(DB_PATH)


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


def main() -> int:
    max_age_seconds = int(os.getenv('HEALTHCHECK_MAX_AGE_SECONDS', '300'))
    print(f'Healthcheck @ {datetime.now().isoformat()}')
    results = []
    if config.GGSEL_ENABLED:
        results.append(check_profile_cycle('ggsel', max_age_seconds))
    if config.DIGISELLER_ENABLED:
        results.append(check_profile_cycle('digiseller', max_age_seconds))
    results.append(check_ggsel_api())
    results.append(check_digiseller_api())
    healthy = all(results) if results else False
    print('HEALTHY' if healthy else 'UNHEALTHY')
    return 0 if healthy else 1


if __name__ == '__main__':
    raise SystemExit(main())
