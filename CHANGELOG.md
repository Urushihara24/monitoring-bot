# Changelog

Notable user-facing and operational changes are recorded here. The project follows a lightweight Keep a Changelog style; version tags will be introduced when the runtime/deployment contract is stable enough for releases.

## Unreleased

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
