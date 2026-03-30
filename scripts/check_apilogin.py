#!/usr/bin/env python3
"""Проверка связки GGSEL_API_KEY + GGSEL_SELLER_ID через /apilogin."""

from __future__ import annotations

import hashlib
import time
import sys
import base64
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

    key_is_jwt_like = config.GGSEL_API_KEY.count('.') == 2
    print(f'apilogin-check: seller_id={config.GGSEL_SELLER_ID}')
    print(f'apilogin-check: api_key_len={len(config.GGSEL_API_KEY)}')
    print(f'apilogin-check: api_key_jwt_like={key_is_jwt_like}')
    print(f'apilogin-check: access_token_env_present={bool(config.GGSEL_ACCESS_TOKEN)}')
    if key_is_jwt_like:
        try:
            payload_part = config.GGSEL_API_KEY.split('.')[1]
            padded = payload_part + '=' * (-len(payload_part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8'))
            print(f'apilogin-check: jwt_sub={payload.get("sub")} jwt_iss={payload.get("iss")}')
        except Exception:
            print('apilogin-check: jwt_payload_parse_failed')

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
    print(f'apilogin-check: content_type={resp.headers.get("content-type")}')
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

    # Если в env задан access token — проверим, валиден ли он для products/list.
    if config.GGSEL_ACCESS_TOKEN:
        try:
            probe = requests.get(
                f'{config.GGSEL_BASE_URL}/products/list',
                params={'page': 1, 'count': 1, 'token': config.GGSEL_ACCESS_TOKEN},
                headers={'lang': config.GGSEL_LANG, 'accept': 'application/json'},
                timeout=20,
            )
            print(f'apilogin-check: access_token_probe_status={probe.status_code}')
            print(f'apilogin-check: access_token_probe_www_auth={probe.headers.get("www-authenticate")}')
        except Exception as e:
            print(f'apilogin-check: access_token_probe_error={e}')

    return 1


if __name__ == '__main__':
    sys.exit(main())
