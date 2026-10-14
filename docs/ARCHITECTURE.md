# Architecture

## Runtime flow

```text
marketplace/storefront reads
          |
          v
 competitor parser
          |
          v
   pricing decision
          |
          v
  safety constraints
          |
          v
 scheduler write boundary ---- DRY_RUN ----> simulated result
          |                                  (no marketplace write)
          v
 marketplace client
          |
          v
 seller price / chat API
```

SQLite stores runtime configuration, product/profile state, price history and alert/deduplication metadata. Telegram is the operator interface; it is not the source of truth for pricing calculations.

## Marketplace contract

`src/marketplace.py` defines the shared `MarketplaceClient` protocol used to describe the core pricing surface: API availability, product reads, current-price reads and price updates. GGSEL and DigiSeller implement this surface structurally while retaining their marketplace-specific helpers.

The same module includes `FakeMarketplaceClient`, an in-memory implementation used by `scripts/demo_runtime.py` and contract tests. It performs no network I/O and lets contributors exercise multiple real pricing decisions without credentials or a seller account.

## Primary modules

- `src/main.py` — startup, profile construction, lifecycle and scheduler management.
- `src/scheduler.py` — orchestration of parsing, pricing, state and notifications.
- `src/scheduler_factory.py` — selects the production scheduler or the write-safe dry-run adapter.
- `src/logic.py` — pure pricing decision logic.
- `src/marketplace.py` — shared marketplace protocol plus the in-memory fake client.
- `src/rsc_parser.py` — competitor/storefront parsing.
- `src/api_client.py` — GGSEL seller API client.
- `src/digiseller_client.py` — DigiSeller API client.
- `src/storage.py` — SQLite-backed state/history/runtime settings.
- `src/telegram_bot.py` — Telegram commands, settings UI and diagnostics.

## Safety boundaries

External writes currently occur through two scheduler-controlled behaviours:

1. seller price updates;
2. marketplace chat auto-replies.

`DRY_RUN=true` replaces the runtime scheduler with `DryRunScheduler`, which blocks both behaviours while delegating normal reads and pricing logic to the production scheduler.

Startup configuration is validated by `src/preflight.py` before the heavy runtime graph is imported. `src/__init__.py` uses lazy exports specifically so package import cannot bypass this ordering.

The fake marketplace runtime is a separate contributor tool. It never instantiates a network-backed marketplace client and reports zero network calls / zero real writes in its machine-readable output.

## State model

State is scoped by marketplace/profile and, where applicable, product runtime profile IDs. New product pairs start disabled and require explicit operator activation. Pricing safety parameters are loaded into runtime configuration and validated before a pricing cycle can perform a write.

## Refactoring direction

The original project grew from a small Telegram bot into a long-running integration service. The largest remaining architectural debt is concentrated in `scheduler.py`, `telegram_bot.py` and `storage.py`.

Refactors should extract cohesive components without changing marketplace behaviour first. Target seams:

- scheduler: parser coordination, pricing-cycle orchestration, chat auto-reply, notification policy;
- Telegram: command routing, keyboards/views, settings flows, diagnostics;
- storage: pricing state, runtime settings, chat metadata and history repositories.

The shared marketplace protocol and contract tests now provide a stable seam for future client refactors.

Behaviour changes should follow extraction in separate PRs so write-path regressions remain reviewable.
