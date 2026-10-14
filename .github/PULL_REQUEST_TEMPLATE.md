## Summary

<!-- What changed and why? -->

## Verification

- [ ] `pytest -q`
- [ ] `ruff check src tests scripts --select F,E9`
- [ ] `python -m compileall -q src scripts healthcheck.py`
- [ ] No live credentials, seller IDs or tokens added
- [ ] Marketplace write behaviour is unchanged, or the change is explicitly documented and tested
- [ ] Production deployment/migration impact is documented when applicable

## Risk

<!-- Describe runtime, data, API-write or migration risk. Use "none" only when genuinely none. -->
