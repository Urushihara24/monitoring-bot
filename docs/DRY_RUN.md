# DRY_RUN safety contract

`DRY_RUN` is the write-safety boundary for onboarding, diagnostics and production audits.

## Guarantees

With `DRY_RUN=true`:

- competitor reads and pricing decisions still execute;
- seller price update calls are intercepted before the marketplace client write;
- marketplace chat auto-replies are suppressed;
- simulated update history is marked with a `dry_run:` reason;
- the simulated price exists only for the current post-update verification path;
- the next pricing cycle reads the real marketplace price again.

## Non-goals

Dry-run does **not** make the process completely read-only locally. Runtime state, counters and history can still be written to SQLite so operators can inspect what the scheduler would have done.

Do not use a production SQLite database if you require a zero-local-mutation rehearsal. Use a copy of the data directory or the credential-free `scripts/demo_pricing.py` simulator instead.

## Arming writes

New `.env.example` configurations start with `DRY_RUN=true`.

Set `DRY_RUN=false` only after verifying:

1. account and product IDs;
2. competitor URLs;
3. pricing limits and mode;
4. observed target prices;
5. chat auto-reply permissions/rules if that feature will be used.

Missing `DRY_RUN` preserves the historical write-enabled behaviour for existing deployments. Invalid explicit values fail startup.
