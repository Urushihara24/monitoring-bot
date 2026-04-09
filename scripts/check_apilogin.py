#!/usr/bin/env python3
"""Проверка связки GGSEL_API_KEY + GGSEL_SELLER_ID через /apilogin."""

from __future__ import annotations

import hashlib
import importlib
import time
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

config = importlib.import_module('src.config').config


def _response_retval(data: dict) -> int | None:
    """Поддержка разных вариантов ключа retval в ответе API."""
    if not isinstance(data, dict):
        return None
    for key in ('retval', 'retVal', 'ret_val'):
        if key not in data:
            continue
        try:
            return int(data.get(key))
        except Exception:
            return None
    return None


def _is_probably_jwt(value: str) -> bool:
    parts = (value or '').split('.')
    return len(parts) == 3 and all(parts)


def main() -> int:
    missing = []
    sign_secret = config.GGSEL_API_SECRET or config.GGSEL_API_KEY
    if not sign_secret:
        missing.append('GGSEL_API_SECRET (or GGSEL_API_KEY)')
    if not config.GGSEL_SELLER_ID:
        missing.append('GGSEL_SELLER_ID')

    if missing:
        print('apilogin-check: missing env vars: ' + ', '.join(missing))
        return 2
    if not config.GGSEL_API_SECRET and _is_probably_jwt(config.GGSEL_API_KEY):
        print(
            'apilogin-check: GGSEL_API_KEY выглядит как JWT access token; '
            'для /apilogin задайте GGSEL_API_SECRET'
        )
        return 2

    print(f'apilogin-check: seller_id={config.GGSEL_SELLER_ID}')
    print(f'apilogin-check: api_key_len={len(config.GGSEL_API_KEY)}')
    print(f'apilogin-check: sign_secret_len={len(sign_secret)}')

    ts = str(int(time.time()))
    sign = hashlib.sha256((sign_secret + ts).encode('utf-8')).hexdigest()

    url = f'{config.GGSEL_BASE_URL}/apilogin'
    payload = {
        'seller_id': config.GGSEL_SELLER_ID,
        'timestamp': ts,
        'sign': sign,
    }

    try:
        resp = requests.post(url, json=payload, timeout=20)
    except Exception as e:
        print(f'apilogin-check: request_error={e}')
        return 1

    print(f'apilogin-check: status={resp.status_code}')
    print(f'apilogin-check: x_request_id={resp.headers.get("x-request-id")}')

    try:
        data = resp.json()
    except Exception:
        print('apilogin-check: non-json response')
        print('apilogin-check: body_head=' + repr(resp.text[:300]))
        return 1

    retval = _response_retval(data)
    print(f'apilogin-check: retval={retval}')
    print(f'apilogin-check: retdesc={data.get("retdesc") or data.get("desc")}')

    token = data.get('token')
    valid_thru = data.get('valid_thru')
    if token and retval in (None, 0):
        print(f'apilogin-check: token_received=yes len={len(str(token))}')
        print(f'apilogin-check: valid_thru={valid_thru}')
        return 0

    print('apilogin-check: token_received=no')
    return 1


if __name__ == '__main__':
    sys.exit(main())
