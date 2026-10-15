# Changelog

Notable user-facing and operational changes are recorded here. The project follows a lightweight Keep a Changelog style and uses tagged GitHub releases for stable versions.

## Unreleased

## [1.0.1] - 2026-10-15

### Changed

- Upgraded `actions/setup-python` from 6 to 7 and `actions/checkout` from 5 to 7 after full repository verification.
- Upgraded `python-telegram-bot` from 22.7 to 22.8.
- Upgraded `pytest-asyncio` from 1.2.0 to 1.4.0 while retaining `pytest==8.4.2`.
- Upgraded `beautifulsoup4` from 4.12.3 to 4.15.0 with parser/regression coverage passing on Python 3.11 and 3.12.
- Upgraded Ruff from 0.14.0 to 0.17.0; CI continues to use the explicit critical `F,E9` rule selection.
- Dependabot now groups lower-risk development and GitHub Actions minor/patch updates while keeping production/runtime Python dependencies isolated.

### Validation

- Runtime-sensitive dependency updates were merged only after CI, Security and credential-free Demo runtime checks passed.
- Pricing formulas, marketplace write semantics, `DRY_RUN`, persisted-state meaning and deployment defaults are unchanged from v1.0.0.

## [1.0.0] - 2026-10-15

### Added

- MIT license and public OSS contribution/security guidance.
- Python 3.11/3.12 CI matrix and dependency checks.
- Credential-free pricing simulator.
- Typed, fail-closed environment schema for IDs, booleans, numeric safety settings, pricing modes, chat policies and logging settings.
- Cross-field startup validation for price and fast-check ranges.
- `DRY_RUN` write-safety boundary for seller price updates and marketplace chat auto-replies.
- Explicit startup write-safety banner (`DRY_RUN` vs `WRITES ARMED`).
- Process-wide log redaction for known credentials, auth headers, token query params and structured sensitive fields.
- Image-level Docker healthcheck and explicit `SIGTERM` stop signal.
- Optional `runtime-nonroot` image target and `docker-compose.secure.yml` using named volumes.
- CI verification for both container targets, healthcheck metadata and non-root volume writes.
- Structured GitHub issue and pull-request templates.
- Architecture and dry-run safety documentation.

### Changed

- Configuration is loaded through an explicit `Config(env)` / `load_config()` snapshot instead of evaluating `os.getenv()` expressions at class-definition time.
- DigiSeller profile defaults consume the typed config snapshot and no longer re-read/process environment values independently.
- Invalid booleans, fractional integer settings, malformed ID lists, NaN/infinite numbers, unknown pricing modes/policies and inverted ranges fail closed instead of being silently coerced or ignored.
- New `.env.example` installations start with `DRY_RUN=true`.
- Package exports are lazy so startup preflight executes before the heavy runtime import graph.
- Compose enables an init process and a 20-second graceful stop window.
- Existing bind-mount deployments explicitly keep the backward-compatible root image target; non-root migration is opt-in.

### Security

- Removed personalized seller IDs from the public example configuration and removed the legacy hidden `GGSEL_SELLER_ID=8175` code fallback.
- Invalid explicit `DRY_RUN` values fail startup rather than falling back to write-enabled behaviour.
- Runtime dependencies identified by `pip-audit` were upgraded to patched versions.
- Issued access tokens are stored in a mode-`0600` ignored file instead of being printed to stdout.
- Logging now redacts configured seller/Telegram secrets and structurally recognizable bearer/query/payload tokens before handlers emit them.

[1.0.1]: https://github.com/Urushihara24/monitoring-bot/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Urushihara24/monitoring-bot/releases/tag/v1.0.0
