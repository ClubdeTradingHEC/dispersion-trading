from wrds_connection import get_wrds_connection


SPX_SECID = 108105


def get_atm_iv(
    db,
    secid: int,
    year: int,
    start_date: str,
    end_date: str,
):
    """
    Pull 30-day ±50-delta implied volatility from
    OptionMetrics IvyDB US.

    Returns both call and put surface observations.
    """

    table = f"optionm.vsurfd{year}"

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
        FROM {table}
        WHERE secid = {secid}
          AND date BETWEEN '{start_date}' AND '{end_date}'
          AND days = 30
          AND (
                (cp_flag = 'C' AND delta = 50)
             OR (cp_flag = 'P' AND delta = -50)
          )
        ORDER BY date, cp_flag
    """

    return db.raw_sql(query, date_cols=["date"])


def build_atm_iv(df):
    """
    Convert call/put observations into one ATM IV per date.
    """

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
        raw = get_atm_iv(
            db=db,
            secid=SPX_SECID,
            year=2024,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        print("\n=== Raw 30D ±50Δ observations ===")
        print(raw.head(10).to_string(index=False))

        atm = build_atm_iv(raw)

        print("\n=== SPX 30D ATM IV ===")
        print(atm.head(10).to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()