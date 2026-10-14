#!/usr/bin/env python3
"""Run several pricing cycles against an in-memory marketplace.

This script never opens network connections and never touches a real seller account.
It exercises the real pricing decision function plus the shared marketplace client
contract so contributors can observe update/skip behaviour without credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.logic import calculate_price  # noqa: E402
from src.marketplace import FakeMarketplaceClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Run the pricing engine against a fake in-memory marketplace.',
    )
    parser.add_argument(
        '--competitors',
        type=float,
        nargs='+',
        default=[0.35, 0.37, 0.34],
        help='Competitor minimum price for each simulated cycle.',
    )
    parser.add_argument('--current', type=float, default=0.36)
    parser.add_argument(
        '--mode',
        choices=('FOLLOW', 'DUMPING', 'RAISE'),
        default='DUMPING',
    )
    parser.add_argument('--min-price', type=float, default=0.25)
    parser.add_argument('--max-price', type=float, default=10.0)
    parser.add_argument('--desired-price', type=float, default=0.35)
    parser.add_argument('--undercut', type=float, default=0.0051)
    parser.add_argument('--raise-value', type=float, default=0.0049)
    parser.add_argument('--round-step', type=float, default=0.01)
    parser.add_argument('--max-down-step', type=float, default=0.03)
    parser.add_argument('--ignore-delta', type=float, default=0.001)
    parser.add_argument(
        '--format',
        choices=('text', 'json'),
        default='text',
        dest='output_format',
    )
    return parser


def build_runtime_config(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        MODE=args.mode,
        MIN_PRICE=args.min_price,
        MAX_PRICE=args.max_price,
        DESIRED_PRICE=args.desired_price,
        UNDERCUT_VALUE=args.undercut,
        RAISE_VALUE=args.raise_value,
        SHOWCASE_ROUND_STEP=args.round_step,
        WEAK_PRICE_CEIL_LIMIT=0.30,
        COOLDOWN_SECONDS=0,
        IGNORE_DELTA=args.ignore_delta,
        HARD_FLOOR_ENABLED=True,
        REBOUND_TO_DESIRED_ON_MIN=False,
        MAX_DOWN_STEP=args.max_down_step,
    )


def simulate(args: argparse.Namespace) -> dict[str, object]:
    client = FakeMarketplaceClient(price=args.current)
    config = build_runtime_config(args)
    cycles: list[dict[str, object]] = []

    for index, competitor_price in enumerate(args.competitors, start=1):
        current_price = client.get_my_price(client.product_id)
        decision = calculate_price(
            competitor_prices=[float(competitor_price)],
            current_price=current_price,
            last_update=None,
            config=config,
        )

        applied = False
        if decision.action == 'update' and decision.price is not None:
            applied = client.update_price(client.product_id, decision.price)

        cycles.append(
            {
                'cycle': index,
                'competitor_price': float(competitor_price),
                'before': current_price,
                'action': decision.action,
                'target_price': decision.price,
                'reason': decision.reason,
                'applied_to_fake_marketplace': applied,
                'after': client.get_my_price(client.product_id),
            }
        )

    return {
        'mode': args.mode,
        'network_calls': 0,
        'real_marketplace_writes': 0,
        'initial_price': args.current,
        'final_price': client.get_my_price(client.product_id),
        'cycles': cycles,
    }


def main() -> int:
    args = build_parser().parse_args()
    result = simulate(args)

    if args.output_format == 'json':
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    print('Fake marketplace runtime (no network, no real writes)')
    print(f"mode: {result['mode']}")
    for cycle in result['cycles']:
        print(
            'cycle {cycle}: competitor={competitor_price} '
            'before={before} action={action} target={target_price} after={after} '
            'reason={reason}'.format(**cycle)
        )
    print(f"final fake price: {result['final_price']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
