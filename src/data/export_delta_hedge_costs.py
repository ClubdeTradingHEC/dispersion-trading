
from pathlib import Path

import pandas as pd

from .wrds_connection import get_wrds_connection


INPUT = Path(
    "data/transaction_costs/top30_2019/simulator_costs_final.csv"
)

OUTPUT = Path(
    "data/transaction_costs/top30_2019/stock_hedge_costs.csv"
)


def main():
    df = pd.read_csv(INPUT, parse_dates=["date"])

    # SPX is hedged with futures, not individual stock shares.
    stocks = df[df["permno"].notna()].copy()

    stocks["permno"] = stocks["permno"].astype(int)

    stocks = stocks[
        ["date", "ticker", "permno"]
    ].drop_duplicates()

    start = stocks["date"].min().date()
    end = stocks["date"].max().date()

    permnos = sorted(stocks["permno"].unique())
    ids = ",".join(str(x) for x in permnos)

    print(f"Period: {start} to {end}")
    print(f"Unique PERMNOs: {len(permnos)}")
    print(f"Security-date pairs: {len(stocks)}")

    db = get_wrds_connection()

    try:
        quotes = db.raw_sql(
            f"""
            SELECT
                permno,
                dlycaldt AS date,
                dlyprc,
                dlybid,
                dlyask
            FROM crsp.dsf_v2
            WHERE permno IN ({ids})
              AND dlycaldt BETWEEN '{start}' AND '{end}'
            """,
            date_cols=["date"],
        )
    finally:
        db.close()

    quotes["date"] = pd.to_datetime(quotes["date"]).dt.normalize()
    quotes["permno"] = quotes["permno"].astype(int)

    if quotes.duplicated(["date", "permno"]).any():
        raise ValueError(
            "Duplicate CRSP date/PERMNO records found."
        )

    result = stocks.merge(
        quotes,
        on=["date", "permno"],
        how="left",
        validate="one_to_one",
    )

    # Bid/ask validity.
    valid = (
        result["dlybid"].notna()
        & result["dlyask"].notna()
        & (result["dlybid"] > 0)
        & (result["dlyask"] > result["dlybid"])
    )

    result["valid_bidask"] = valid

    # Do not assign zero costs when quotes are missing.
    result["stock_mid"] = (
        result["dlybid"] + result["dlyask"]
    ) / 2

    result["half_spread_per_share_usd"] = (
        result["dlyask"] - result["dlybid"]
    ) / 2

    result["full_spread_per_share_usd"] = (
        result["dlyask"] - result["dlybid"]
    )

    result["half_spread_pct"] = (
        100
        * result["half_spread_per_share_usd"]
        / result["stock_mid"]
    )

    cost_cols = [
        "stock_mid",
        "half_spread_per_share_usd",
        "full_spread_per_share_usd",
        "half_spread_pct",
    ]

    result.loc[~valid, cost_cols] = float("nan")

    result["base_cost_100_shares_usd"] = (
        100 * result["half_spread_per_share_usd"]
    )

    result["stress_cost_100_shares_usd"] = (
        100 * result["full_spread_per_share_usd"]
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    result = result.sort_values(
        ["date", "ticker"]
    )

    result.to_csv(OUTPUT, index=False)

    print("\n=== CRSP STOCK HEDGE COSTS ===")
    print("Observations:", len(result))
    print("Valid quotes:", int(valid.sum()))
    print("Invalid/missing quotes:", int((~valid).sum()))

    print("\n=== Cost distribution ===")
    print(
        result[
            [
                "half_spread_per_share_usd",
                "half_spread_pct",
                "base_cost_100_shares_usd",
            ]
        ].describe().to_string()
    )

    print("\n=== Example ===")
    print(
        result[
            [
                "date",
                "ticker",
                "dlybid",
                "dlyask",
                "half_spread_per_share_usd",
                "valid_bidask",
            ]
        ].head(10).to_string(index=False)
    )

    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
