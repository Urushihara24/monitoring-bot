# v1 release readiness

The repository is considered ready for a stable v1 release when the following conditions hold on `main`.

## Safety

- `DRY_RUN=true` is the default for new installations.
- Invalid safety values fail closed before the application import graph starts.
- Seller price writes, marketplace chat auto-replies and write-capable smoke probes are blocked in dry-run mode.
- Known credentials/tokens are redacted from runtime logs.
- Public examples and tracked fixtures contain no live credentials or seller IDs.

## Verification

- Python 3.11 and 3.12 CI are green.
- Dependency audit and tracked-secret scan are green.
- Root-compatible and non-root container targets build successfully.
- The credential-free fake marketplace demo runs in CI with zero network calls and zero real writes.
- Docker Compose lifecycle verification starts a credential-free process in the production runtime image, sends SIGTERM through `docker compose stop`, and verifies graceful completion inside the documented stop window.

## Operability

- Startup clearly reports whether writes are armed.
- Docker images expose a healthcheck and explicit SIGTERM behaviour.
- A backward-compatible deployment path and an opt-in non-root path are documented.
- Release, security and contribution procedures are documented.

## Contributor experience

A contributor can clone the repository, install development dependencies, run tests, run a multi-cycle pricing demo without credentials, understand the write boundary, and propose a focused change without access to a seller account.

## Post-v1 architecture status

The post-v1 behaviour-preserving modularization tracked in #24 is complete:

- configuration uses an explicit typed settings loader with fail-closed startup semantics;
- active scheduler orchestration is split across parser coordination, notification policy, chat auto-reply orchestration and pricing-cycle coordination;
- the active scheduler inherits from a fail-closed runtime host, so extracted responsibilities cannot silently fall back to legacy orchestration bodies;
- Telegram routing, keyboard/views, settings mutations and status/diagnostics rendering are separated behind modular runtime facades;
- active persistence uses focused pricing-state, runtime-settings, chat-metadata and history repositories while retaining SQLite migration compatibility;
- the production container lifecycle is covered by a Compose SIGTERM end-to-end check.

The historical monolithic scheduler/Telegram/storage surfaces remain only where compatibility and regression coverage require them; new runtime work should target the modular boundaries.
