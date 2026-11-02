
import argparse

import numpy as np
import pandas as pd


def validate_costs(path, top=5):
    df = pd.read_csv(path)

    required = [
        "ticker", "date", "dte",
        "call_delta", "put_delta",
        "call_bid", "call_ask",
        "put_bid", "put_ask",
        "straddle_mid",
        "half_spread_usd",
        "half_spread_pct",
        "vega_usd_per_vol_point",
        "cost_vol_points",
        "contract_size",
    ]

    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year

    numeric = [x for x in required if x not in ("ticker", "date")]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Recalculate quoted execution costs.
    df["calculated_mid"] = (
        df["call_bid"] + df["call_ask"]
        + df["put_bid"] + df["put_ask"]
    ) / 2

    df["calculated_half_spread"] = (
        df["call_ask"] - df["call_bid"]
        + df["put_ask"] - df["put_bid"]
    ) / 2

    df["calculated_cost_vol"] = (
        df["calculated_half_spread"]
        / df["vega_usd_per_vol_point"]
    )

    df["cost_error"] = (
        df["cost_vol_points"] - df["calculated_cost_vol"]
    ).abs()

    # Basic quality checks.
    df["valid_quotes"] = (
        (df["call_bid"] > 0)
        & (df["put_bid"] > 0)
        & (df["call_ask"] > df["call_bid"])
        & (df["put_ask"] > df["put_bid"])
    )

    df["valid_deltas"] = (
        df["call_delta"].between(0.40, 0.60)
        & df["put_delta"].between(-0.60, -0.40)
    )

    df["valid_maturity"] = df["dte"].between(20, 45)

    df["valid_vega"] = (
        np.isfinite(df["vega_usd_per_vol_point"])
        & (df["vega_usd_per_vol_point"] > 0)
    )

    df["valid_arithmetic"] = (
        np.isfinite(df["cost_error"])
        & (df["cost_error"] < 1e-8)
        & np.isclose(
            df["straddle_mid"],
            df["calculated_mid"],
            rtol=1e-8,
            atol=1e-8,
        )
        & np.isclose(
            df["half_spread_usd"],
            df["calculated_half_spread"],
            rtol=1e-8,
            atol=1e-8,
        )
    )

    checks = [
        "valid_quotes",
        "valid_deltas",
        "valid_maturity",
        "valid_vega",
        "valid_arithmetic",
    ]

    df["passes_qa"] = df[checks].all(axis=1)

    print("\n=== QA Summary ===")
    print(f"Observations:      {len(df)}")
    print(f"Passed QA:         {df['passes_qa'].sum()}")
    print(f"Failed QA:         {(~df['passes_qa']).sum()}")

    for col in checks:
        print(f"{col:20s} {df[col].sum()}/{len(df)}")

    # Cost distribution per ticker.
    summary = (
        df.groupby(["year", "ticker"])
        .agg(
            observations=("cost_vol_points", "size"),
            median_cost=("cost_vol_points", "median"),
            mean_cost=("cost_vol_points", "mean"),
            p95_cost=("cost_vol_points", lambda x: x.quantile(0.95)),
            max_cost=("cost_vol_points", "max"),
            median_spread_pct=("half_spread_pct", "median"),
        )
        .reset_index()
    )

    print("\n=== Costs by ticker ===")
    print(summary.to_string(index=False, float_format="%.4f"))

    columns = [
        "date", "dte", "call_delta", "put_delta",
        "straddle_mid", "half_spread_usd",
        "half_spread_pct", "vega_usd_per_vol_point",
        "cost_vol_points",
    ]

    for ticker, group in df.groupby("ticker"):
        print(f"\n=== {ticker}: {top} most expensive dates ===")

        expensive = group.nlargest(top, "cost_vol_points")
        print(
            expensive[columns].to_string(
                index=False,
                float_format="%.4f",
            )
        )

    if not df["passes_qa"].all():
        print("\n=== Failed observations ===")
        print(
            df.loc[~df["passes_qa"], ["ticker", "date"] + checks]
            .to_string(index=False)
        )

    return df, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/transaction_costs/straddle_costs_daily_2019.csv",
    )
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    validate_costs(args.input, args.top)


if __name__ == "__main__":
    main()
