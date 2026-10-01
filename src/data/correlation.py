import pandas as pd


def get_stock_daily_returns(
    db,
    permno,
    start_date,
    end_date,
):
    """
    Pull CRSP daily stock returns.
    """

    df = db.raw_sql(
        f"""
        SELECT
            dlycaldt AS date,
            dlyret AS return
        FROM crsp.dsf_v2
        WHERE permno = {int(permno)}
          AND dlycaldt >= '{start_date}'
          AND dlycaldt < '{end_date}'
          AND dlyret IS NOT NULL
        ORDER BY dlycaldt
        """,
        date_cols=["date"],
    )

    df["return"] = pd.to_numeric(
        df["return"],
        errors="coerce",
    )

    return df.dropna(
        subset=["return"]
    )


def daily_to_monthly(df):
    """
    Compound daily returns into monthly returns:

        R_month = product(1 + R_day) - 1
    """

    df = df.copy()

    df["month"] = (
        df["date"]
        .dt.to_period("M")
    )

    return (
        df.groupby(
            "month"
        )["return"]
        .apply(
            lambda x: (1 + x).prod() - 1
        )
        .reset_index()
    )


def get_completed_month_window(
    signal_date,
    months,
):
    """
    Return the date range covering the previous
    `months` completed calendar months.

    Example:
        signal_date = 2024-01-03
        months = 36

        start = 2021-01-01
        end   = 2024-01-01

    The end date is exclusive.
    """

    signal_date = pd.Timestamp(
        signal_date
    )

    end_month = (
        signal_date
        .to_period("M")
    )

    first_month = (
        end_month
        - months
    )

    start_date = (
        first_month
        .start_time
    )

    end_date = (
        end_month
        .start_time
    )

    return (
        start_date,
        end_date,
    )


def get_stock_index_correlation(
    db,
    permno,
    benchmark_monthly,
    signal_date,
    months=36,
):
    """
    Compute stock/index correlation using the previous
    completed monthly returns.

    The benchmark monthly returns should contain:

        month
        benchmark_return
    """

    (
        start_date,
        end_date,
    ) = get_completed_month_window(
        signal_date=signal_date,
        months=months,
    )

    stock_daily = get_stock_daily_returns(
        db=db,
        permno=permno,
        start_date=start_date.date(),
        end_date=end_date.date(),
    )

    if stock_daily.empty:
        raise ValueError(
            f"No stock returns found for PERMNO {permno}."
        )

    stock_monthly = (
        daily_to_monthly(
            stock_daily
        )
        .rename(
            columns={
                "return": "stock_return"
            }
        )
    )

    merged = stock_monthly.merge(
        benchmark_monthly,
        on="month",
        how="inner",
    )

    merged = (
        merged
        .sort_values(
            "month"
        )
        .tail(
            months
        )
        .copy()
    )

    if len(merged) < months:
        raise ValueError(
            f"PERMNO {permno}: only "
            f"{len(merged)} aligned months found; "
            f"expected {months}."
        )

    correlation = (
        merged[
            "stock_return"
        ]
        .corr(
            merged[
                "benchmark_return"
            ]
        )
    )

    if pd.isna(
        correlation
    ):
        raise ValueError(
            f"Correlation could not be computed "
            f"for PERMNO {permno}."
        )

    return float(
        correlation
    )