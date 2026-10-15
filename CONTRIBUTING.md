# Contributing

Contributions are welcome. The project controls real seller accounts, so changes that can reach marketplace write endpoints are treated as safety-sensitive.

## First contribution

Before starting work, check the issue assignees and latest comments so two contributors do not duplicate the same task.

[#42 — sanitized storefront parser regression fixtures](https://github.com/Urushihara24/monitoring-bot/issues/42) is an example of a bounded contributor task, but it is currently assigned and in progress. If no unclaimed issue fits, open a focused issue or proposal first and keep the scope small enough for one reviewable PR.

Good first contributions should normally be:

- credential-free;
- testable offline where possible;
- isolated from marketplace writes;
- narrow enough to review independently;
- explicit about acceptance criteria and runtime risk.

Before starting another substantial refactor, open or reference an issue first. The post-v1 modularization is complete, so maintenance work should improve the active modular boundaries rather than reopen legacy decomposition work.

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
- do not add live seller IDs, tokens, cookies or buyer/order payloads to fixtures;
- target active modular surfaces for new behavior;
- treat `scheduler.py` and `telegram_bot.py` as legacy compatibility/reference surfaces unless a tracked issue explicitly requires changes there;
- keep `storage.py` changes focused on bootstrap/migrations compatibility, with new persistence behavior going through the repository boundaries where possible.

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
