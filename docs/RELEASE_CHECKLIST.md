# Release checklist

Use this checklist before tagging or deploying a revision that can reach seller accounts.

- [ ] CI passes on all supported Python versions.
- [ ] `pytest -q` passes.
- [ ] Critical Ruff and compile checks pass.
- [ ] No live credentials, cookies, seller IDs or buyer/order data are present in the diff.
- [ ] Marketplace write-path changes have focused regression tests.
- [ ] New installations remain `DRY_RUN=true` by default.
- [ ] A dry-run or read-only smoke was performed for integration changes.
- [ ] Pricing limit defaults/migrations were reviewed.
- [ ] SQLite/data migration impact is documented.
- [ ] Docker/runtime permission impact is documented.
- [ ] Rollback steps are known for deployment changes.
- [ ] Changelog entry is present for operator-visible changes.
