#!/usr/bin/env python3
"""Smoke-check Seller API по текущему .env без изменения цены."""

from __future__ import annotations

import sys

from src.api_client import GGSELClient
from src.config import config


def main() -> int:
    missing = []
    if not config.GGSEL_API_KEY:
        missing.append('GGSEL_API_KEY')
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
    )

    api_access = client.check_api_access()
    print(f'smoke: api_access={api_access}')
    if not api_access:
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
