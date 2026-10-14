# Operations reference

Detailed runtime and operator notes for the GGSEL + DigiSeller auto-pricing bot.

## Profiles

Supported profiles:

- `ggsel`
- `digiseller`

Each profile stores its own credentials, primary/active product, tracked products, competitor URLs, runtime settings, state, history and alerts.

## Typical Telegram workflow

1. Select a marketplace from `🧩 Профиль`.
2. Open `📦 Товары`.
3. Add a product and competitor URL: `<product_id> <competitor_url>`.
4. Open `⚙ Настройки` and verify the active product.
5. Enable `🔔 Автоцена`.
6. Select `Следование`, `Демпинг` or `Повышение`.
7. Configure minimum/maximum price, price-change step and rounding as needed.
8. Use `📊 Статус` to verify the parsed competitor price and active settings.

The Telegram UI is currently Russian.

## Pricing modes

### Follow

Use the competitor price directly with 4-decimal precision.

### Undercut

The current rule starts from the competitor storefront price rounded to two decimals and subtracts the configured undercut value.

### Raise

The current rule starts from the competitor storefront price rounded to two decimals and adds the configured raise value.

## Safety controls

The runtime includes controls for:

- minimum and maximum prices;
- maximum downward step;
- cooldowns and fast upward rebound;
- position/weak-signal filtering;
- idempotent updates;
- safe skips when the target price is already applied;
- safe skips when no competitor is configured;
- per-product isolation of pricing settings.

## Competitor parsing pipeline

GGSEL parsing uses a fallback chain:

1. HTML request;
2. unit-price extraction when available;
3. CSS price selectors;
4. GGSEL public product endpoint fallback for supported domains.

Runtime state records the last parsed competitor price, URL, parsing method, timestamp and parsing errors/blocking reasons.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
```

Minimum environment configuration includes:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_IDS`
- seller credentials for every enabled profile
- seller/product identifiers
- competitor URL configuration when automatic monitoring is required

When a seller API key is a JWT access token, configure the corresponding API secret when token refresh through `ApiLogin` is required.

## Run locally

```bash
python3 -m src
```

## Docker

```bash
docker compose up -d --build
docker compose logs -f
```

See [`DEPLOY.md`](DEPLOY.md) for deployment notes.

## Telegram commands

- `/start`
- `/status`
- `/status <profile>`
- `/diag`
- `/diag <profile>`
- `/smoke`
- `/smoke <profile>`

Accepted profile aliases include `gg`/`ggsel` and `digi`/`dg`/`digiseller`/`plati`.

## Multiple products

A profile can monitor multiple products. Every product has its own competitor list and pricing/runtime settings. The active product only determines which product is currently edited through Telegram; monitoring can continue for all configured products.

## Automatic order instructions

GGSEL and DigiSeller profiles can optionally send product instructions to order chats when the relevant seller API permissions are available.

Controls include:

- enable/disable per profile;
- product allow-list;
- empty-chat-only mode;
- message-history deduplication;
- per-option rules;
- product-card instruction fallback;
- configurable cleanup/retention for sent-state records.

Keep this feature disabled until seller chat permissions and product instruction data have been verified for the target account.

## Smoke scripts

Check active seller profiles:

```bash
python3 scripts/smoke_profiles_api.py
```

Read-only verification:

```bash
python3 scripts/smoke_profiles_api.py --profile all --verify-read
```

DigiSeller-only verification:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --verify-read
```

Optional mutation-and-rollback probe:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --mutate --delta 0.0001 --verify-read
```

Chat permission smoke without sending a message:

```bash
python3 scripts/smoke_chat_api.py --profile all
```

Instruction-data availability smoke:

```bash
python3 scripts/smoke_instruction_data.py --profile all
```

## Tests and static checks

```bash
pytest -q
python3 -m compileall src scripts healthcheck.py
```

## Code map

- `src/main.py` — profile startup and orchestration
- `src/scheduler.py` — parse → calculate → update/skip cycle
- `src/logic.py` — pricing rules
- `src/rsc_parser.py` — competitor parser
- `src/api_client.py` — GGSEL seller API
- `src/digiseller_client.py` — DigiSeller API
- `src/telegram_bot.py` — Telegram UI and handlers
- `src/storage.py` — SQLite runtime state/history/alerts

## External API references

- GGSEL Seller API: `https://seller.ggsel.com/docs/seller-api-v-1`
- DigiSeller API: `https://my.digiseller.com/inside/api.asp`

For a non-technical setup flow, see [`INSTRUCTION_CUSTOMER.md`](INSTRUCTION_CUSTOMER.md).
