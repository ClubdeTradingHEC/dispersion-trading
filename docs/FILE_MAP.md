# Delivered file inventory

Every delivered source file is listed below. Generated material is excluded.
Kevin-derived files preserve the approved delivery starting bytes, including
earlier approved integration changes. This is an inventory, not another engine.

| File | Purpose / consumer |
|---|---|
| `.gitattributes` | Explicit line endings for our files without rewriting Kevin working files. |
| `.github/workflows/tests.yml` | Hosted offline checks on pushes/pull requests; no WRDS credentials. |
| `.gitignore` | Secrets, licensed data, runtime outputs and environments stay out of Git. |
| `.python-version` | Select Python 3.12 for uv. |
| `AGENTS.md` | Current scope, ownership, scientific and authorization rules. |
| `backtest/.gitkeep` | Existing empty project-directory marker. |
| `configs/djia_crash_days.json` | Fixed 33 Model B crash dates; kept separate to inspect the sample rule. |
| `configs/local_pilot.json` | Bounded SPX access/measurement diagnostics; prevents routine full-history downloads. |
| `configs/measurement.json` | DJIA financial rebuilding and explicit observation/vendor conventions. |
| `configs/spx.json` | Seven-year SPX acquisition/measurement and five/seven-year exports. |
| `configs/study.json` | Four retained models, feature windows, A/B study split and permanent/runtime paths. |
| `data/.gitkeep` | Existing empty project-directory marker. |
| `docs/FILE_MAP.md` | This necessity/ownership review; each retained file is accounted for. |
| `docs/KEVIN_REVIEW.md` | Verified baseline, branch comparison and ownership guide. |
| `docs/METHODOLOGY.md` | Financial definitions, features, units, timing and inference. |
| `docs/PROJECT_GUIDE.md` | Detailed reproducible operations and recovery behavior. |
| `docs/RESULTS.md` | Important aggregate research findings usable without licensed local data. |
| `docs/SOURCES.md` | Primary methodological and dated economic references. |
| `docs/VALIDATION.md` | Actual current checks and remaining limits. |
| `important_data/README.md` | Non-sensitive inventory/instructions; the only tracked file in that folder. |
| `pyproject.toml` | Package/CLI/dependency/test/build declarations. |
| `README.md` | Installation, data boundary, commands and handoff entry point. |
| `scripts/__init__.py` | Existing script package marker. |
| `scripts/discovery/__init__.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/compare_iv_methods.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/discover_crsp_optionm_link.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/discover_crsp_stock_table.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/discover_djia_sources.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/discover_ndx_sources.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/discover_optionmetrics_pricing_inputs.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/discover_sp500_sources.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/find_djia_index.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/find_underlying_price_source.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/inspect_iv_tables.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/inspect_usb_mapping.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/iv_lookup.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/discovery/pull_optionmetrics.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `scripts/export_source.py` | Committed GitHub ZIP-equivalent export or explicitly labelled working candidate. |
| `src/__init__.py` | Existing source package marker. |
| `src/data/__init__.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/compustat_membership.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/correlation.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/index_config.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/index_constituents.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/index_discovery.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/index_return.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/index_weights.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/membership_csv.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/miv.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/miv_history.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/option_pricing.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/optionmetrics_iv.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/query_cache.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/rates.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/security_lookup.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/data/wrds_connection.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `src/research/__init__.py` | Python package marker; contains no trial implementation. |
| `src/research/batching.py` | Bounded disk measurement, verified restart checkpoints and atomic output publication. Consumer: CLI measure/live verification. |
| `src/research/cli.py` | Supported command interface and offline test receipts. Consumer: dispersion entry point. |
| `src/research/config.py` | Financial/index settings and validation. Consumers: acquisition, measurement and financial inference. |
| `src/research/correlation_features.py` | Slow Pearson and downside features with exact pair aggregation. Consumer: dataset preparation. |
| `src/research/dataset.py` | Canonical dataset, source/code fingerprints and eligibility. Consumers: all study phases. |
| `src/research/diagnostics.py` | Stationarity, calibration and residual diagnostics. Consumer: study report. |
| `src/research/errors.py` | Structured financial-data rejection codes. Consumers: all financial input/calculation layers and Kevin adapters. |
| `src/research/exploration.py` | Actual-gap quintiles/deciles, tail episodes and explanatory controls. Consumer: study explore. |
| `src/research/inference.py` | Calendar-grid HAC, bootstrap, historical gap inference and sensitivity samples. Consumers: reports, models and basket tests. |
| `src/research/inputs.py` | Normalized table contracts, effective membership/link selection, return quality and label availability. Consumers: storage/acquisition/measurement. |
| `src/research/measurement.py` | IC, exact fast/explicit pair RC, missing-pair bounds, MIV and matched MIC measures. Consumer: financial pipeline and real verification. |
| `src/research/modeling.py` | Single OLS solver, actual chronological forecast blocks, A/B fits and robust comparisons. Consumers: workflow and reports. |
| `src/research/pipeline.py` | Financial basket/option/return orchestration and explicit exclusions. Consumer: bounded measurement runner. |
| `src/research/pricing.py` | Package adapter reusing Kevin pricing/rates plus quality diagnostics. Consumer: financial pipeline. |
| `src/research/reporting.py` | Generic financial gap/basket/branch reporting. Consumers: analyze/report commands. |
| `src/research/reproduction.py` | Fresh-checkout membership, source staging and matched gap exports; consumer: CLI. |
| `src/research/statistics.py` | Crash masks, consecutive-session runs and multiplicity correction. Consumers: preparation and inference. |
| `src/research/store.py` | Verified partitioned source IO and atomic publication/JSON metadata. Consumers: acquisition, measurement and research workflow. |
| `src/research/study_report.py` | Four-model equations/scores, fixed diagnostics and historical/public gap summaries. Consumer: study report. |
| `src/research/subsets.py` | Point-in-time basket adequacy and held-out equivalence checks. Consumers: subsets and generic financial report. |
| `src/research/workflow.py` | Study phase dispatch, compact retained model bundle, real arithmetic/parity and source receipts. Consumer: CLI study. |
| `src/research/wrds_client.py` | Explicit bounded acquisition using Kevin connection/cache primitives. Consumers: access/extract and optional live verification. |
| `src/run_dispersion.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `strategy/.gitkeep` | Existing empty project-directory marker. |
| `tests/__init__.py` | Existing test package marker. |
| `tests/test_crsp_optionm_mapping.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/test_full_mapping_20240103.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/test_marshall_correlations.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/test_ndx_membership_sources.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/test_optionmetrics_stocks.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/test_sp500_constituents.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/test_sp500_weights.py` | Protected Kevin-derived implementation/discovery/manual check; retained unchanged during this delivery. Manual tests may contact WRDS. |
| `tests/unit/test_audit_corrections.py` | Financial branch isolation, mappings, finite OLS input, paired losses, disk batching and recovery. |
| `tests/unit/test_available_pairs.py` | Offline contract tests for available pairs. Consumer: pytest/offline CLI. |
| `tests/unit/test_correlation_features.py` | Independent feature arithmetic, sign rules, missingness and entry-prefix invariance. |
| `tests/unit/test_financial_contracts.py` | Known financial formulas, rate/package inversion, source and time-bound contracts. |
| `tests/unit/test_inference_timing.py` | Independent HAC/equivalence arithmetic and actual matured training admission. |
| `tests/unit/test_integration_contracts.py` | Cross-layer API/schema/storage/measurement contracts and dependency compatibility. |
| `tests/unit/test_modeling.py` | Independent OLS/HAC/Wald arithmetic and active A/B admission. |
| `tests/unit/test_repository_contracts.py` | Production consumers, unused imports, ignored settings, undefined globals and atomic metadata failure recovery. |
| `tests/unit/test_reproduction.py` | Budget-before-login, matched CSV arithmetic/schema and source-export exclusions. |
| `tests/unit/test_research_readiness.py` | Observation ceilings, original Kevin defaults, extraction limits and no hidden live work. |
| `tests/unit/test_sample_timing.py` | Actual forecast block leakage/A-B tests, crash boundaries and checkpoint reuse. |
| `tests/unit/test_workflow.py` | Approved specification, stale input/model rejection and failed-fit recovery. |
| `uv.lock` | Reproducible runtime dependency contract. |
