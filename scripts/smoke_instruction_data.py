#!/usr/bin/env python3
"""Smoke-check доступности текстов инструкций по профилям."""

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
from src.scheduler import Scheduler


class _DummyTelegram:
    async def notify(self, *_args, **_kwargs):
        return None

    async def notify_error(self, *_args, **_kwargs):
        return None


def _shorten(text: str, max_len: int) -> str:
    value = (text or '').strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + '…'


def _print_extract(
    *,
    profile: str,
    product_id: int,
    locale: str,
    mode: str,
    text: str,
    preview_chars: int,
):
    print(
        f'[{profile}] product={product_id} '
        f'locale={locale} mode={mode} len={len(text)}'
    )
    if text:
        print(f'[{profile}] preview={_shorten(text, preview_chars)}')


def _extract_for_profile(
    *,
    profile: str,
    scheduler: Scheduler,
    client,
    product_ids: list[int],
    preview_chars: int,
) -> bool:
    ok_any = False
    for product_id in product_ids:
        if product_id <= 0:
            continue

        if profile == 'ggsel':
            product_info = client.get_product_info(product_id, timeout=10) or {}
            locales = ['ru', 'en']
            payloads = {
                'ru': product_info,
                'en': product_info,
            }
        else:
            product_info_ru = client.get_product_info(
                product_id,
                timeout=10,
                lang='ru-RU',
            ) or {}
            product_info_en = client.get_product_info(
                product_id,
                timeout=10,
                lang='en-US',
            ) or {}
            locales = ['ru', 'en']
            payloads = {
                'ru': product_info_ru,
                'en': product_info_en,
            }

        for locale in locales:
            for mode in ('already', 'add'):
                text = scheduler._pick_instruction_text(
                    payloads.get(locale, {}),
                    mode=mode,
                    locale=locale,
                )
                _print_extract(
                    profile=profile,
                    product_id=product_id,
                    locale=locale,
                    mode=mode,
                    text=text,
                    preview_chars=preview_chars,
                )
                if text:
                    ok_any = True
    return ok_any


def _ggsel_product_ids() -> list[int]:
    product_id = int(config.GGSEL_PRODUCT_ID or 0)
    return [product_id] if product_id > 0 else []


def _digiseller_product_ids() -> list[int]:
    ids: list[int] = []
    for value in config.DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS or []:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in ids:
            ids.append(parsed)
    default_pid = int(config.DIGISELLER_PRODUCT_ID or 0)
    if default_pid > 0 and default_pid not in ids:
        ids.append(default_pid)
    return ids


def check_ggsel(args) -> bool:
    if not config.GGSEL_ENABLED:
        print('[ggsel] skipped (disabled)')
        return True
    product_ids = _ggsel_product_ids()
    if not product_ids:
        print('[ggsel] no product ids configured')
        return False
    client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        api_secret=config.GGSEL_API_SECRET,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
        access_token=config.GGSEL_ACCESS_TOKEN,
    )
    scheduler = Scheduler(
        api_client=client,
        telegram_bot=_DummyTelegram(),
        profile_id='ggsel',
        profile_name='GGSEL',
        product_id=product_ids[0],
        competitor_urls=[],
    )
    return _extract_for_profile(
        profile='ggsel',
        scheduler=scheduler,
        client=client,
        product_ids=product_ids,
        preview_chars=args.preview_chars,
    )


def check_digiseller(args) -> bool:
    if not config.DIGISELLER_ENABLED:
        print('[digiseller] skipped (disabled)')
        return True
    product_ids = _digiseller_product_ids()
    if not product_ids:
        print('[digiseller] no product ids configured')
        return False
    client = DigiSellerClient(
        api_key=config.DIGISELLER_API_KEY,
        api_secret=config.DIGISELLER_API_SECRET,
        seller_id=config.DIGISELLER_SELLER_ID,
        base_url=config.DIGISELLER_BASE_URL,
        lang=config.DIGISELLER_LANG,
        access_token=config.DIGISELLER_ACCESS_TOKEN,
        default_product_id=product_ids[0],
    )
    scheduler = Scheduler(
        api_client=client,
        telegram_bot=_DummyTelegram(),
        profile_id='digiseller',
        profile_name='DIGISELLER',
        product_id=product_ids[0],
        competitor_urls=[],
    )
    return _extract_for_profile(
        profile='digiseller',
        scheduler=scheduler,
        client=client,
        product_ids=product_ids,
        preview_chars=args.preview_chars,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Smoke-check доступности текстов инструкций',
    )
    parser.add_argument(
        '--profile',
        choices=('all', 'ggsel', 'digiseller'),
        default='all',
        help='какой профиль проверять',
    )
    parser.add_argument(
        '--preview-chars',
        type=int,
        default=160,
        help='длина preview текста (по умолчанию 160)',
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
