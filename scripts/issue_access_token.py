#!/usr/bin/env python3
"""Выпускает GGSEL access token через /apilogin и печатает его для .env."""

from __future__ import annotations

import sys

from src.api_client import GGSELClient
from src.config import config


def main() -> int:
    missing = []
    if not config.GGSEL_API_KEY:
        missing.append('GGSEL_API_KEY')
    if not config.GGSEL_SELLER_ID:
        missing.append('GGSEL_SELLER_ID')

    if missing:
        print('issue-token: missing env vars: ' + ', '.join(missing))
        return 2

    if config.GGSEL_API_KEY.count('.') == 2:
        print('issue-token: GGSEL_API_KEY looks like JWT access token, not API secret key')
        print('issue-token: use this value as GGSEL_ACCESS_TOKEN or provide real API secret in GGSEL_API_KEY')
        return 1

    client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
    )

    ok = client._refresh_access_token(timeout=20)
    print(f'issue-token: success={ok}')
    if not ok:
        return 1

    print('issue-token: put these lines into .env')
    print(f'GGSEL_ACCESS_TOKEN={client.access_token}')
    if client.token_valid_thru is not None:
        print(f'issue-token: valid_thru={client.token_valid_thru.isoformat()}')

    # Быстрая валидация токена на products/list
    probe = client.check_api_access()
    print(f'issue-token: probe_api_access={probe}')
    return 0 if probe else 1


if __name__ == '__main__':
    sys.exit(main())
