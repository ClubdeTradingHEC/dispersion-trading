import pandas as pd

from .index_discovery import discover_optionmetrics_index


def get_index_returns(
    db,
    ticker,
    start_date,
    end_date,
):
    """
    Load daily OptionMetrics index returns for an inclusive date range.

    Returns:
        (dataframe, secid, source)
    """
    ticker = str(ticker).upper().strip()

    info = discover_optionmetrics_index(
        db=db,
        ticker=ticker,
    )
    secid = info["secid"]

    df = db.raw_sql(
        f"""
        SELECT
            date,
            close,
            return
        FROM optionm.secprd
        WHERE secid = {secid}
          AND date >= '{start_date}'
          AND date <= '{end_date}'
        ORDER BY date
        """,
        date_cols=["date"],
    )

    if df.empty:
        raise ValueError(
            f"No OptionMetrics index returns found for {ticker} "
            f"between {start_date} and {end_date}."
        )

    df["return"] = pd.to_numeric(df["return"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "return"]).copy()

    if df.empty:
        raise ValueError(
            f"OptionMetrics returned no valid index returns for {ticker} "
            f"between {start_date} and {end_date}."
        )

    return df, int(secid), "OptionMetrics"
