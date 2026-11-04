# Team integration — 2026-11-03

The input was the already combined team checkout at `5ceaa01` (main). Work is
on `codex/integrate-team-updates` in a separate folder. The supplied mixed folder,
the earlier research delivery and original development project are not edited.
No remote, main branch, history or inherited stash is rewritten; no push occurs.

## Accepted plan and safeguards

All eight plan points and eight additional safeguards remain applicable:

1. **Identify exactly what changed.** Compare the mixed project, earlier research
   delivery and available Git history; distinguish our changes, team updates,
   overlapping implementations and missing files. Newer is not automatically better.
2. **Map how the whole project works.** Trace acquisition, membership/identifiers,
   pricing, IC/RC, regressions and other team modules, including producers/consumers.
3. **Choose one implementation where there is genuine duplication.** Compare
   correctness, assumptions, compatibility, tests and maintenance. Preserve distinct
   tasks; record decisions; specifically confirm protected Kevin-derived changes.
4. **Preserve our agreed research specifications.** Keep four equations, A/B,
   timing, crash rules, actual gaps, corrected missing-stock handling and MIV/IC/RC distinctions.
5. **Resolve dependencies and integrate the workflows.** Keep coherent installation,
   configuration and commands, verified WRDS compatibility and the supplied CSV route.
6. **Verify the combined project at several levels.** Run both sets of tests,
   independent arithmetic, same-input comparisons, bounded live queries, a small
   end-to-end workflow and a clean source-export installation. Full downloads/refits
   are separate; never imply an unexecuted historical replication passed.
7. **Clean the final delivery.** Retain useful source/tests/docs/config; exclude
   credentials, environments, caches and reproducible outputs; identify essential
   external inputs and keep licensed extracts outside tracked delivery.
8. **Provide an inspectable handoff.** English README, operation instructions,
   file map, decisions and truthful PASS/FAIL/NOT RUN evidence. Preserve history on
   a review branch; distinguish the unfinished independent Faria replication.
9. **Check behavior before deleting duplicates.** Similar functions can have
   different inputs, dates, units or missing-data rules; inspect callers and outputs.
10. **Trace undocumented code.** Read it, identify consumers, run focused checks
    and explain its purpose; missing documentation alone does not justify deletion.
11. **Check interactions explicitly.** Dependencies, filenames, overwritten outputs,
    units, configuration, imports and unexpected network/calculation side effects.
12. **Establish a baseline before integration.** Separate inherited failures from
    integration regressions.
13. **Integrate in small steps.** Check meaningful changes while failures remain local.
14. **Preserve financial differences deliberately.** Pricing, weighting and missing-data
    choices must not be silently merged just to reduce code.
15. **Remove files only with evidence.** Check necessity, replacements and consumers;
    investigate uncertain purpose or retain with a clear note.
16. **Verify reproducibility separately from saved results.** State which results
    were actually regenerated, not merely present in an old report.

Additional commitments: choose implementations by fitness for the intended task,
not attractive results; use external references for concrete questions; preserve
original script launch paths where practical; keep optional credentials outside source.

## Findings and decisions

The mixed folder had all of `src/research/`, all 160 prior unit cases and the new
team modules, but older packaging/entry points and reverted Kevin integration.
Baseline with the previously tested environment: **133 passed, 27 failed**.
Failures were import paths, missing mapping counts/ambiguity handling and history
defaults. The new team commits add files rather than changing existing Kevin files
after `335eeb5`. Rafael explicitly authorized choosing the working integration
after these concrete failures were presented.

| Area | Decision and rationale |
|---|---|
| Existing Kevin modules, discovery/manual entry points | Restore only earlier approved functional integration differences from the ready research delivery; do not replace newly added team modules. Keep original rate/pricing/weight conventions. |
| Research engine/configuration | Preserve all research calculations and four A/B specifications; only the verification CLI checkout-location bug is corrected; no new fit, thresholds or outcome-tuned choices. |
| New quote/cost/returns exports | Retain the ten newly supplied `src/data/` files and execution-cost helper unchanged. They serve different tasks from theoretical surface-package IV and forward IC/RC. |
| Packaging | Restore the working Python 3.12 package and both existing commands, add `dispersion-events`, requests/openpyxl and regenerate the lock. Preserve pandas 2.1.4 / SQLAlchemy 1.4.54. |
| Two near-duplicate basket scripts | One shared implementation, same trailing session and pair-weight definitions. Keep both original paths as launchers. Actual old/new real-data parity is within floating-point rounding. |
| Event study | Preserve event-day changes, broad-move criteria, Welch/Mann–Whitney calculations. English outputs, empty-group handling and explicit descriptive/overlap caveats. No regression features or trading thresholds added. |
| VIX exploration | Preserve next-21-session volatility and both chart types; handle missing VIX/returns explicitly. Realized-over-implied is not labelled actual trading loss. |
| Macro calendar | Keep team's curated events/config and monthly FRED filtering, externalize API key, paginate, reject future-end requests and align to exchange holidays. No claim of independently verified historical event vintage. |
| Producer/consumer mismatch | Common explicit basket filename consumed by study and VIX commands. Runtime outputs go to caller-selected directories under data/. |
| Other useful files | No source path deleted. Old script filenames remain small import-safe compatibility launchers. Data/cost/discovery/manual tools remain. |
| Data | Preserve supplied membership CSV locally and byte-for-byte. Untrack it in the integration index without deleting it. WRDS recipients receive it separately; automatic DJIA name discovery remains failing. |

The event module reuses the existing exact pair identity for its complete trailing
columns, using `a=w`. The research engine uses `a=w*IV` and future windows. The two
are not interchangeable. Team event exclusion is per stock, not whole-day rejection.
Constant-return columns are now reported/excluded rather than producing silent NaNs.
The market proxy refuses incomplete return-weight mass rather than silently treating
missing returns as zero. It remains a same-day constituent-weight return proxy,
not the official index and not a tradable point-in-time portfolio.

## Verification scope and limitations

See VALIDATION.md for executed checks. All generated checks/data/environments are
outside the delivered source tree. The full historical research was not rerun;
the prior aggregate results remain historical evidence, not new estimates.
The independent raw-data Faria-period reconstruction remains unfinished.

Automatic Compustat DJIA name matching fails the existing confidence requirement.
Do not weaken it or claim it passed: use the supplied dated membership CSV.
Full FRED calendar acquisition requires each operator's FRED_API_KEY; no key was
available for a new release-calendar acquisition. Public VIX CSV acquisition did pass.
The curated macro configuration and its monthly release selection are exploratory,
not certified publication-time predictors. Legacy p-values assume independent
observations and are explicitly labelled naive; overlapping event windows do not
establish causal effects. No new execution simulator or profit claim is introduced.

## Review and delivery

Compare the integration worktree against parent `5ceaa01`; changes are intentionally
left uncommitted for review. Use `git diff --ignore-space-at-eol` and `git status`
for tracked changes, and inspect new src/events/config/docs/tests paths shown by
status. The branch does not modify upstream main. Do not pop the inherited stash
over this tree: it contains an earlier integration state, not an integration command.
After review, explicitly commit source changes and the membership untracking,
then use scripts/export_source.py for an exact committed GitHub-equivalent export.
No automatic push or duplicate ZIP is made.

Final additional evidence: the source-only export contains 131 inventoried files;
its fresh environment passes all 187 tests. All 104 Python files compile and have
no unresolved function-global names. All original script launch paths accept help.
Real feature regeneration reproduces 3,665 rows/3,414 eligible, all eight saved
regressions and 15 annual arithmetic checks. No new outcome-selected model is fitted.

## Final deeper review — 2026-11-04

The first 171 tests missed seven concrete teammate-facing failures. They were
reproduced before fixes and retained as external verification evidence:

1. Legacy script paths no longer produced their original filenames. Thin adapters
   now preserve the old producer/consumer CSV/XLSX/chart contracts for no-output-flag
   runs, while sharing one calculation engine. Explicit output flags stay canonical.
2. A failed event rerun could partly replace tables under an old PASS receipt.
   Whole-generation publication now uses the existing transactional publisher.
3. A completely absent trading date silently compressed historical/future windows.
   Exchange sessions are explicit; no missing return is invented.
4. Concatenated different indices could be processed as one basket. Inputs now
   require one index, valid permanent identifiers, session dates and decimal weights.
5. The original cost report exits 0 even with failed rows. Preserve that reporting
   interface; add dispersion-costs validate for strict automated QA on the same math.
6. One document had Windows-default bytes incompatible with UTF-8. Source/docs
   are now verified portable UTF-8.
7. Non-editable installation looked for tests in site-packages. The offline
   verifier now locates the source checkout, with an actionable missing-checkout error.

Additionally, the original Nasdaq discovery diagnostic failed three exploratory
queries on absent column assumptions (42703), not account permissions. Rafael
specifically approved its schema-aware correction. All seven manual diagnostics
then ran without query errors; incompatible candidate tables are explicitly skipped.
No production financial/membership behavior was changed for this correction.

A fresh one-date DJIA extraction through the supplied membership CSV created all
nine raw tables and measured IC/future RC successfully. IC, past RC and future RC
match the saved 2024-07-01 result exactly. Original fixed-path stress/stock-hedge
utilities also ran unchanged using the existing one-date 2024 cost sample, with
four straddle rows and three valid stock-hedge rows. This is not a 2019 study.
The new non-editable installation passes all 186 offline tests.

The automatic DJIA name-discovery failure and missing live FRED API key remain
separate documented limits. No full-history research refresh, push or commit occurs.

Final same-input comparisons also preserve the original basket shock annotations, event-statistic tables and VIX overlay columns. Their maximum numerical differences are 5.56e-16, 2.99e-16 and 1.43e-14 respectively on the retained real sample.
