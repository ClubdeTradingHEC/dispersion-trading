# Current integration review

Final deep-check exception: Rafael specifically approved updating only the Nasdaq
manual discovery diagnostic to inspect actual columns before exploratory queries.
No production financial/membership calculation changes accompany this correction.
All seven manual WRDS diagnostics were then executed without query errors.

The active branch is `codex/integrate-team-updates`, based on team main `5ceaa01`.
INTEGRATION.md records current decisions and checks. Existing Kevin files had
reverted to the initial pipeline; earlier approved working integration differences
were restored after Rafael's explicit authorization. New team quote/cost/export
modules are unchanged. No push/history rewrite occurs. The material below records
the prior source-only delivery and remains historical context, not this branch's
current verification receipt.

# Kevin's review guide

## Branch and comparison points

The local review branch is `codex/github-ready`. No push, merge, rebase, remote
change or history rewrite was performed. `main` remains at the verified original
pipeline commit `335eeb5bab93844a0a92ab08f12f2006ff9f65f6`.

The earlier research integration commit is
`0d3deceb91d5d65be56f43ee4b6d3558d46e9182`. The source consolidation commit is
`928c6c9` (with any subsequent delivery fixes shown by `git log` on this branch).
These commits consolidate previously uncommitted approved work; their order does
not purport to reconstruct the chronology of all earlier research experiments.
New local commits use the same Codex attribution as the earlier integration
commit; personal Git settings and Kevin's authorship are preserved.

From a checkout of the review branch:

```powershell
git log --oneline --decorate main..HEAD
git diff --stat 335eeb5bab93844a0a92ab08f12f2006ff9f65f6 HEAD
git diff --ignore-space-at-eol 335eeb5bab93844a0a92ab08f12f2006ff9f65f6 HEAD -- src/data src/run_dispersion.py
git diff --ignore-space-at-eol 335eeb5bab93844a0a92ab08f12f2006ff9f65f6 HEAD -- src/research configs tests/unit
```

A GitHub ZIP has source files but no Git history. Use GitHub's comparison view or
a Git checkout for these commands. The final tip is reported by `git rev-parse HEAD`;
the exported files are made from that exact committed tree, not an older branch.

## Ownership and what changed

Our layer adds package-IV-based IC/RC measurement, exact complete-panel fast pair
aggregation, explicitly covered available-observation pairs, HAC/bootstrap
inference, actual-gap exploration and the four retained A/B OLS equations.
It includes source/code fingerprints and strict outcome-availability admission.

Diffs against the initial pipeline also contain earlier approved changes to
Kevin-derived integration files. They are not new pricing changes made during
this delivery cleanup. This delivery preserved the starting working bytes of all
39 protected files under src/data, the original runner, discovery scripts and
manual tests. Git stores those exact bytes; compare with --ignore-space-at-eol
to suppress line-ending differences against older commits.

This delivery adds maintained `membership`, `stage` and `gaps` commands to replace
manual/private preparation scripts. Membership calls Kevin's existing resolver;
financial calculations are not reimplemented. Acquisition can publish a raw/
bundle directly. Staging preserves the existing DJIA inputs; the new S&P export
reproduces the earlier corrected four-column files and inference.

No pricing model, rate rule, weight convention, history window, A/B exclusion,
forecast specification or research split was changed for delivery. Missing-data
policy remains the explicitly approved available-input policy. Kevin's manual
live tests remain separate from offline verification.

## Review order

1. Read README and docs/METHODOLOGY.md for definitions, units and limitations.
2. Inspect configs/study.json and configs/djia_crash_days.json for the four
   equations, common eligibility, split dates and fixed training exclusions.
3. Inspect measurement.py, pipeline.py and correlation_features.py for the math;
   dataset.py/modeling.py/workflow.py for timing and estimation.
4. Inspect reproduction.py and PROJECT_GUIDE for the fresh-checkout data path.
5. Run `uv sync --locked`, then `uv run --locked --no-sync dispersion verify`.
   This requires no credentials or market data. Review VALIDATION for what was
   actually executed; new live history downloads are explicitly not part of it.

FILE_MAP accounts for every delivered file. Historical findings remain in
RESULTS; generated observations, fitted models, caches, presentation PDFs,
environments and verification logs are omitted and recreated locally as needed.
A verified implementation is not certification of zero bias or trading profit.
