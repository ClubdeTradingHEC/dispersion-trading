from wrds_connection import get_wrds_connection


TEST_TICKERS = ["AAPL", "MSFT", "AMZN"]


def get_secids(db, tickers):
    """Find OptionMetrics SECIDs for a list of tickers."""

    ticker_list = ", ".join(f"'{ticker}'" for ticker in tickers)

    query = f"""
        SELECT
            secid,
            ticker,
            cusip,
            index_flag,
            issue_type
        FROM optionm.securd
        WHERE ticker IN ({ticker_list})
        ORDER BY ticker
    """

    return db.raw_sql(query)


def get_atm_iv(
    db,
    secids,
    year,
    start_date,
    end_date,
):
    """
    Pull 30-day +50Δ call and -50Δ put IV
    for multiple securities.
    """

    secid_list = ", ".join(str(int(x)) for x in secids)

    query = f"""
        SELECT
            secid,
            date,
            days,
            delta,
            cp_flag,
            impl_volatility,
            impl_strike,
            dispersion
        FROM optionm.vsurfd{year}
        WHERE secid IN ({secid_list})
          AND date BETWEEN '{start_date}' AND '{end_date}'
          AND days = 30
          AND (
                (cp_flag = 'C' AND delta = 50)
             OR (cp_flag = 'P' AND delta = -50)
          )
        ORDER BY secid, date, cp_flag
    """

    return db.raw_sql(query, date_cols=["date"])


def build_atm_iv(df):
    """Average +50Δ call IV and -50Δ put IV."""

    pivot = df.pivot(
        index=["secid", "date"],
        columns="cp_flag",
        values="impl_volatility",
    ).reset_index()

    pivot["atm_iv"] = (pivot["C"] + pivot["P"]) / 2

    return pivot


def main():
    db = get_wrds_connection()

    try:
        # 1. Find SECIDs
        securities = get_secids(db, TEST_TICKERS)

        print("\n=== Test Securities ===")
        print(securities.to_string(index=False))

        secids = securities["secid"].tolist()

        # 2. Pull January 2024 IV data
        raw = get_atm_iv(
            db=db,
            secids=secids,
            year=2024,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        print("\n=== Raw 30D ±50Δ Observations ===")
        print(raw.head(20).to_string(index=False))

        # 3. Construct ATM IV
        atm = build_atm_iv(raw)

        # Add tickers back
        atm = atm.merge(
            securities[["secid", "ticker"]],
            on="secid",
            how="left",
        )

        atm = atm[
            ["date", "ticker", "secid", "C", "P", "atm_iv"]
        ]

        print("\n=== 30D ATM IV ===")
        print(atm.head(30).to_string(index=False))

        # 4. Basic QA
        print("\n=== Observations per Ticker ===")
        print(atm.groupby("ticker")["date"].count())

        print("\n=== Missing Values ===")
        print(atm[["C", "P", "atm_iv"]].isna().sum())

    finally:
        db.close()


if __name__ == "__main__":
    main()