import pandas as pd

from wrds_connection import get_wrds_connection


TEST_DATE = "2024-01-03"

TEST_PERMNOS = {
    14593: "AAPL",
    10107: "MSFT",
    84788: "AMZN",
}


def compound_returns(x):
    """Compound daily returns into one monthly return."""
    return (1 + x).prod() - 1


def main():
    db = get_wrds_connection()

    try:
        permnos = ", ".join(
            str(p) for p in TEST_PERMNOS.keys()
        )

        # --------------------------------------------
        # 1. Pull roughly 3 years of stock returns
        # --------------------------------------------
        stocks = db.raw_sql(f"""
            SELECT
                permno,
                ticker,
                dlycaldt AS date,
                dlyret
            FROM crsp.dsf_v2
            WHERE permno IN ({permnos})
            AND dlycaldt >= '2021-01-01'
            AND dlycaldt < '2024-01-01'
            AND dlyret IS NOT NULL
            ORDER BY permno, dlycaldt
        """, date_cols=["date"])

        # --------------------------------------------
        # 2. Pull S&P 500 returns
        # --------------------------------------------
        market = db.raw_sql("""
            SELECT
                caldt AS date,
                sprtrn
            FROM crsp.dsp500p
            WHERE caldt >= '2021-01-01'
            AND caldt < '2024-01-01'
            AND sprtrn IS NOT NULL
            ORDER BY caldt
        """, date_cols=["date"])

        # --------------------------------------------
        # 3. Convert daily → monthly
        # --------------------------------------------
        stocks["month"] = stocks["date"].dt.to_period("M")
        market["month"] = market["date"].dt.to_period("M")

        stock_monthly = (
            stocks.groupby(["permno", "ticker", "month"])["dlyret"]
            .apply(compound_returns)
            .reset_index(name="stock_return")
        )

        market_monthly = (
            market.groupby("month")["sprtrn"]
            .apply(compound_returns)
            .reset_index(name="market_return")
        )

        # --------------------------------------------
        # 4. Join market and stock returns
        # --------------------------------------------
        merged = stock_monthly.merge(
            market_monthly,
            on="month",
            how="inner",
        )

        # --------------------------------------------
        # 5. Calculate stock-market correlations
        # --------------------------------------------
        correlations = (
            merged.groupby(["permno", "ticker"])
            .apply(
                lambda x: x["stock_return"].corr(
                    x["market_return"]
                )
            )
            .reset_index(name="rho_market")
        )

        counts = (
            merged.groupby(["permno", "ticker"])
            .size()
            .reset_index(name="n_months")
        )

        correlations = correlations.merge(
            counts,
            on=["permno", "ticker"],
        )

        print("\n=== 3-Year Monthly Stock-Market Correlations ===")
        print(correlations.to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()