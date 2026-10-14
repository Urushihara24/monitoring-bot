#!/usr/bin/env python3
"""Run the pricing engine locally without marketplace or Telegram credentials."""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

from src.preflight import validate_startup_environment

validate_startup_environment()

from src.logic import calculate_price  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Simulate a pricing decision without seller API writes.',
    )
    parser.add_argument(
        '--competitor',
        type=float,
        nargs='+',
        default=[0.35],
        help='One or more competitor prices (default: 0.35).',
    )
    parser.add_argument(
        '--current',
        type=float,
        default=0.36,
        help='Current seller price (default: 0.36).',
    )
    parser.add_argument(
        '--mode',
        choices=('FOLLOW', 'DUMPING', 'RAISE'),
        default='DUMPING',
        help='Pricing strategy (default: DUMPING).',
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


def build_demo_config(args: argparse.Namespace) -> SimpleNamespace:
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
    decision = calculate_price(
        competitor_prices=list(args.competitor),
        current_price=args.current,
        last_update=None,
        config=build_demo_config(args),
    )
    return {
        'mode': args.mode,
        'competitor_prices': list(args.competitor),
        'current_price': args.current,
        'action': decision.action,
        'target_price': decision.price,
        'reason': decision.reason,
        'minimum_competitor_price': decision.competitor_price,
    }


def main() -> int:
    args = build_parser().parse_args()
    result = simulate(args)

    if args.output_format == 'json':
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print('Pricing simulation (no API writes)')
        print(f"mode: {result['mode']}")
        print(f"competitors: {result['competitor_prices']}")
        print(f"current price: {result['current_price']}")
        print(f"action: {result['action']}")
        print(f"target price: {result['target_price']}")
        print(f"reason: {result['reason']}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
