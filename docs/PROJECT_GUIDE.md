# Reproduction and operation

Run from the repository root with the Python 3.12 uv environment. Use one writer
per output directory. All `important_data/` contents except its README, and all
runtime `data/` outputs, stay outside Git. No observations are included in a ZIP.

## Authentication

Set WRDS_USERNAME in your own shell. Let WRDS use your external pgpass file or
its normal password prompt. Never put account values in source, configuration,
commands checked into Git or an environment file shared with the team. Kevin's
connection/cache implementation is unchanged.

## Bounded live pilot

These commands contact WRDS and require appropriate subscriptions:

```powershell
uv run --locked --no-sync dispersion access --config configs/local_pilot.json
uv run --locked --no-sync dispersion extract --config configs/local_pilot.json --output important_data/pilot --provisional
uv run --locked --no-sync dispersion measure --input important_data/pilot/bundle --config configs/local_pilot.json --output data/pilot --provisional
```

The pilot is one SPX entry date. `--provisional` labels uncertified vendor
conventions; it does not change Kevin's rate rule or option pricing.

## DJIA membership and acquisition (explicit live work)

Use the supplied validated historical CSV at
`important_data/sources/membership.csv` (columns `index,permno,start,end`). It is
local-only and not included in a GitHub source export. It covers the configured
entry period with 28–30 mapped members; early partial baskets stay qualified.
Share this required input separately with authorized WRDS users.

**Do not run `dispersion membership` as an installation/reproduction prerequisite.**
The retained optional command invokes Kevin's automatic name matcher, which still
fails its confidence check for DJX. Table access succeeds; this is not a password
or missing-data permission error. Do not weaken the matcher or fabricate members.

With the CSV supplied, start acquisition here (explicit live work):

```powershell
uv run --locked --no-sync dispersion extract --config configs/measurement.json --output important_data/sources --bundle-name raw --provisional
```

This writes important_data/sources/raw/manifest.json and licensed shards. Full
historical acquisition is substantial; do not run it to check an installation.
The configured observation ceiling is not proof that data exist through that date.
If investigating automatic membership separately, use a one-date configuration
and the default five-date budget, never an unreviewed full-history request.

## DJIA measurement and preparation (offline)

```powershell
uv run --locked --no-sync dispersion measure --input important_data/sources/raw --config configs/measurement.json --output data/measurements/djia --provisional
uv run --locked --no-sync dispersion stage --measurements data/measurements/djia
uv run --locked --no-sync dispersion study check
uv run --locked --no-sync dispersion study prepare
uv run --locked --no-sync dispersion study fit
uv run --locked --no-sync dispersion study explore
uv run --locked --no-sync dispersion study report
uv run --locked --no-sync dispersion study verify
```

`stage` publishes the standard measured full DJIA basket as financial_panel.parquet
and the six-column entry constituent input expected by `prepare`. It explicitly
preserves incomplete mapping qualifications; it does not certify an official-index
replication. To remeasure a scoped entry, add `--dates 2024-07-01` to `measure` and
use a separate output; do not stage a one-date pilot as the full historical study.

`prepare` creates dataset.parquet and source/code fingerprints. `fit` publishes
all eight approved fits atomically. `explore` groups actual completed gaps, not
predicted thresholds. `report` writes Markdown, tables, diagnostics and charts;
`verify` reconstructs real arithmetic and coefficients against statsmodels and
checks timing. None queries WRDS. Generated files can be recreated and are not
shipped. One-off presentation PDFs from the earlier work are not runtime inputs.

## S&P 500 five/seven-year extension

Only `extract` in this sequence contacts WRDS. It uses CRSP historical SPX
membership directly and the same bounded acquisition/measurement engines.

```powershell
uv run --locked --no-sync dispersion extract --config configs/spx.json --output important_data/spx_30d --bundle-name raw --provisional
uv run --locked --no-sync dispersion measure --input important_data/spx_30d/raw --config configs/spx.json --output data/measurements/spx --provisional
uv run --locked --no-sync dispersion gaps --measurements data/measurements/spx --config configs/spx.json --output data/results/spx --years 5,7
```

The output CSV columns are date_of_IC, IC, matched_date_of_RC, RC. Values are
decimals. The matched RC end is entry plus 30 calendar days; daily returns cover
(entry,end]. The available-option-stock proxy is explicit. Missing returns use
observed-session pairs and reported weight coverage, not blanket window rejection.
results.json includes HAC15/30/60, a block-bootstrap interval and Holm adjustment.
coverage.csv contains the measured entry information and status fields.

For the same export on DJIA, use its measurement/config paths and `--basket full`.
The full-basket option eligibility remains distinct from the SPX available-option
proxy. No missing option IV is fabricated.

## Optional original-paper comparison

The historical public-series comparison is separate from WRDS replication and
is optional. Obtain the original published precomputed series with a verified
version/provenance. Convert it locally to
`important_data/sources/public_ic_rc.parquet`, with a datetime `date` column and
finite decimal `SP500ic30,SP500rc30` columns. Record its source and checksum locally.
Then `study report` performs the documented 20/21/22-observation comparisons.
Without that external input, the report marks SOURCE_UNAVAILABLE; it does not
silently substitute a fabricated series. Historical aggregate results remain in
docs/RESULTS.md. Original native-sample coefficient references are also optional
historical inputs, not required for reconstructing current saved models.

## Recovery, testing and source export

Queries, raw shards and measurement checkpoints have inspectable fingerprints.
Changed code/config/data invalidates prepared inputs and saved fits; rerun the
appropriate phases. Failed atomic publication preserves the previous complete
output. Do not treat a partially completed phase as a current result.

```powershell
uv run --locked --no-sync dispersion verify
python scripts/export_source.py --output dist/dispersion-research
```

Default verification is offline; live verification requires explicit `--live`,
with extraction separately explicit. Kevin's `tests/test_*.py` are manual live
checks and are excluded from ordinary pytest collection. GitHub CI runs the offline
suite. The source export requires a reviewed commit; use `--working-tree` only
for a labelled pre-commit candidate. Nothing auto-pushes, merges or rewrites history.

## Other team workflows

See [TEAM_WORKFLOWS](TEAM_WORKFLOWS.md) for returns/cost exports and the consolidated
macro/basket/event/VIX commands. These do not change the four-equation research study.
