# Auto-Pricing Bot (GGSEL + DigiSeller)

Telegram bot for competitor-price monitoring and automatic product-price updates through seller APIs.

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![SQLite](https://img.shields.io/badge/SQLite-State-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![pytest](https://img.shields.io/badge/pytest-Tested-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-CI-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)

</div>

| Engineering focus | Reliability controls | Verification |
|---|---|---|
| Independent GGSEL and DigiSeller profiles, competitor parsing and price automation | Price floors, rate limits, cooldowns, idempotent updates and safe parser fallbacks | Docker deployment, GitHub Actions and a pytest suite covering core behavior |

**Start here:** [customer guide](INSTRUCTION_CUSTOMER.md) · [deployment](DEPLOY.md) · [tests](tests/) · [source](src/)

A simplified customer guide without technical terminology is available here:
- [`INSTRUCTION_CUSTOMER.md`](INSTRUCTION_CUSTOMER.md)

Independent profiles are supported:
- `ggsel`
- `digiseller`

Each profile stores its own:
- API keys / access token
- primary product ID
- tracked-product list (`tracked_products`)
- competitor list
- runtime settings
- state / history / alerts

## Typical customer workflow

1. In the bot, press `🧩 Профиль` and select a marketplace (`GGSEL` or `DIGISELLER`).
2. Press `📦 Товары`.
3. Add a product and competitor in one line:
   - `<product_id> <competitor_url>`
   - example: `4697439 https://ggsel.net/catalog/product/102124601`
4. Press `⚙ Настройки` and verify that the correct `Активный товар` is shown.
5. Enable `🔔 Автоцена`.
6. Select a mode:
   - `Следование` — match the competitor price.
   - `Демпинг` — price slightly below the competitor.
   - `Повышение` — price slightly above the competitor.
7. Configure the main limits if needed:
   - `📉 Мин` — minimum price.
   - `📈 Макс` — maximum price.
   - `↘️ Шаг-` and `↗️ Шаг+` — price-change step.
   - `🔘 Округление` — rounding step, for example `0.01` or `0.0001`.
8. Open `📊 Статус` and verify that:
   - the competitor URL is correct;
   - the competitor price is parsed;
   - the mode and limits match the intended configuration.

> The Telegram UI is currently Russian, so button labels are kept exactly as they appear in the bot.

Important:
- All settings apply only to the active product, meaning the current product↔competitor pair.
- Switching products with `⬅/➡` changes only the product being edited, not the profile.
- Keep automatic order instructions disabled until that feature is being tested separately.

## Core pricing logic

Base pricing rule:
- `my_price = competitor_min - UNDERCUT_VALUE`
- default `UNDERCUT_VALUE=0.0051`
- example: competitor `0.3400` -> our price `0.3349`

Safety limits and controls:
- `MIN_PRICE`, `MAX_PRICE`
- `MODE=FOLLOW|DUMPING|RAISE`
- `FOLLOW`: set exactly the competitor price, 4 decimal places
- `DUMPING`: `round(competitor, 2) - 0.0051`
- `RAISE`: `round(competitor, 2) + 0.0049`
- `MAX_DOWN_STEP` limits sudden downward moves
- `FAST_REBOUND_DELTA` + cooldown bypass allows a fast upward rebound
- when `POSITION_FILTER_ENABLED=true` and `rank=N/A`, the
  `WEAK_UNKNOWN_RANK_*` heuristic uses the absolute/relative gap between the first and second prices
  to avoid undercutting a weak competitor signal

Idempotent updates:
- when the competitor price has not changed, no duplicate API update is sent;
- if the target price was already applied, the bot performs a safe `skip` without extra noise;
- if a profile has an empty competitor list, the cycle performs a safe `skip` without error alerts;
- a profile can operate without `COMPETITOR_URLS` for manual operations and API smoke checks.

Price precision:
- calculation, storage and Telegram display use `4` decimal places;
- GGSEL update payloads send prices in `0.0000` format;
- marketplace read APIs may return rounded values, and the logic accounts for that behavior.

## Competitor parsing pipeline

Pipeline:
1. `stealth_requests` + HTML (`BeautifulSoup`)
2. unit-price extraction (`unitsToPay / unitsToGet`) when available
3. fallback to CSS price selectors
4. fallback to the public endpoint `https://api4.ggsel.com/goods/<id>`
   for `ggsel.*` domains only

Stored state includes:
- `last_competitor_min`
- `last_competitor_url`
- `last_competitor_method`
- `last_competitor_parse_at`
- parser errors / blocking reasons

Cookie behavior:
- the bot reloads cookies from `.env` on every cycle without a restart;
- if cookies expire and parsing succeeds without them, runtime cookies are cleared automatically to avoid repeating a broken request;
- if the retry without cookies also fails, stale runtime cookies are reset so the next cycle does not stay stuck on the same `401/403` state;
- the env-file path can be overridden with `ENV_FILE_PATH`.

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
# runtime dependencies
pip install -r requirements.txt
# test/lint dependencies
pip install -r requirements-dev.txt
cp .env.example .env
```

Minimum `.env` configuration:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_IDS`
- for each enabled profile: `*_API_KEY`/`*_ACCESS_TOKEN`, `*_SELLER_ID`, `*_PRODUCT_ID`
- if `*_API_KEY` is a JWT access token, configure `*_API_SECRET` for `ApiLogin` token refresh
- `GGSEL_COMPETITOR_URLS` and/or `DIGISELLER_COMPETITOR_URLS`
  - GGSEL falls back to `COMPETITOR_URLS` for backward compatibility
- competitor cookies: `GGSEL_COMPETITOR_COOKIES` / `DIGISELLER_COMPETITOR_COOKIES`
  - if profile-specific values are absent, the shared `COMPETITOR_COOKIES` value is used
- for non-standard deployments, `ENV_FILE_PATH` can be set explicitly

If an enabled profile has no `*_PRODUCT_ID`, that profile does not start. This is a fail-safe against noisy empty loops and meaningless API updates.

Optional DigiSeller profile defaults:
- `DIGISELLER_MIN_PRICE`
- `DIGISELLER_MAX_PRICE`
- `DIGISELLER_DESIRED_PRICE`
- `DIGISELLER_UNDERCUT_VALUE`
- `DIGISELLER_MODE`
- `DIGISELLER_WEAK_PRICE_CEIL_LIMIT`
- `DIGISELLER_POSITION_FILTER_ENABLED`
- `DIGISELLER_WEAK_POSITION_THRESHOLD`
- `DIGISELLER_WEAK_UNKNOWN_RANK_ENABLED`
- `DIGISELLER_WEAK_UNKNOWN_RANK_ABS_GAP`
- `DIGISELLER_WEAK_UNKNOWN_RANK_REL_GAP`
- `DIGISELLER_CHECK_INTERVAL`
- `DIGISELLER_FAST_CHECK_INTERVAL_MIN`
- `DIGISELLER_FAST_CHECK_INTERVAL_MAX`
- `DIGISELLER_COOLDOWN_SECONDS`
- `DIGISELLER_IGNORE_DELTA`
- `DIGISELLER_NOTIFY_SKIP`
- `DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS`
- `DIGISELLER_NOTIFY_COMPETITOR_CHANGE`
- `DIGISELLER_COMPETITOR_CHANGE_DELTA`
- `DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS`
- `DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE`
- `DIGISELLER_NOTIFY_PARSER_ISSUES`
- `DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS`
- `DIGISELLER_HARD_FLOOR_ENABLED`
- `DIGISELLER_MAX_DOWN_STEP`
- `DIGISELLER_FAST_REBOUND_DELTA`
- `DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN`

These defaults are applied only when the corresponding runtime key has not already been stored in the database (`runtime_settings`).

Global Telegram error-notification flag:
- `NOTIFY_ERRORS=false` — do not send `❌ Ошибка` notifications to Telegram; write them only to server logs.

### Enabling the DigiSeller profile

Minimum variables:
- `DIGISELLER_ENABLED=true`
- `DIGISELLER_API_KEY` or `DIGISELLER_ACCESS_TOKEN`
- `DIGISELLER_API_SECRET` if `DIGISELLER_API_KEY` stores a JWT
- `DIGISELLER_SELLER_ID`
- `DIGISELLER_PRODUCT_ID`

Recommended values:
- `DIGISELLER_COMPETITOR_URLS` when automatic competitor monitoring is required
- `DIGISELLER_REQUIRE_API_ON_START=true` to prevent startup with invalid API access

Optional order-chat auto-instruction settings for DigiSeller:
- `DIGISELLER_CHAT_AUTOREPLY_ENABLED=true`
- `DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS=5077639,5104800`
- `DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS=30`
- `DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES=true`
- `DIGISELLER_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT=true`
- `DIGISELLER_CHAT_AUTOREPLY_REQUIRE_RULES=true`
- `DIGISELLER_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT=false`
- `DIGISELLER_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK=false`
- `DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES=30`
- `DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS=30`
- `DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS=24`
- `DIGISELLER_CHAT_TEMPLATE_RU_ALREADY`, `DIGISELLER_CHAT_TEMPLATE_RU_ADD`
- `DIGISELLER_CHAT_TEMPLATE_EN_ALREADY`, `DIGISELLER_CHAT_TEMPLATE_EN_ADD`

If templates are not configured, the bot reads text from product fields:
- RU: `info_ru`/`instruction_ru`/`add_info_ru`, falling back to `info`/`instruction`/`add_info`
- EN: `info_en`/`instruction_en`/`add_info_en`, falling back to `info`/`instruction`/`add_info`

For the `add` mode, `add_info*` has priority; otherwise `info*` is preferred.
An instruction is processed independently for every new order (`order_id`).
For the same order, the bot sends the instruction only once using `order_id` anti-duplication plus text deduplication against message history.
If `*_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT=true`, instructions are sent only to an empty order chat.
Before sending, the bot checks chat API permissions; insufficient permissions skip sending and record the reason in `/diag` under `Chat perms`.
When `*_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT=false`, custom rule text is ignored and only product-card instruction text for the selected option is used.
When `*_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK=false`, fallback template messages are not used.
If the selected order option/variant has its own instruction text, that text takes priority over the generic `info/add_info` text.
If the selected option has no text, sending is skipped and the reason is logged.
The same behavior applies to DigiSeller and GGSEL when `*_CHAT_AUTOREPLY_ENABLED` is enabled.

Equivalent GGSEL settings are also available:
- `GGSEL_CHAT_AUTOREPLY_ENABLED`
- `GGSEL_CHAT_AUTOREPLY_PRODUCT_IDS`
- `GGSEL_CHAT_AUTOREPLY_INTERVAL_SECONDS`
- `GGSEL_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES`
- `GGSEL_CHAT_AUTOREPLY_ONLY_EMPTY_CHAT`
- `GGSEL_CHAT_AUTOREPLY_REQUIRE_RULES`
- `GGSEL_CHAT_AUTOREPLY_ALLOW_CUSTOM_TEXT`
- `GGSEL_CHAT_AUTOREPLY_ALLOW_TEMPLATE_FALLBACK`
- `GGSEL_CHAT_AUTOREPLY_LOOKBACK_MESSAGES`
- `GGSEL_CHAT_AUTOREPLY_SENT_TTL_DAYS`
- `GGSEL_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS`
- `GGSEL_CHAT_TEMPLATE_RU_ALREADY`, `GGSEL_CHAT_TEMPLATE_RU_ADD`
- `GGSEL_CHAT_TEMPLATE_EN_ALREADY`, `GGSEL_CHAT_TEMPLATE_EN_ADD`

Quick DigiSeller-only verification:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --verify-read
```

Run the application:

```bash
python3 -m src
```

## Docker

```bash
docker compose up -d --build
docker compose logs -f
```

## Telegram controls (reply keyboard)

Commands:
- `/start`
- `/status` — status of the active profile
- `/status <profile>` — status of the selected profile
- `/diag` — diagnostics for the active profile
- `/diag <profile>` — diagnostics for the selected profile
- `/smoke` — safe API smoke check for the active profile: read + no-op write + verify
  - DigiSeller also reports `token/perms`
  - optional profile argument: `/smoke ggsel` or `/smoke digiseller`

Profile aliases accepted in command arguments:
- GGSEL: `gg`, `ggsel`
- DigiSeller: `digi`, `dg`, `digiseller`, `plati`

### Main menu
- `📊 Статус`
- `📦 Товары`
- `⬅ Пред. товар` / `➡ След. товар`
- `🧩 Профиль`
- `⚙ Настройки`

UX notes:
- `⬅/➡` only switches the **active product being managed** and keeps the user on the main menu;
- this reduces accidental clicks and unintended manual price changes;
- switching profiles automatically clears any unfinished pending action.

### Managing products
The `📦 Товары` button opens product input:
- send `product_id` — add/select a product;
- send `list` — show the profile's product list;
- send `<product_id> <competitor_url>` — add/select a product and bind the competitor URL in one step;
- assign a readable name with `name <product_id|active> <name>`;
- clear the custom name with `clearname <product_id|active>`.

Examples:
- `4697439`
- `4697439 https://ggsel.net/catalog/product/102124601`
- `name active Gift skins`

### Multiple-product behavior
- one profile can monitor multiple products simultaneously;
- every product has its own competitor-URL list;
- the bot monitors **all products in the list**;
- the list displays `ID + name` when a name is available from the product card or has been set manually;
- `active product` identifies which product's pricing mode, automation and limits are being edited;
- `📊 Статус` shows:
  - active product;
  - active position in the list (`1/N`);
  - key prices: current / bot-set / competitor;
  - current URL / parsing method / last parse timestamp.

### Settings (`⚙ Настройки`)
Available controls:
- `🔔 Авто: ВКЛ/ВЫКЛ` — active product only
- `🎯 Цена`
- `🔀 Режим`
- `📦 Товары` — add/select a product and bind a competitor URL
- `🗑 Удалить товар` — remove one product (`active`/`id`) or all products (`all`)
- `💬 Инструкции: ВКЛ/ВЫКЛ` — when the profile supports chat API
- `📭/📨 Только пустой чат` — send automatic instructions only into an empty chat
- `📝 Правила инстр.` — per-option instruction rules

### Pricing modes in plain language
- `Следование` (Follow):
  set exactly the competitor price with 4 decimal places, for example `0.3560 -> 0.3560`.
- `Демпинг` (Undercut):
  start from the competitor storefront price rounded to 2 decimals:
  `round(competitor, 2) - 0.0051`, for example `0.35 -> 0.3449`.
- `Повышение` (Raise):
  also starts from the 2-decimal storefront price:
  `round(competitor, 2) + 0.0049`, for example `0.35 -> 0.3549`.

Important:
- pricing strategies, automation and limits are isolated per product inside each profile;
- settings from one product are never copied to another automatically;
- after adding/removing products through Telegram, the new scheduler set is applied after the process/container restarts.

### Automatic-instruction rules by product option
- Open `⚙ Настройки` -> `📝 Правила инстр.`.
- The bot displays the available product-option variants.
- If at least one rule is enabled, instructions are sent only for matching enabled rules.
- Enable/disable, reset and exit actions are available as buttons below the rules message.
- Custom text is optional; without it, the bot reads instruction text from the product card.
- Optional text commands:
  - `text <N> <text>` — set custom text for a variant;
  - `clear <N>` — remove custom text and fall back to the product-card instruction;
  - `done` — exit the editor.

## Utility scripts

Check GGSEL `apilogin` using `GGSEL_API_SECRET`, with fallback to `GGSEL_API_KEY`:

```bash
python3 scripts/check_apilogin.py
```

If `GGSEL_API_KEY` is a JWT access token, configure `GGSEL_API_SECRET`; otherwise `apilogin` is unavailable.

Issue an access token through `apilogin`:

```bash
python3 scripts/issue_access_token.py
```

Smoke-check active profiles:

```bash
python3 scripts/smoke_profiles_api.py
```

Read-only smoke without a write probe:

```bash
python3 scripts/smoke_profiles_api.py --profile all --verify-read
```

DigiSeller only:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller
```

If a profile is explicitly requested with `--profile ggsel|digiseller` but disabled in `.env`, the script exits with code `1`.

Smoke with a real test mutation and rollback:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --mutate --delta 0.0001 --verify-read
```

Order-chat permission smoke without sending messages:

```bash
python3 scripts/smoke_chat_api.py --profile all
```

Safe `chat.send` POST probe using `id_i=0`:

```bash
python3 scripts/smoke_chat_api.py --profile digiseller --send-probe
```

Instruction-text availability smoke without sending messages:

```bash
python3 scripts/smoke_instruction_data.py --profile all
```

## Tests and checks

```bash
pytest -q
python3 -m compileall src scripts healthcheck.py
```

On Python 3.14+, use the versions pinned in `requirements-dev.txt` (`pytest==8.4.2`, `pytest-asyncio==1.2.0`) to avoid deprecated warnings from older `pytest-asyncio` releases.

## Code structure

- `src/main.py` — profile startup and orchestration
- `src/scheduler.py` — parse -> calculate -> update/skip cycle
- `src/logic.py` — pricing business rules
- `src/rsc_parser.py` — competitor parser
- `src/api_client.py` — GGSEL API client
- `src/digiseller_client.py` — DigiSeller API client
- `src/telegram_bot.py` — Telegram reply UI and handlers
- `src/storage.py` — SQLite state/runtime/history/alerts

## API sources

- GGSEL Seller API: `https://seller.ggsel.com/docs/seller-api-v-1`
- DigiSeller API: `https://my.digiseller.com/inside/api.asp`
