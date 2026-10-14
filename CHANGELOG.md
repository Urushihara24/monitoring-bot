# Changelog

Notable user-facing and operational changes are recorded here. The project follows a lightweight Keep a Changelog style; version tags will be introduced when the runtime/deployment contract is stable enough for releases.

## Unreleased

### Added

- MIT license and public OSS contribution/security guidance.
- Python 3.11/3.12 CI matrix and dependency checks.
- Credential-free pricing simulator.
- Startup preflight for seller/product IDs and safety-sensitive booleans.
- `DRY_RUN` write-safety boundary for seller price updates and marketplace chat auto-replies.
- Structured GitHub issue and pull-request templates.
- Architecture and dry-run safety documentation.

### Changed

- New `.env.example` installations start with `DRY_RUN=true`.
- Package exports are lazy so startup preflight executes before the heavy runtime import graph.

### Security

- Removed personalized seller IDs from the public example configuration.
- Invalid explicit `DRY_RUN` values fail startup rather than falling back to write-enabled behaviour.
