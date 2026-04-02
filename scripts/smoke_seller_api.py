#!/usr/bin/env python3
"""Smoke-check Seller API по текущему .env без изменения цены."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api_client import GGSELClient
from src.config import config


def main() -> int:
    missing = []
    if not config.GGSEL_API_KEY and not config.GGSEL_ACCESS_TOKEN:
        missing.append('GGSEL_API_KEY or GGSEL_ACCESS_TOKEN')
    if not config.GGSEL_PRODUCT_ID:
        missing.append('GGSEL_PRODUCT_ID')

    if missing:
        print('smoke: missing env vars: ' + ', '.join(missing))
        return 2

    client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
        access_token=config.GGSEL_ACCESS_TOKEN,
    )

    api_access = client.check_api_access()
    print(f'smoke: api_access={api_access}')
    if not api_access:
        # Детализируем причину авторизации для быстрой диагностики.
        import hashlib
        import requests
        import time
        url = f'{config.GGSEL_BASE_URL}/products/list'
        try:
            resp = requests.get(
                url,
                params={'page': 1, 'count': 1, 'token': client.access_token or ''},
                headers={'lang': config.GGSEL_LANG, 'accept': 'application/json'},
                timeout=20,
            )
            print(f'smoke: auth_status={resp.status_code}')
            print(f'smoke: www_authenticate={resp.headers.get("www-authenticate")}')
            print(f'smoke: x_request_id={resp.headers.get("x-request-id")}')
        except Exception as e:
            print(f'smoke: auth_probe_error={e}')

        # Дополнительно проверяем прямой apilogin по документации.
        try:
            ts = str(int(time.time()))
            sign = hashlib.sha256((config.GGSEL_API_KEY + ts).encode('utf-8')).hexdigest()
            login_resp = requests.post(
                f'{config.GGSEL_BASE_URL}/apilogin',
                json={
                    'seller_id': config.GGSEL_SELLER_ID,
                    'timestamp': ts,
                    'sign': sign,
                },
                timeout=20,
            )
            print(f'smoke: apilogin_status={login_resp.status_code}')
            print(f'smoke: apilogin_body={login_resp.text[:300]}')
        except Exception as e:
            print(f'smoke: apilogin_probe_error={e}')
        return 1

    product = client.get_product(config.GGSEL_PRODUCT_ID)
    product_found = product is not None
    print(f'smoke: product_found={product_found} id={config.GGSEL_PRODUCT_ID}')
    if not product_found:
        return 1

    print(f'smoke: product_price={product.price}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
