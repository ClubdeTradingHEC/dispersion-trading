# Source-delivery verification

The delivery was checked on Windows with Python 3.12.15. The retained dependency
lock preserves pandas 2.1.4 and SQLAlchemy 1.4.54. GitHub Linux CI is configured;
its hosted execution is NOT RUN until the branch is pushed.

| Check | Status | Evidence |
|---|---|---|
| Offline unit suite | PASS | 160 tests; no failures/errors/skips |
| New maintained SPX export | PASS | Both real five/seven-year CSVs exactly match the corrected saved exports; n, mean, HAC SE and confidence intervals agree within 1e-12 |
| New DJIA stage/preparation | PASS | Real IC, past/future RC, counts and label dates preserved; prepared features and A/B eligibility match the existing dataset (3,665 rows, 3,414 eligible) |
| Kevin-derived files | PASS | All 39 working files and staged Git blobs match the delivery starting bytes |
| Credential check | PASS | Known local password compared without disclosure against source files and reachable Git blobs; no matches |
| Dependency installation | PASS | All 32 locked packages installed into a separate disposable environment; dependency declarations and lock preserved |
| Clean exported-folder test | PASS | Installed from the source-only candidate into the separate environment; offline CLI passes all 160 tests and imports resolve inside the export, with no original data or environment |
| New live WRDS queries | NOT RUN | This handoff performs no acquisition; new membership acquisition is budgeted and requires separate explicit execution |
| Full historical model refit | NOT RUN | No financial definitions changed; delivery checks reuse saved inputs for parity without rerunning the research |

The source delivery contains no generated test receipts, model bundles, licensed
observations, query caches, charts, PDFs or environment. Detailed local verification
logs remain outside the delivered tree. Results in docs/RESULTS.md are retained
aggregate research findings, not newly estimated trading profits.

A fresh empirical run requires the appropriate WRDS subscriptions, external local
authentication and generated data. Historical publication/revision timing and
vendor conventions remain uncertified. The previously inspected final comparison
period is not a new untouched test. Missing source data cannot be manufactured.
