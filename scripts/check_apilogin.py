#!/usr/bin/env python3
"""Проверка связки GGSEL_API_KEY + GGSEL_SELLER_ID через /apilogin."""

from __future__ import annotations

import hashlib
import time
import sys
import json

import requests

from src.config import config


def main() -> int:
    missing = []
    if not config.GGSEL_API_KEY:
        missing.append('GGSEL_API_KEY')
    if not config.GGSEL_SELLER_ID:
        missing.append('GGSEL_SELLER_ID')

    if missing:
        print('apilogin-check: missing env vars: ' + ', '.join(missing))
        return 2

    print(f'apilogin-check: seller_id={config.GGSEL_SELLER_ID}')
    print(f'apilogin-check: api_key_len={len(config.GGSEL_API_KEY)}')

    ts = str(int(time.time()))
    sign = hashlib.sha256((config.GGSEL_API_KEY + ts).encode('utf-8')).hexdigest()

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

    retval = data.get('retval')
    print(f'apilogin-check: retval={retval}')
    print(f'apilogin-check: retdesc={data.get("retdesc") or data.get("desc")}')

    token = data.get('token')
    valid_thru = data.get('valid_thru')
    if token:
        print(f'apilogin-check: token_received=yes len={len(str(token))}')
        print(f'apilogin-check: valid_thru={valid_thru}')
        return 0

    print('apilogin-check: token_received=no')
    return 1


if __name__ == '__main__':
    sys.exit(main())
