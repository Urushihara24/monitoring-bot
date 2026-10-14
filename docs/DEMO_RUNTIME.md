# Credential-free fake marketplace runtime

The project includes two no-credential developer entry points:

- `scripts/demo_pricing.py` — one pricing decision;
- `scripts/demo_runtime.py` — several pricing cycles against an in-memory marketplace client.

## Why it exists

Contributors should be able to understand and exercise the pricing core without:

- creating a Telegram bot;
- owning a GGSEL or DigiSeller account;
- placing real seller credentials in `.env`;
- sending marketplace writes;
- relying on an external network connection.

## Run

```bash
python3 scripts/demo_runtime.py
```

Custom sequence:

```bash
python3 scripts/demo_runtime.py \
  --mode DUMPING \
  --competitors 0.35 0.37 0.34 \
  --current 0.36
```

JSON output:

```bash
python3 scripts/demo_runtime.py --format json
```

The JSON payload explicitly reports:

```json
{
  "network_calls": 0,
  "real_marketplace_writes": 0
}
```

Updates are applied only to the process-local `FakeMarketplaceClient` instance.

## Contract seam

`src/marketplace.py` exposes `MarketplaceClient`, a runtime-checkable protocol describing the shared pricing surface implemented by both production marketplace clients and the fake client.

This keeps demos and future orchestration refactors coupled to a small contract instead of GGSEL/DigiSeller implementation details.
