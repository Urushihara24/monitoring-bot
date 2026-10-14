# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for vulnerabilities that could expose seller credentials, Telegram bot tokens, marketplace access tokens, cookies, buyer/order data or enable unintended marketplace writes.

Use a private GitHub security advisory for this repository when available, or contact the maintainer through the contact method listed on the GitHub profile.

Include only the minimum information required to reproduce the issue. Redact secrets and personal/order data from logs, screenshots and payloads.

## Supported code

Security fixes target the current `main` branch. Marketplace APIs are external dependencies and can change independently of this project.

## High-risk areas

Changes in these areas require explicit tests and review of write behaviour:

- seller price update endpoints;
- marketplace chat send endpoints;
- authentication/token refresh;
- cookies and anti-bot handling;
- SQLite migrations and runtime state;
- deployment/container permissions;
- `DRY_RUN` and startup safety checks.

## Secret handling

Never commit real values for:

- `TELEGRAM_BOT_TOKEN`;
- `GGSEL_API_KEY`, `GGSEL_API_SECRET`, `GGSEL_ACCESS_TOKEN`;
- `DIGISELLER_API_KEY`, `DIGISELLER_API_SECRET`, `DIGISELLER_ACCESS_TOKEN`;
- marketplace cookies;
- private order/chat payloads containing buyer information.

Use `.env` locally and keep `.env.example` credential-free. Rotate any secret immediately if it is accidentally committed or shared.

The Python package installs a process-wide log redaction layer before runtime modules are imported. It removes configured secret values and structurally recognizable bearer tokens, token query parameters and sensitive structured fields from normal log records and exception text. This is defense in depth, not permission to log raw secrets deliberately: new code should still avoid constructing logs that contain credentials or private buyer/order payloads.

## Safe reproduction

Prefer, in order:

1. `scripts/demo_pricing.py` for pricing-only reproduction;
2. `DRY_RUN=true` for end-to-end scheduler diagnostics without marketplace writes;
3. sanitized read-only smoke checks;
4. mutation/rollback probes only on accounts/products you control and only when the risk is understood.
