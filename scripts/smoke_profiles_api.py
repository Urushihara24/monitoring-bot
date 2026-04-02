#!/usr/bin/env python3
"""Smoke-check активных профилей (GGSEL + DIGISELLER)."""

from __future__ import annotations

import sys

from src.api_client import GGSELClient
from src.config import config
from src.digiseller_client import DigiSellerClient


def check_ggsel() -> bool:
    if not config.GGSEL_ENABLED:
        print('[ggsel] skipped (disabled)')
        return True
    client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
        access_token=config.GGSEL_ACCESS_TOKEN,
    )
    ok = client.check_api_access()
    print(f'[ggsel] api_access={ok}')
    if not ok:
        return False
    if config.GGSEL_PRODUCT_ID:
        p = client.get_product(config.GGSEL_PRODUCT_ID)
        print(f'[ggsel] product_found={p is not None}')
        return p is not None
    return True


def check_digiseller() -> bool:
    if not config.DIGISELLER_ENABLED:
        print('[digiseller] skipped (disabled)')
        return True
    client = DigiSellerClient(
        api_key=config.DIGISELLER_API_KEY,
        seller_id=config.DIGISELLER_SELLER_ID,
        base_url=config.DIGISELLER_BASE_URL,
        lang=config.DIGISELLER_LANG,
        access_token=config.DIGISELLER_ACCESS_TOKEN,
        default_product_id=config.DIGISELLER_PRODUCT_ID,
    )
    ok = client.check_api_access()
    print(f'[digiseller] api_access={ok}')
    if not ok:
        return False
    if config.DIGISELLER_PRODUCT_ID:
        p = client.get_product(config.DIGISELLER_PRODUCT_ID)
        print(f'[digiseller] product_found={p is not None}')
        return p is not None
    return True


def main() -> int:
    results = [check_ggsel(), check_digiseller()]
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
