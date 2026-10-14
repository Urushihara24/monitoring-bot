# Stable v1 scope

The stable v1 line focuses on safe marketplace repricing operations rather than feature breadth.

Included:

- GGSEL and DigiSeller profile support;
- competitor monitoring and pricing decisions;
- write-safe onboarding through `DRY_RUN`;
- Telegram operator controls and diagnostics;
- persisted runtime state/history;
- credential-free pricing and fake-marketplace demos;
- root-compatible and non-root Docker deployment paths;
- CI, dependency audit, secret scanning and release guidance.

Deferred to post-v1 architectural work:

- large-module decomposition of scheduler, Telegram UI and storage;
- a dedicated typed settings package replacing import-time environment defaults;
- additional marketplaces;
- distributed/multi-instance coordination.

A post-v1 refactor must preserve the stable pricing/write-safety behaviour and remain covered by contract/regression tests.
