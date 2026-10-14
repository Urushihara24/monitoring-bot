# DRY_RUN safety contract

`DRY_RUN` is the write-safety boundary for onboarding, diagnostics and production audits.

## Guarantees

With `DRY_RUN=true`:

- competitor reads and pricing decisions still execute;
- seller price update calls are intercepted before the marketplace client write;
- marketplace chat auto-replies are suppressed;
- `scripts/smoke_profiles_api.py --write-probe` and `--mutate` are blocked before marketplace clients are exercised;
- simulated update history is marked with a `dry_run:` reason;
- the simulated price exists only for the current post-update verification path;
- the next pricing cycle reads the real marketplace price again.

The write-safety flag is parsed by the shared `src.write_safety` helper so runtime scheduling and operator smoke tooling use the same fail-closed semantics.

## Non-goals

Dry-run does **not** make the process completely read-only locally. Runtime state, counters and history can still be written to SQLite so operators can inspect what the scheduler would have done.

Do not use a production SQLite database if you require a zero-local-mutation rehearsal. Use a copy of the data directory or the credential-free `scripts/demo_pricing.py` simulator instead.

Authentication/token-refresh utilities may still contact marketplace authentication endpoints. `DRY_RUN` is intended to prevent seller-data writes such as price changes and outbound marketplace chat messages; it is not an offline mode.

## Arming writes

New `.env.example` configurations start with `DRY_RUN=true`.

Set `DRY_RUN=false` only after verifying:

1. account and product IDs;
2. competitor URLs;
3. pricing limits and mode;
4. observed target prices;
5. chat auto-reply permissions/rules if that feature will be used.

Write-capable smoke probes also require `DRY_RUN=false`; this prevents a diagnostic command from bypassing the runtime safety boundary.

Missing `DRY_RUN` preserves the historical write-enabled behaviour for existing deployments. Invalid explicit values fail closed.
