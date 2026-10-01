# Dispersion Trading - HEC Montréal Trading Club

Research on a dispersion trading strategy,
based on the methodology of Marshall (2009) and Nelken (2006).

## Team

| Name    |
|---------|
| Jeremy  |
| Rami    |
| Kevin   |
| Rafael  |
| Mia     |

## Repo structure

- `data/` — raw and processed data (WRDS/OptionMetrics) — not version-controlled, see `.gitignore`
- `strategy/` — strategy logic (IOIV/MIV calculation, modified Markowitz equation, ATM definition)
- `backtest/` — trade simulation, delta hedging, transaction costs, results


## Methodology

The core dispersion measure is based on the simplified Marshall implied volatility:

\[
MIV_t = \sum_i w_{i,t}\sigma_{i,t}\rho_{i,m,t}
\]

where:

- \(w_{i,t}\) is the weight of constituent \(i\)
- \(\sigma_{i,t}\) is the constituent implied volatility
- \(\rho_{i,m,t}\) is the historical correlation between constituent \(i\) and the index

The dispersion spread is:

\[
Spread_t = IV_{index,t} - MIV_t
\]

### Implied volatility construction

The primary IV methodology uses the OptionMetrics +50Δ call and −50Δ put surface points.

Instead of averaging their implied volatilities directly, the model:

1. retrieves the `impl_premium` of the +50Δ call and −50Δ put;
2. sums the two premiums;
3. retrieves the corresponding strikes, standardized forward, and zero rate;
4. solves for a single volatility that reproduces the combined premium using Black pricing and `scipy.optimize`.

The previous simple-average method remains available as a benchmark:

\[
IV_{avg} =
\frac{
IV_{+50\Delta,C}
+
IV_{-50\Delta,P}
}{2}
\]

## Data

The project uses WRDS data sources including:

- **OptionMetrics IvyDB US**
  - implied volatility surfaces
  - option premiums
  - standardized forwards
  - zero curves
  - OptionMetrics SECIDs

- **CRSP**
  - stock returns
  - stock prices
  - market capitalization
  - PERMNO identifiers
  - S&P 500 historical membership

- **Compustat**
  - historical index constituent membership
  - index identifiers such as GVKEYX
  - constituent identifiers such as GVKEY, IID, CUSIP, and ticker
  - used mainly for indices whose historical membership is not directly available through CRSP

Historical index membership, prices, returns, weights, implied volatility surfaces, and security mappings are resolved dynamically where possible.

## Repo structure

```text
src/
├── data/
│   ├── compustat_membership.py   # Generic Compustat index membership
│   ├── correlation.py            # Return aggregation and stock-index correlation
│   ├── index_config.py           # Known index defaults and configuration
│   ├── index_constituents.py     # Constituent membership orchestration
│   ├── index_discovery.py        # OptionMetrics / Compustat index discovery
│   ├── index_return.py           # Historical index returns
│   ├── index_weights.py          # Price, market-cap, and equal weighting
│   ├── membership_csv.py         # Optional CSV-based historical membership
│   ├── miv.py                    # One-date Marshall MIV calculation
│   ├── miv_history.py            # Historical MIV and dispersion series
│   ├── option_pricing.py         # Black pricing and combined-premium IV inversion
│   ├── optionmetrics_iv.py       # OptionMetrics IV and surface retrieval
│   ├── security_lookup.py        # Ticker / PERMNO / SECID / CUSIP mapping
│   └── wrds_connection.py        # WRDS connection helper
│
└── run_dispersion.py             # Main strategy entry point

data/
└── Raw and processed local data; not version-controlled
```

## Main workflow
```
Index
  ↓
Historical constituents
  ↓
Index weights
  ↓
Constituent implied volatility
  ↓
Stock-index correlation
  ↓
Marshall MIV
  ↓
Observed index implied volatility
  ↓
Dispersion spread
```

Example
Single-date calculation:
```
uv run python run_dispersion.py \
    --index DJIA \
    --date 2024-01-03 \
    --iv-method combined_50delta
```

Historical calculation:
```
uv run python run_dispersion.py \
    --index DJIA \
    --start 2024-01-03 \
    --end 2024-01-31 \
    --iv-method combined_50delta
```
The original IV averaging methodology can still be used with:
```--iv-method average_50delta```



