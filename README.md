# Dispersion research — integrated team project

Kevin's WRDS/MIV implementation, Rafael's IC/RC research, and the team's event, VIX and execution-cost tools. This is a
source-only project: data, environments, fitted models and generated reports
are created locally and are not part of the GitHub download.

Team roster from the incoming repository: Jeremy, Rami, Kevin, Rafael and Mia.

## Install and verify

Use Python 3.12 and uv. Run commands from the extracted repository root:

```powershell
uv sync --locked
uv run --locked --no-sync dispersion verify
```

Verification is offline. It runs the maintained unit suite, not Kevin's live
manual tests. No WRDS login, downloads or model fitting occur during verification.
A ZIP download works without Git installed for installation and research use.

## Reproduce the research

[PROJECT_GUIDE](docs/PROJECT_GUIDE.md) gives the complete acquisition, measurement,
preparation, fitting and reporting commands, with explicit live/offline boundaries.
You need your own licensed WRDS access and local authentication for acquisition.
Supply the dated DJIA membership CSV separately at `important_data/sources/membership.csv`.
The automatic DJIA name-discovery route currently fails its confidence check;
skip `dispersion membership` when the supplied CSV is available. No desktop path is hardcoded.

After acquiring and staging DJIA measurements, run:

```powershell
uv run --locked --no-sync dispersion study check
uv run --locked --no-sync dispersion study prepare
uv run --locked --no-sync dispersion study fit
uv run --locked --no-sync dispersion study explore
uv run --locked --no-sync dispersion study report
uv run --locked --no-sync dispersion study verify
```

The four equations predict 30-calendar-day future RC: IC-only; IC + past RC;
five variables; IC + past RC + slow/downside co-movement. Each has A (all eligible
training) and B (fixed crash-containing training exclusions). Training information
is restricted to 2011-2022; the 2023-2025 comparison period was previously inspected.
The signal is IC minus predicted RC, in decimals and correlation points, not trade
returns. Actual-gap quintiles/deciles are a separate descriptive exercise.

S&P 500 five/seven-year matched exports use `configs/spx.json` and `dispersion gaps`.
Only explicit acquisition commands contact WRDS. Historical publication timing,
partial baskets, vendor conventions and model calibration remain qualified.

## Team workflows

[TEAM_WORKFLOWS](docs/TEAM_WORKFLOWS.md) documents the preserved returns, listed-option
quotes/costs, macro calendar, trailing basket RC, event study and VIX tools.
`dispersion-events --help` exposes explicit paths and live/offline boundaries.
`dispersion-costs validate --input PATH` provides strict offline cost QA with a
nonzero exit on failed rows; the original human-readable cost report remains available.
The original five script names remain compatibility launchers. The team's trailing
weight-only RC and our forward weight-times-IV RC remain separate definitions.

[INTEGRATION](docs/INTEGRATION.md) retains all 16 agreed plan/safeguard points,
integration decisions and known limits. Work is on `codex/integrate-team-updates`,
based on the team's `5ceaa01`; original supplied folders remain unchanged.
The integration changes are uncommitted for review; nothing was pushed.

## Files and ownership

- `src/data/`, `src/run_dispersion.py`, discovery scripts and manual tests:
  Kevin-derived implementation, with the earlier approved compatibility changes restored during integration.
- `src/research/`: financial measurement, inference, four-model study and reproduction.
- `src/events/`: consolidated English event/basket/VIX workflows.
- `src/backtest/transaction_costs.py`: preserved team cost arithmetic, not a simulator.
- New quote/cost/return export modules in `src/data/`: preserved team functionality.
- `configs/`: declared dates, conventions and the fixed 33 DJIA crash dates.
- `tests/unit/`: offline contracts and hand-checkable arithmetic/timing fixtures.
- `docs/`: methodology, retained findings, operation, validation and file inventory.
- `important_data/README.md`: explains local-only inputs and generated data.

Kevin's original entry point remains `dispersion-trading-hec-trading-club` and
retains its existing live/manual behavior. See [Kevin's review guide](docs/KEVIN_REVIEW.md)
for the verified Git baseline and the distinction between earlier approved
integration changes and this source-delivery work.

## Source delivery

[FILE_MAP](docs/FILE_MAP.md) accounts for retained files. [VALIDATION](docs/VALIDATION.md)
records executed checks and limits. [RESULTS](docs/RESULTS.md) retains concise
aggregate findings; [METHODOLOGY](docs/METHODOLOGY.md) defines formulas and timing.

After committing the reviewed tree, export its exact GitHub ZIP contents:

```powershell
python scripts/export_source.py --output dist/dispersion-research
```

The export contains no `.git`, `.venv`, raw data, saved models, caches or generated
PDFs/charts. The explicit `--working-tree` option creates a review candidate before
committing; it is not labelled a committed snapshot. A push remains a separate
action. No code check establishes zero bias or trading profitability.
