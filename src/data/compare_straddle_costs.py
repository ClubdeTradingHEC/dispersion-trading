
import argparse
from pathlib import Path

import pandas as pd

from .wrds_connection import get_wrds_connection
from .option_quotes import get_atm_straddle_quotes


DEFAULT_TICKERS = ["SPX", "AAPL", "MSFT", "NVDA"]

SELECTION_METHODS = [
    "closest_30d",
    "liquidity_aware",
]


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

def get_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compare historical ATM straddle transaction costs "
            "under closest-30D and liquidity-aware selection."
        )
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="OptionMetrics tickers to analyze",
    )

    parser.add_argument(
        "--output",
        default="data/transaction_costs",
        help="Output directory",
    )

    parser.add_argument(
        "--min-open-interest",
        type=int,
        default=100,
        help="Minimum open interest on each leg for liquidity-aware selection",
    )

    parser.add_argument(
        "--max-maturity-distance",
        type=int,
        default=10,
        help="Maximum absolute distance from 30 DTE for liquidity-aware selection",
    )

    return parser.parse_args()


# ============================================================
# OPTIONMETRICS SECURITY LOOKUP
# ============================================================

def get_secids(db, tickers):
    """
    Resolve tickers to OptionMetrics SECIDs.

    Requires a unique SECID per ticker for this diagnostic.
    For long historical samples, use point-in-time mapping.
    """

    results = {}

    for ticker in tickers:
        ticker = ticker.upper().strip()
        safe_ticker = ticker.replace("'", "''")

        df = db.raw_sql(
            f"""
            SELECT DISTINCT
                secid
            FROM optionm.securd
            WHERE UPPER(ticker) = '{safe_ticker}'
            """
        )

        ids = (
            pd.to_numeric(
                df["secid"],
                errors="coerce",
            )
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        if len(ids) != 1:
            raise ValueError(
                f"{ticker}: expected exactly one SECID, found {ids}. "
                "Resolve this security mapping before running."
            )

        results[ticker] = ids[0]

    return results


# ============================================================
# TRADING DATES
# ============================================================

def get_trading_dates(db, start, end):
    """
    Use actual trading dates from CRSP.

    This avoids assuming every weekday is a trading day.
    """

    df = db.raw_sql(
        f"""
        SELECT DISTINCT
            dlycaldt AS date
        FROM crsp.dsf_v2
        WHERE dlycaldt >= '{start}'
          AND dlycaldt <= '{end}'
        ORDER BY dlycaldt
        """,
        date_cols=["date"],
    )

    if df.empty:
        return []

    return df["date"].dt.date.tolist()


# ============================================================
# SUMMARY STATISTICS
# ============================================================

def build_summary(daily):
    """
    Summarize transaction costs by ticker, year, and method.
    """

    daily = daily.copy()

    daily["date"] = pd.to_datetime(
        daily["date"]
    )

    daily["year"] = daily["date"].dt.year

    summary = (
        daily.groupby(
            [
                "year",
                "ticker",
                "selection_method",
            ],
            as_index=False,
        )
        .agg(
            observations=(
                "cost_vol_points",
                "size",
            ),
            median_cost_vol_pts=(
                "cost_vol_points",
                "median",
            ),
            mean_cost_vol_pts=(
                "cost_vol_points",
                "mean",
            ),
            p95_cost_vol_pts=(
                "cost_vol_points",
                lambda x: x.quantile(0.95),
            ),
            max_cost_vol_pts=(
                "cost_vol_points",
                "max",
            ),
            median_half_spread_pct=(
                "half_spread_pct",
                "median",
            ),
            median_dte=(
                "dte",
                "median",
            ),
            median_min_oi=(
                "min_open_interest",
                "median",
            ),
            median_total_volume=(
                "total_volume",
                "median",
            ),
            wide_spread_count=(
                "wide_spread_flag",
                "sum",
            ),
        )
    )

    return summary.sort_values(
        [
            "year",
            "ticker",
            "selection_method",
        ]
    ).reset_index(drop=True)


# ============================================================
# PAIRED COMPARISON
# ============================================================

def build_method_comparison(daily):
    """
    Compare both methods for the same ticker and date.

    Only dates for which both methods succeeded are included.
    """

    columns = [
        "cost_vol_points",
        "half_spread_pct",
        "dte",
        "min_open_interest",
        "total_volume",
        "expiration",
        "strike",
    ]

    wide = daily.pivot_table(
        index=[
            "date",
            "ticker",
            "secid",
        ],
        columns="selection_method",
        values=columns,
        aggfunc="first",
    )

    wide.columns = [
        f"{metric}_{method}"
        for metric, method in wide.columns
    ]

    wide = wide.reset_index()

    baseline = "cost_vol_points_closest_30d"
    liquid = "cost_vol_points_liquidity_aware"

    if baseline not in wide.columns or liquid not in wide.columns:
        return pd.DataFrame()

    wide = wide.dropna(
        subset=[
            baseline,
            liquid,
        ]
    ).copy()

    wide["cost_difference_vol_pts"] = (
        wide[liquid] - wide[baseline]
    )

    wide["cost_reduction_pct"] = (
        100
        * (wide[baseline] - wide[liquid])
        / wide[baseline]
    )

    wide["dte_difference"] = (
        wide["dte_liquidity_aware"]
        - wide["dte_closest_30d"]
    )

    wide["same_expiration"] = (
        wide["expiration_closest_30d"]
        == wide["expiration_liquidity_aware"]
    )

    wide["same_strike"] = (
        wide["strike_closest_30d"]
        == wide["strike_liquidity_aware"]
    )

    return wide.sort_values(
        [
            "ticker",
            "date",
        ]
    ).reset_index(drop=True)


# ============================================================
# MAIN EXPORT FUNCTION
# ============================================================

def compare_costs(
    start,
    end,
    tickers,
    output,
    min_open_interest=100,
    max_maturity_distance=10,
):
    start_date = pd.Timestamp(start).date()
    end_date = pd.Timestamp(end).date()

    if end_date < start_date:
        raise ValueError(
            "--end must be greater than or equal to --start."
        )

    if start_date.year != end_date.year:
        raise ValueError(
            "Run one calendar year at a time for this diagnostic."
        )

    year = start_date.year

    db = get_wrds_connection()

    rows = []
    skipped = []

    try:
        secids = get_secids(
            db=db,
            tickers=tickers,
        )

        dates = get_trading_dates(
            db=db,
            start=start_date,
            end=end_date,
        )

        if not dates:
            raise ValueError(
                "No trading dates found."
            )

        print("\n=== STRADDLE COST COMPARISON ===")
        print(f"Period: {start_date} to {end_date}")
        print(f"Trading dates: {len(dates)}")
        print(f"Tickers: {', '.join(secids)}")
        print(f"Methods: {', '.join(SELECTION_METHODS)}")

        print("\n=== SECID Mapping ===")

        for ticker, secid in secids.items():
            print(f"{ticker:8s} -> {secid}")

        total = (
            len(dates)
            * len(secids)
            * len(SELECTION_METHODS)
        )

        count = 0

        # ----------------------------------------------------
        # DAILY EXECUTION
        # ----------------------------------------------------

        for date in dates:
            print(f"\n=== {date} ===")

            for ticker, secid in secids.items():

                for method in SELECTION_METHODS:
                    count += 1

                    try:
                        result = get_atm_straddle_quotes(
                            db=db,
                            secid=secid,
                            date=date,
                            selection_method=method,
                            min_open_interest=min_open_interest,
                            max_maturity_distance=max_maturity_distance,
                        )

                        result["ticker"] = ticker

                        rows.append(result)

                        print(
                            f"[{count}/{total}] "
                            f"{ticker:5s} | "
                            f"{method:16s} | "
                            f"{result['cost_vol_points']:.4f} vol pts | "
                            f"DTE={result['dte']:2d} | "
                            f"minOI={result['min_open_interest']:.0f}"
                        )

                    except ValueError as error:
                        skipped.append({
                            "date": str(date),
                            "ticker": ticker,
                            "secid": secid,
                            "selection_method": method,
                            "reason": str(error),
                        })

                        print(
                            f"[{count}/{total}] "
                            f"{ticker:5s} | "
                            f"{method:16s} | "
                            f"SKIPPED: {error}"
                        )

    finally:
        db.close()

    if not rows:
        raise ValueError(
            "No valid straddles found."
        )

    # ========================================================
    # BUILD DATAFRAMES
    # ========================================================

    daily = pd.DataFrame(rows)

    daily = daily.sort_values(
        [
            "date",
            "ticker",
            "selection_method",
        ]
    ).reset_index(drop=True)

    summary = build_summary(daily)

    comparison = build_method_comparison(daily)

    skipped_df = pd.DataFrame(
        skipped,
        columns=[
            "date",
            "ticker",
            "secid",
            "selection_method",
            "reason",
        ],
    )

    # ========================================================
    # EXPORT
    # ========================================================

    output_dir = Path(output)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    daily_file = (
        output_dir
        / f"straddle_costs_daily_{year}.csv"
    )

    summary_file = (
        output_dir
        / f"straddle_costs_summary_{year}.csv"
    )

    comparison_file = (
        output_dir
        / f"straddle_costs_comparison_{year}.csv"
    )

    skipped_file = (
        output_dir
        / f"straddle_costs_skipped_{year}.csv"
    )

    daily.to_csv(
        daily_file,
        index=False,
    )

    summary.to_csv(
        summary_file,
        index=False,
    )

    comparison.to_csv(
        comparison_file,
        index=False,
    )

    skipped_df.to_csv(
        skipped_file,
        index=False,
    )

    # ========================================================
    # PRINT RESULTS
    # ========================================================

    print("\n" + "=" * 80)
    print("SUMMARY BY TICKER AND METHOD")
    print("=" * 80)

    display_columns = [
        "ticker",
        "selection_method",
        "observations",
        "median_cost_vol_pts",
        "mean_cost_vol_pts",
        "p95_cost_vol_pts",
        "median_half_spread_pct",
        "median_dte",
        "median_min_oi",
    ]

    print(
        summary[display_columns].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    # --------------------------------------------------------
    # PAIRED METHOD COMPARISON
    # --------------------------------------------------------

    if not comparison.empty:
        print("\n" + "=" * 80)
        print("PAIRED METHOD COMPARISON")
        print("=" * 80)

        paired_summary = (
            comparison.groupby("ticker")
            .agg(
                paired_dates=("date", "size"),
                median_cost_reduction_pct=(
                    "cost_reduction_pct",
                    "median",
                ),
                mean_cost_reduction_pct=(
                    "cost_reduction_pct",
                    "mean",
                ),
                median_dte_difference=(
                    "dte_difference",
                    "median",
                ),
                same_expiration_count=(
                    "same_expiration",
                    "sum",
                ),
                same_strike_count=(
                    "same_strike",
                    "sum",
                ),
            )
            .reset_index()
        )

        print(
            paired_summary.to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )

    print("\n=== EXPORT COMPLETE ===")
    print(f"Daily observations: {len(daily)}")
    print(f"Skipped observations: {len(skipped_df)}")
    print(f"Paired comparisons: {len(comparison)}")

    print("\nSaved files:")
    print(daily_file)
    print(summary_file)
    print(comparison_file)
    print(skipped_file)

    return daily, summary, comparison


# ============================================================
# MAIN
# ============================================================

def main():
    args = get_args()

    compare_costs(
        start=args.start,
        end=args.end,
        tickers=args.tickers,
        output=args.output,
        min_open_interest=args.min_open_interest,
        max_maturity_distance=args.max_maturity_distance,
    )


if __name__ == "__main__":
    main()
