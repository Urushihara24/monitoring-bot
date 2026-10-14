# Contributing

Contributions are welcome. The project controls real seller accounts, so changes that can reach marketplace write endpoints are treated as safety-sensitive.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

The example environment uses `DRY_RUN=true`. Keep it enabled unless you intentionally test writes on an account and product you control.

## Before opening a pull request

Run:

```bash
pytest -q
ruff check src tests scripts --select F,E9
python -m compileall -q src scripts healthcheck.py
```

For pricing-only changes, also exercise `scripts/demo_pricing.py` with representative edge cases.

## Change design

Prefer small, reviewable pull requests. In particular:

- keep pricing decisions separate from marketplace I/O;
- add regression tests before changing safety logic;
- preserve profile/product isolation;
- do not make a failed validation silently fall back to a write-enabled state;
- document SQLite/data migrations and deployment impact;
- do not add live seller IDs, tokens, cookies or buyer/order payloads to fixtures.

Large refactors of `scheduler.py`, `telegram_bot.py` or `storage.py` should first extract one cohesive responsibility without changing behaviour. Follow-up behaviour changes should be separate PRs.

## Commit and PR content

Describe:

1. the problem;
2. the minimal change;
3. tests performed;
4. marketplace write/runtime risk;
5. migration/deployment impact, if any.

Use the repository pull-request checklist and keep secrets out of logs and screenshots.

## Reporting security issues

See [`SECURITY.md`](SECURITY.md). Do not disclose credential or write-control vulnerabilities in a public issue.
