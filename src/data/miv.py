from pathlib import Path

import pandas as pd

from .wrds_connection import get_wrds_connection

from .index_config import (
    get_index_config,
    normalize_index,
)

from .index_constituents import get_index_constituents
from .membership_csv import load_membership_file

from .index_weights import get_index_weights
from .index_return import get_index_returns

from .security_lookup import (
    get_optionmetrics_secid,
    get_index_secid,
)

from .optionmetrics_iv import get_iv

from .correlation import (
    daily_to_monthly,
    get_stock_index_correlation,
)


# ============================================================
# SETTINGS
# ============================================================


def get_optional_index_config(index):
    """
    Return configured index metadata when available.

    Unknown indices are still allowed.
    """

    try:
        return get_index_config(index)

    except ValueError:
        return {}


def normalize_index_name(index):
    return normalize_index(
        str(index).upper().strip()
    )


def resolve_index_settings(
    index,
    benchmark=None,
    weighting="auto",
):
    """
    Normalize index and resolve benchmark + weighting in one place.
    """

    index = normalize_index_name(index)

    config = get_optional_index_config(
        index
    )

    if benchmark is None:
        benchmark = config.get(
            "benchmark",
            index,
        )

    benchmark = (
        str(benchmark)
        .upper()
        .strip()
    )

    if (
        weighting is None
        or weighting == "auto"
    ):
        weighting = config.get(
            "weighting"
        )

        if weighting is None:
            raise ValueError(
                f"Weighting method could not be inferred "
                f"for index '{index}'. "
                f"Provide price, market_cap, or equal."
            )

    return {
        "index": index,
        "benchmark": benchmark,
        "weighting": weighting,
    }


# ============================================================
# MEMBERSHIP
# ============================================================


def load_optional_membership(
    membership_file,
    tickers=None,
):
    """
    Load historical membership CSV only when needed.

    Explicit ticker baskets do not require a membership file.
    """

    if tickers is not None:
        return None

    if membership_file is None:
        return None

    path = Path(
        membership_file
    )

    if not path.exists():
        return None

    return load_membership_file(
        membership_file
    )


# ============================================================
# BENCHMARK RETURNS
# ============================================================


def prepare_benchmark_monthly_returns(
    db,
    benchmark,
    signal_date,
    months,
):
    """
    Load benchmark returns over the completed-month
    correlation window.
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
        .date()
    )

    end_date = (
        end_month
        .start_time
        - pd.Timedelta(days=1)
    ).date()

    (
        benchmark_daily,
        benchmark_secid,
        benchmark_source,
    ) = get_index_returns(
        db=db,
        ticker=benchmark,
        start_date=start_date,
        end_date=end_date,
    )

    if benchmark_daily.empty:
        raise ValueError(
            f"No benchmark returns found for {benchmark}."
        )

    benchmark_monthly = (
        daily_to_monthly(
            benchmark_daily[
                [
                    "date",
                    "return",
                ]
            ]
        )
        .rename(
            columns={
                "return": "benchmark_return"
            }
        )
    )

    return (
        benchmark_monthly,
        benchmark_secid,
        benchmark_source,
    )


# ============================================================
# CONSTITUENT OBSERVATION
# ============================================================


def compute_constituent_observation(
    db,
    row,
    benchmark_monthly,
    signal_date,
    days,
    months,
    iv_method,
):
    """
    Compute everything needed for one constituent:

        SECID
        IV
        stock/index correlation
        Marshall contribution
    """

    ticker = (
        str(row["ticker"])
        .upper()
        .strip()
    )

    permno = int(
        row["permno"]
    )

    weight = float(
        row["weight"]
    )

    secid = get_optionmetrics_secid(
        db=db,
        permno=permno,
        ticker=ticker,
        date=signal_date.date(),
        days=days,
    )

    iv = get_iv(
        db=db,
        secid=secid,
        date=signal_date.date(),
        days=days,
        method=iv_method,
    )

    correlation = (
        get_stock_index_correlation(
            db=db,
            permno=permno,
            benchmark_monthly=benchmark_monthly,
            signal_date=signal_date,
            months=months,
        )
    )

    contribution = (
        weight
        * iv
        * correlation
    )

    price = None

    if (
        "price" in row.index
        and pd.notna(
            row["price"]
        )
    ):
        price = float(
            row["price"]
        )

    market_cap = None

    if (
        "dlycap" in row.index
        and pd.notna(
            row["dlycap"]
        )
    ):
        market_cap = float(
            row["dlycap"]
        )

    return {
        "ticker": ticker,
        "permno": permno,
        "secid": secid,
        "price": price,
        "market_cap": market_cap,
        "weight": weight,
        "iv": iv,
        "correlation": correlation,
        "contribution": contribution,
    }


# ============================================================
# CORE MARSHALL MIV
# ============================================================


def compute_miv_for_date(
    db,
    membership,
    index,
    benchmark,
    date,
    days=30,
    months=36,
    weighting="auto",
    tickers=None,
    iv_method="combined_50delta",
    verbose=True,
):
    """
    Compute Marshall simplified implied volatility:

        MIV_t =
            sum_i(
                w_i,t
                * sigma_i,t
                * rho_i,m,t
            )

    The same IV methodology is applied to constituents
    and benchmark.
    """

    signal_date = pd.Timestamp(
        date
    )

    settings = resolve_index_settings(
        index=index,
        benchmark=benchmark,
        weighting=weighting,
    )

    index = settings[
        "index"
    ]

    benchmark = settings[
        "benchmark"
    ]

    weighting = settings[
        "weighting"
    ]

    # --------------------------------------------------------
    # Constituents
    # --------------------------------------------------------

    constituents = get_index_constituents(
        db=db,
        index=index,
        date=signal_date.date(),
        membership=membership,
        tickers=tickers,
    )

    if constituents.empty:
        raise ValueError(
            f"No constituents found for "
            f"{index} on {signal_date.date()}."
        )

    # --------------------------------------------------------
    # Weights
    # --------------------------------------------------------

    weights = get_index_weights(
        db=db,
        constituents=constituents,
        date=signal_date.date(),
        method=weighting,
    )

    if weights.empty:
        raise ValueError(
            f"No valid weights found for "
            f"{index} on {signal_date.date()}."
        )

    required_columns = {
        "ticker",
        "permno",
        "weight",
    }

    missing = (
        required_columns
        - set(
            weights.columns
        )
    )

    if missing:
        raise ValueError(
            "Weight DataFrame is missing: "
            + ", ".join(
                sorted(missing)
            )
        )

    # --------------------------------------------------------
    # Benchmark history
    # --------------------------------------------------------

    (
        benchmark_monthly,
        benchmark_secid,
        benchmark_source,
    ) = prepare_benchmark_monthly_returns(
        db=db,
        benchmark=benchmark,
        signal_date=signal_date,
        months=months,
    )

    # --------------------------------------------------------
    # Constituents
    # --------------------------------------------------------

    results = []

    for _, row in weights.iterrows():

        ticker = (
            str(row["ticker"])
            .upper()
            .strip()
        )

        if verbose:
            print(
                f"Processing {ticker}..."
            )

        try:
            observation = (
                compute_constituent_observation(
                    db=db,
                    row=row,
                    benchmark_monthly=benchmark_monthly,
                    signal_date=signal_date,
                    days=days,
                    months=months,
                    iv_method=iv_method,
                )
            )

            results.append(
                observation
            )

        except ValueError as e:

            if verbose:
                print(
                    f"  Skipped: {e}"
                )

    details = pd.DataFrame(
        results
    )

    if details.empty:
        raise ValueError(
            "No usable constituent observations."
        )

    details = (
        details
        .sort_values(
            "contribution",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # MIV
    # --------------------------------------------------------

    miv = float(
        details[
            "contribution"
        ].sum()
    )

    weight_coverage = float(
        details[
            "weight"
        ].sum()
    )

    # --------------------------------------------------------
    # Benchmark IV
    # --------------------------------------------------------

    index_iv_secid = get_index_secid(
        db=db,
        ticker=benchmark,
    )

    index_iv = get_iv(
        db=db,
        secid=index_iv_secid,
        date=signal_date.date(),
        days=days,
        method=iv_method,
    )

    # --------------------------------------------------------
    # Spread
    # --------------------------------------------------------

    spread = (
        index_iv
        - miv
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = {
        "date": signal_date.date(),
        "index": index,
        "benchmark": benchmark,
        "weighting": weighting,
        "iv_method": iv_method,

        "benchmark_secid": (
            benchmark_secid
        ),

        "benchmark_source": (
            benchmark_source
        ),

        "index_iv_secid": (
            index_iv_secid
        ),

        "index_atm_iv": (
            index_iv
        ),

        "miv": miv,

        "spread": spread,

        "spread_vol_bps": (
            spread
            * 10000
        ),

        "correlation_months": (
            months
        ),

        "iv_days": (
            days
        ),

        "constituents_used": (
            len(details)
        ),

        "constituents_expected": (
            len(weights)
        ),

        "weight_coverage": (
            weight_coverage
        ),

        "explicit_ticker_universe": (
            tickers is not None
        ),
    }

    return (
        summary,
        details,
    )


# ============================================================
# PUBLIC FUNCTION
# ============================================================


def run_miv(
    index,
    date,
    benchmark=None,
    days=30,
    months=36,
    membership_file="data/index_membership.csv",
    weighting="auto",
    tickers=None,
    iv_method="combined_50delta",
    verbose=True,
):
    """
    Public one-date MIV function.

    run_dispersion.py should be the CLI entry point.
    """

    settings = resolve_index_settings(
        index=index,
        benchmark=benchmark,
        weighting=weighting,
    )

    membership = (
        load_optional_membership(
            membership_file=membership_file,
            tickers=tickers,
        )
    )

    db = get_wrds_connection()

    try:
        return compute_miv_for_date(
            db=db,
            membership=membership,
            index=settings["index"],
            benchmark=settings["benchmark"],
            date=date,
            days=days,
            months=months,
            weighting=settings["weighting"],
            tickers=tickers,
            iv_method=iv_method,
            verbose=verbose,
        )

    finally:
        db.close()