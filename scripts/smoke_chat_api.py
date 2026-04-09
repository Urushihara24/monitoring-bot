#!/usr/bin/env python3
"""Smoke-check прав chat API активных профилей."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GGSELClient = importlib.import_module('src.api_client').GGSELClient
config = importlib.import_module('src.config').config
DigiSellerClient = importlib.import_module(
    'src.digiseller_client'
).DigiSellerClient


def _print_result(profile: str, ok: bool, desc: str) -> bool:
    print(f'[{profile}] chat_perms_ok={ok}')
    print(f'[{profile}] chat_perms_desc={desc}')
    return bool(ok)


def check_ggsel(args) -> bool:
    if not config.GGSEL_ENABLED:
        print('[ggsel] skipped (disabled)')
        return True
    client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        api_secret=config.GGSEL_API_SECRET,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
        access_token=config.GGSEL_ACCESS_TOKEN,
    )
    ok, desc = client.get_chat_perms_status(
        timeout=args.timeout,
        include_send_probe=args.send_probe,
    )
    return _print_result('ggsel', ok, desc)


def check_digiseller(args) -> bool:
    if not config.DIGISELLER_ENABLED:
        print('[digiseller] skipped (disabled)')
        return True
    client = DigiSellerClient(
        api_key=config.DIGISELLER_API_KEY,
        api_secret=config.DIGISELLER_API_SECRET,
        seller_id=config.DIGISELLER_SELLER_ID,
        base_url=config.DIGISELLER_BASE_URL,
        lang=config.DIGISELLER_LANG,
        access_token=config.DIGISELLER_ACCESS_TOKEN,
        default_product_id=config.DIGISELLER_PRODUCT_ID,
    )
    ok, desc = client.get_chat_perms_status(
        timeout=args.timeout,
        include_send_probe=args.send_probe,
    )
    return _print_result('digiseller', ok, desc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Smoke-check chat API профилей',
    )
    parser.add_argument(
        '--profile',
        choices=('all', 'ggsel', 'digiseller'),
        default='all',
        help='какой профиль проверять',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=8,
        help='таймаут запросов в секундах (по умолчанию 8)',
    )
    parser.add_argument(
        '--send-probe',
        action='store_true',
        help=(
            'добавить безопасную POST-пробу chat.send '
            '(id_i=0, без реальной отправки)'
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.profile == 'ggsel' and not config.GGSEL_ENABLED:
        print('[ggsel] disabled: set GGSEL_ENABLED=true to run this profile')
        return 1
    if args.profile == 'digiseller' and not config.DIGISELLER_ENABLED:
        print(
            '[digiseller] disabled: '
            'set DIGISELLER_ENABLED=true to run this profile'
        )
        return 1

    selected = []
    if args.profile in ('all', 'ggsel'):
        selected.append(check_ggsel(args))
    if args.profile in ('all', 'digiseller'):
        selected.append(check_digiseller(args))
    results = selected or [True]
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
