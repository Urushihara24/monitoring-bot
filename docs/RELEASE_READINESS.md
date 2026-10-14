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

## Operability

- Startup clearly reports whether writes are armed.
- Docker images expose a healthcheck and explicit SIGTERM behaviour.
- A backward-compatible deployment path and an opt-in non-root path are documented.
- Release, security and contribution procedures are documented.

## Contributor experience

A contributor can clone the repository, install development dependencies, run tests, run a multi-cycle pricing demo without credentials, understand the write boundary, and propose a focused change without access to a seller account.

## Non-blocking post-v1 architecture work

The following improvements are valuable but do not block safe v1 usage because current behaviour is covered by tests and explicit write boundaries:

- split `scheduler.py` into cohesive orchestration components;
- split `telegram_bot.py` into handlers/views/settings/diagnostics;
- split `storage.py` into focused repositories;
- migrate import-time environment parsing to a dedicated typed settings loader.

These should be delivered as behaviour-preserving extraction PRs before further feature growth.
