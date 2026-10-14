#!/usr/bin/env python3
"""Issue a GGSEL access token without exposing it through stdout."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GGSELClient = importlib.import_module('src.api_client').GGSELClient
config = importlib.import_module('src.config').config

DEFAULT_OUTPUT = Path('data/issued_ggsel_token.env')


def _is_probably_jwt(value: str) -> bool:
    parts = (value or '').split('.')
    return len(parts) == 3 and all(parts)


def _write_token_file(path: Path, token: str) -> Path:
    """Persist the issued token to a user-only file instead of stdout."""
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        'GGSEL_ACCESS_TOKEN=' + token + '\n',
        encoding='utf-8',
    )
    os.chmod(target, 0o600)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Issue a GGSEL access token and save it to a mode-0600 env snippet. '
            'The token is never printed to stdout.'
        )
    )
    parser.add_argument(
        '--output-file',
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f'secure output path (default: {DEFAULT_OUTPUT})',
    )
    return parser


def main(argv: Sequence[str] = ()) -> int:
    """Issue and validate a token.

    ``argv`` defaults to an empty sequence so callers/tests do not accidentally
    consume the parent process arguments.  The CLI passes ``sys.argv[1:]``
    explicitly below.
    """
    args = _build_parser().parse_args(list(argv))
    missing = []
    sign_secret = config.GGSEL_API_SECRET or config.GGSEL_API_KEY
    if not sign_secret:
        missing.append('GGSEL_API_SECRET (or GGSEL_API_KEY)')
    if not config.GGSEL_SELLER_ID:
        missing.append('GGSEL_SELLER_ID')

    if missing:
        print('issue-token: missing env vars: ' + ', '.join(missing))
        return 2
    if not config.GGSEL_API_SECRET and _is_probably_jwt(config.GGSEL_API_KEY):
        print(
            'issue-token: GGSEL_API_KEY looks like a JWT access token; '
            'set GGSEL_API_SECRET to issue a new token'
        )
        return 2

    client = GGSELClient(
        api_key=config.GGSEL_API_KEY,
        api_secret=config.GGSEL_API_SECRET,
        seller_id=config.GGSEL_SELLER_ID,
        base_url=config.GGSEL_BASE_URL,
        lang=config.GGSEL_LANG,
    )

    ok = client._refresh_access_token(timeout=20)
    print(f'issue-token: success={ok}')
    if not ok or not client.access_token:
        return 1

    output_path = _write_token_file(args.output_file, client.access_token)
    print(
        'issue-token: token saved securely to '
        f'{output_path} (mode 0600; value not printed)'
    )
    if client.token_valid_thru is not None:
        print(f'issue-token: valid_thru={client.token_valid_thru.isoformat()}')

    # Quick validation on a read endpoint.
    probe = client.check_api_access()
    print(f'issue-token: probe_api_access={probe}')
    return 0 if probe else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
