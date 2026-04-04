#!/usr/bin/env python3
"""Smoke-check активных профилей (GGSEL + DIGISELLER)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api_client import GGSELClient
from src.config import config
from src.digiseller_client import DigiSellerClient
from src.profile_smoke import SmokeResult, run_profile_smoke


def _print_result(profile: str, result: SmokeResult) -> bool:
    print(f'[{profile}] api_access={result.api_access}')
    print(f'[{profile}] product_read_ok={result.product_read_ok}')
    print(f'[{profile}] current_price={result.current_price}')
    print(f'[{profile}] write_probe_ok={result.write_probe_ok}')
    if result.mutated:
        print(f'[{profile}] rollback_ok={result.rollback_ok}')
    print(f'[{profile}] probe_price={result.probe_price}')
    if result.verify_price is not None:
        print(f'[{profile}] verify_price={result.verify_price}')
    if result.token_perms_ok is not None or result.token_perms_desc is not None:
        print(f'[{profile}] token_perms_ok={result.token_perms_ok}')
        print(f'[{profile}] token_perms_desc={result.token_perms_desc}')
    if (
        result.token_refresh_ok is not None
        or result.token_refresh_desc is not None
    ):
        print(f'[{profile}] token_refresh_ok={result.token_refresh_ok}')
        print(f'[{profile}] token_refresh_desc={result.token_refresh_desc}')
    if result.error:
        print(f'[{profile}] error={result.error}')
    if not result.api_access:
        return False
    if not result.product_read_ok:
        return False
    if not result.write_probe_ok:
        return False
    if result.mutated and not bool(result.rollback_ok):
        return False
    return True


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
    result = run_profile_smoke(
        client,
        config.GGSEL_PRODUCT_ID,
        mutate=args.mutate,
        delta=args.delta,
        verify_read=args.verify_read,
        write_probe=not args.read_only,
    )
    return _print_result('ggsel', result)


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
    result = run_profile_smoke(
        client,
        config.DIGISELLER_PRODUCT_ID,
        mutate=args.mutate,
        delta=args.delta,
        verify_read=args.verify_read,
        write_probe=not args.read_only,
    )
    return _print_result('digiseller', result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Smoke-check активных профилей API',
    )
    parser.add_argument(
        '--profile',
        choices=('all', 'ggsel', 'digiseller'),
        default='all',
        help='какой профиль проверять',
    )
    parser.add_argument(
        '--mutate',
        action='store_true',
        help=(
            'сделать реальное тестовое изменение цены и rollback; '
            'по умолчанию write probe выполняется noop-ценой'
        ),
    )
    parser.add_argument(
        '--delta',
        type=float,
        default=0.0001,
        help='дельта для mutate режима (по умолчанию 0.0001)',
    )
    parser.add_argument(
        '--verify-read',
        action='store_true',
        help='после write probe дополнительно перечитать текущую цену',
    )
    parser.add_argument(
        '--read-only',
        action='store_true',
        help='проверять только чтение (без write probe)',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mutate and args.read_only:
        print('invalid args: --mutate нельзя использовать вместе с --read-only')
        return 1
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
