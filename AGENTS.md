# Dispersion research — repository instructions

## Current authorization and ownership

Rafael authorized the full cleanup of our entire project layer, preserving four
OLS specifications (IC-only; IC+past RC; five variables; slow/downside) and both
A/B designs. Remove superseded trial infrastructure, duplicate data and obsolete
instructions. Keep useful financial calculations, tests and actual-gap research.
The separate user backup is outside this repository's cleanup scope. Keep a file-by-file purpose/consumer inventory in docs/FILE_MAP.md; do not retain a helper merely because an old test calls it.

Preserve src/data/, src/run_dispersion.py, scripts/discovery/ and Kevin's manual
tests/test_*.py. Ask for specific confirmation before changing Kevin-derived
code or behavior. General cleanup/improvement requests do not authorize that.
The protected baseline is the working state at cleanup start; earlier approved
integration changes are not automatically reverted.

Keep Kevin's rate rule (divide by 100 when abs(raw)>1), weights, monthly/history
handling, partial MIV and partial mapping with missing counts. Do not change
pricing models, rates or vendor conventions to make diagnostics pass.

## Active specification

Read README.md, pyproject.toml, uv.lock, configs/study.json,
configs/measurement.json and docs/METHODOLOGY.md before substantial changes.
Latest explicit user choices supersede historical PDFs and generic defaults.

DJIA/DJX, 30 calendar days. Training entries begin 2011-01-01, and both signal
and outcome availability must be <=2022-12-31. Annual development predictions
use earlier matured labels. Final comparison: 2023-01-01 through feasible
2025-08-29 entries. This period is already inspected, not fresh confirmation.
The global observation ceiling is 2026-12-31; it does not prove data exist.
Configured option sources previously ended 2025-08-29. Never fabricate future
observations or unmatured labels. Earlier observations can supply feature history,
not pre-2011 training rows. Original-paper comparisons retain their own dates.

Fit all four approved equations for A (all eligible training) and B (fixed crash
exclusions). configs/djia_crash_days.json contains 33 predefined crash dates;
exclude entry crashes and future-30-day crash-containing training outcomes only.
Keep crash returns in predictors and use the same final dates including stress.
All models use common feature eligibility; original native-sample results have
separate compact parity evidence. No automatic winner selection or outcome-tuned
exclusions, feature windows, calibration or thresholds.

## Financial and statistical contracts

Definitions, formulas, units and source caveats are in docs/METHODOLOGY.md.
Add package premiums, never IVs. Keep stock-index MIV separate from stock-stock
IC/RC. Freeze entry membership/weights/IV-based pair weights for future RC.
Use the exact fast pair identity only when its complete-panel assumptions hold.
Rafael explicitly removed blanket window rejection for one unavailable stock.
Follow Kevin's skip-and-report approach: omit missing entry weighting inputs;
retain valid vendor returns regardless of duration flags; match observed returns
per pair (minimum configured overlap), and explicitly normalize available pair
weights while reporting counts, original pair-weight mass and missing observations.
Do not clamp raw IC, zero-fill missing returns, silently reweight surviving pairs,
substitute survivors or label a partial basket as the complete official index.

Use label availability, not only signal date, to admit training examples. Features
must use entry-or-earlier information. Publication/revision timing is uncertified;
state assumptions rather than claiming executable point-in-time certification.
Overlapping outcomes require calendar-grid HAC, block bootstrap and non-overlap
sensitivities. Keep calibration, stability, stationarity, influence, variance and
collinearity diagnostics visible. Non-rejection is not proof of no bias or
coefficient stability; associations and positive gaps are not trading profit.

Keep package-IV/MIV, IC/RC, exploratory MIC, basket and actual-gap functionality.
New nonlinear models, LASSO/BLT, trade execution and hedged P&L are outside scope
unless specifically authorized. Do not resurrect them from historical materials.

## Implementation, tests and data

Prefer one authoritative path and targeted changes. No duplicate production
engines, frozen source copies, fake market datasets or simulator laboratories.
Keep useful tests and small hand-checkable arithmetic/timing fixtures. Document
logical blocks in our code; preserve Kevin-derived files even for cosmetic edits.

Use Python 3.12 and the existing uv lock. Preserve pandas 2.1.4 / SQLAlchemy 1.4.54
compatibility; pandas 2.2.3 previously broke normal wrds.raw_sql locally.
Dependency edits require coherent TOML/lock/environment updates and checks.
Run focused tests after changes and the offline CLI before compatibility claims.
Real arithmetic checks complement, not replace, software tests. Never claim an
unexecuted query, PDF read, paper replication or independent review.

Raw licensed observations and reusable datasets remain ignored under important_data/. Runtime outputs under data/ are disposable. Credentials stay in local
WRDS authentication. Do not log credentials, connection strings or licensed raw
rows, or commit/upload licensed extracts. Keep queries scoped, bounded, cached
and restartable. Unexpectedly costly historical downloads require approval.
Ordinary imports, offline tests and study phases must not query WRDS.

Use explicit commands documented in README and PROJECT_GUIDE. Source checksums,
model/data fingerprints and phase receipts must remain inspectable. Keep generated
outputs local and concise. No new historical dossier for every small change.

## Git and delivery

Use the current authorized branch and respect existing user edits. Do not commit,
push, change remotes, rebase or rewrite history without explicit instruction.
Verify deletion targets are within the intended workspace. Avoid duplicate
archives; the user already has a separate backup.

Report actual changed files, commands/test counts, empirical findings and any
material limits. Use PASS, FAIL, NOT RUN or NEEDS DECISION accurately. Engineering
readiness does not certify zero bias, vendor conventions or trading profitability.
