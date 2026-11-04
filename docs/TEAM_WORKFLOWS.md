# Team event and execution-cost workflows

Run from the project root after `uv sync --locked`. Use a different output directory
for separate experiments. Ordinary imports and offline verification contact no service.
All generated CSV/XLSX/PNG files remain ignored under data/. Every operator supplies
their own external WRDS authentication; FRED release acquisition separately requires
FRED_API_KEY in the local process environment. Do not edit source to insert keys.

## Returns and trailing basket RC

Kevin's retained export provides daily dated members, weights and returns. This is
explicit live work; long date ranges can be expensive. Example one-day check:

```powershell
uv run --locked --no-sync python -m src.data.export_returns_weights --index SPX --start 2024-07-01 --end 2024-07-01 --weighting market_cap --output important_data/team/returns_one_day.csv
```

For the team's historical event study, acquire its declared interval (2021-08-01
through 2025-07-31), plus any desired leading history, into a separate returns CSV.
The trailing basket calculation requires at least 30 observed trading sessions;
one day cannot produce it. No observations are bundled with the source.

The CSV schema is `date,permno,daily_return,weight` (optional ticker/index/price/cap).
Dates/PERMNO must be unique; returns/weights are decimals. Run offline:

```powershell
uv run --locked --no-sync dispersion-events basket --returns important_data/team/spx_returns_weights_2021_2025.csv --output data/events/basket
```

This writes `basket_correlation.csv`, `tables.xlsx`, full/quarterly charts and
run.json with input/code/output fingerprints. Each output directory belongs to
one command. Publication swaps the complete generation after every table and
chart succeeds; a failed rerun leaves the previous complete generation untouched.
Reruns remove stale charts owned by the previous generation and refuse unrelated
files or output directories containing inputs. Use one writer per directory. Add `--events data/events/macro/macro_events.csv` to annotate charts
and enrich the table, or `--no-plots` for tables only. The same command handles
the 2024-only study with its own input/output; no duplicate calculation engine.

For endpoint weights w and a complete trailing correlation matrix R:

`RC_team = (w' R w - sum(w_i^2)) / ((sum w_i)^2 - sum(w_i^2))`.

The shared fast identity produces this same result without forming the full matrix.
This is trailing 30 **exchange trading-session**, weight-only stock–stock RC.
A completely absent trading date stays missing in the session grid, rather than
silently extending a 30-session or 21-session window. Mixed indices, invalid
identifiers, holiday rows and percent-scaled weights are rejected. Our forecasting
target is future 30 **calendar-day**, weight-times-IV RC. See METHODOLOGY.md.
Stocks without the required complete trailing history/nonzero variance are omitted
and counted. Weights are normalized within the surviving basket, with available
entry mass reported. Partial baskets are not complete official index measurements.

## Macro calendar (live FRED) and event study (offline)

```powershell
uv run --locked --no-sync dispersion-events macro --start 2021-08-01 --end 2025-07-31 --output data/events/macro
uv run --locked --no-sync dispersion-events study --returns important_data/team/spx_returns_weights_2021_2025.csv --correlation data/events/basket/basket_correlation.csv --events data/events/macro/macro_events.csv --output data/events/study
```

configs/events.json preserves the team's FOMC/shock dates and release descriptions.
The macro command requests FRED release dates, retains the team's first-per-month
selection (last for CPI/PPI), and uses the exchange calendar for holidays/weekends
and the declared after-close shocks. The curated calendar/monthly filtering is not
a certified historical release archive. GDP may have several legitimate releases
per quarter; a one-per-month heuristic does not establish revision-free timing.
Dates of explanations remain research annotations, not predictive model inputs.

The study computes RC(t)-RC(t-1), RC(t+1)-RC(t-1), RC(t+2)-RC(t-1).
Normal comparison dates have no FOMC/CPI/NFP in [t-1,t+2]. Broad moves use the
retained absolute return >=1.5% and equal-name directional breadth >=80%.
Outputs are `by_event_type.csv`, `broad_moves.csv`, `event_detail.csv`, tables.xlsx
and run.json. Empty groups are reported with zero count and unavailable statistics.
Welch and Mann–Whitney p-values are retained but named **naive**: rolling windows,
event clusters and repeated comparisons prevent independent-observation inference.
They are descriptive diagnostics; confirmatory event-effect research needs its
own dependence-aware design, not an automatic claim from these tables.

## VIX overlay (offline)

Supply FRED VIXCLS CSV with `observation_date,VIXCLS`; the public CSV endpoint is
https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS . Keep it local.

```powershell
uv run --locked --no-sync dispersion-events vix --returns important_data/team/spx_returns_weights_2021_2025.csv --correlation data/events/basket/basket_correlation.csv --vix important_data/team/VIXCLS.csv --output data/events/vix
```

Retains next 21 observed trading-session sample standard deviation ×sqrt(252)×100.
Entry returns are excluded; the final 21 dates have no matured outcome. VIX is in
annualized percent and is forward-filled from prior observations only. Missing
return weight prevents a false complete-market return/volatility. The same-day
weighted constituent return is a proxy; official index returns are preferable
for a separately specified index-volatility study. Plots cover full history,
2022 and spring 2025 when present. VIX is volatility, not IC; realized above VIX
is not evidence that an actual option trade lost that amount. The overlay also
reports each VIX observation date and its age; forward-filling does not imply
that the carried observation is fresh.

## Preserved execution-cost work

The following new team files retain their supplied bytes and interfaces:

- src/data/option_quotes.py: listed compatible same-strike/expiration call/put
  pairs, closest-30-day and liquidity-aware selection, half-spread/vega arithmetic.
- src/data/compare_straddle_costs.py: selected tickers/method comparison.
- src/data/export_top30_straddle_costs.py: dated SPX top-N, historical links,
  batched quotes, daily/annual/quality/skip and simulator-cost tables.
- src/data/validate_straddle_costs.py: recomputation/quality checks on those tables.
- src/data/export_delta_hedge_costs.py and add_stress_scenario.py: existing
  fixed-path utilities for top30_2019; inputs must first exist at their documented
  module constants. They are retained, not falsely presented as parameterized CLIs.
- src/data/check_stock_bidask.py, inspect_quote_outliers.py and
  scripts/diagnostics/check_option_quotes.py: manual live diagnostics.
- src/backtest/transaction_costs.py: option, stock, futures and total dollar-cost
  helpers; not a trade/backtest engine.

Example bounded live cost acquisition and offline QA:

```powershell
uv run --locked --no-sync python -m src.data.export_top30_straddle_costs --start 2024-07-01 --end 2024-07-01 --top 3 --output data/transaction_costs/pilot
uv run --locked --no-sync dispersion-costs validate --input data/transaction_costs/pilot/straddle_costs_daily.csv
```

Costs are separate from theoretical surface premiums used for package IV. The
OptionMetrics-authored [IvyDB US manual v5.0, p.20](https://lib.tsinghua.edu.cn/PDF/OptionMetricsshiyongzhinan.pdf)
defines option-price vega in cents per volatility percentage point; this supports
the retained division by 100 for dollar-per-point cost calculations. This reference
does not certify execution prices, publication-time liquidity or strategy profit.
Future cost models must not double-charge commissions: exported base/stress costs
exclude commissions; helper option_execution_cost adds its own commission.

## Original script names

All five paths under `scripts/save file/` remain executable, import-safe thin
launchers. Two basket presets share one implementation; no duplicate engines.
Without an explicit --output, they write the canonical data/events outputs and
also preserve the original current-directory CSV/XLSX/chart filenames for existing
consumers. The two 2021_2025 basket CSV spellings (with and without _v2) are both
provided, resolving the original producer/consumer mismatch. The event compatibility
workbook retains its old sheet names and legacy headers; the primary CLI outputs
remain English. These root-level local artifacts are explicitly ignored by Git.
With --output, the launchers use the explicit canonical output directory only.
Do not mix compatibility artifacts with the owned canonical generation directory.
Original local input names are accepted; defaults also recognize the documented
important_data/team inputs and previously generated macro/basket files.
The consolidated plotting style can differ; mathematical parity is checked on
complete real inputs. Missing whole sessions now remain missing, never compressed.

## Membership schema boundary

The research CSV `important_data/sources/membership.csv` uses dated PERMNO intervals
`index,permno,start,end`. Kevin's older optional membership loader expects
`index,ticker,start_date,end_date`. These schemas serve different interfaces;
do not pass the research CSV into the older --membership-file option unchanged.
SPX exports use dated CRSP membership directly. Kevin's explicit --tickers path
was live-checked on three stocks; it does not represent a complete index basket.
No silent ticker/PERMNO conversion or contemporary replacement list was introduced.

## Automated cost QA and preserved manual diagnostics

The original `python -m src.data.validate_straddle_costs` remains a human-readable
report and preserves its old exit behavior. Automation must use
`dispersion-costs validate --input FILE`: it calls the same calculation, prints
only counts, and exits 1 for failed/empty QA or 2 for invalid/unreadable inputs.
No cost formula, quote selector or protected data module is changed by this wrapper.

All seven supplied manual WRDS diagnostics were executed with their bounded
historical scopes. Rafael specifically authorized making only
tests/test_ndx_membership_sources.py schema-aware after its exploratory probes
failed on nonexistent columns (SQL 42703). It now filters only actual GVKEYX
columns, uses actual date fields where available and explicitly skips incompatible
candidate tables. It does not replace production membership logic or certify full
Nasdaq coverage. Ordinary pytest/dispersion verify remain fully offline.

The original basket launchers still include the team's five extra 2024 shocks,
even when an older macro CSV lacks them. The primary basket CLI can opt into this
compatibility behavior with --legacy-shocks-config configs/events.json; otherwise
it annotates only the supplied events. The VIX command also accepts --events for
shock annotations in the 2022 and spring-2025 zoom charts.
