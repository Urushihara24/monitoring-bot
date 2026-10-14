# Changelog

Notable user-facing and operational changes are recorded here. The project follows a lightweight Keep a Changelog style; version tags will be introduced when the runtime/deployment contract is stable enough for releases.

## Unreleased

### Added

- MIT license and public OSS contribution/security guidance.
- Python 3.11/3.12 CI matrix and dependency checks.
- Credential-free pricing simulator.
- Startup preflight for seller/product IDs and safety-sensitive booleans.
- `DRY_RUN` write-safety boundary for seller price updates and marketplace chat auto-replies.
- Explicit startup write-safety banner (`DRY_RUN` vs `WRITES ARMED`).
- Process-wide log redaction for known credentials, auth headers, token query params and structured sensitive fields.
- Structured GitHub issue and pull-request templates.
- Architecture and dry-run safety documentation.

### Changed

- New `.env.example` installations start with `DRY_RUN=true`.
- Package exports are lazy so startup preflight executes before the heavy runtime import graph.

### Security

- Removed personalized seller IDs from the public example configuration.
- Invalid explicit `DRY_RUN` values fail startup rather than falling back to write-enabled behaviour.
- Runtime dependencies identified by `pip-audit` were upgraded to patched versions.
- Issued access tokens are stored in a mode-`0600` ignored file instead of being printed to stdout.
- Logging now redacts configured seller/Telegram secrets and structurally recognizable bearer/query/payload tokens before handlers emit them.
