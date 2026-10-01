import pandas as pd

from .security_lookup import (
    resolve_tickers_to_permnos,
)

from .membership_csv import (
    get_csv_constituents,
)

from .compustat_membership import (
    get_compustat_index_constituents,
)

from .security_lookup import (
    attach_crsp_tickers,
)


def get_sp500_constituents(
    db,
    date,
):
    """
    Historical S&P 500 membership from CRSP.
    """

    date = pd.Timestamp(
        date
    ).date()

    members = db.raw_sql(
        f"""
        SELECT DISTINCT
            permno
        FROM crsp.dsp500list_v2
        WHERE mbrstartdt <= '{date}'
          AND mbrenddt >= '{date}'
        """
    )

    if members.empty:
        raise ValueError(
            f"No S&P 500 constituents found for {date}."
        )

    members["permno"] = pd.to_numeric(
        members["permno"],
        errors="coerce",
    )

    members = members.dropna(
        subset=["permno"]
    )

    members["permno"] = (
        members["permno"]
        .astype(int)
    )

    result = attach_crsp_tickers(
        db=db,
        permnos=(
            members["permno"]
            .unique()
            .tolist()
        ),
        date=date,
    )

    if result.empty:
        raise ValueError(
            f"S&P 500 membership exists on {date}, "
            f"but CRSP ticker mapping returned no rows."
        )

    return result


def get_wrds_index_constituents(
    db,
    index,
    date,
):
    """
    Resolve historical constituents from WRDS.

    SPX:
        dedicated CRSP membership table

    Other indices:
        generic Compustat membership discovery
    """

    index = (
        str(index)
        .upper()
        .strip()
    )

    if index in {
        "SPX",
        "SP500",
        "S&P500",
        "S&P 500",
    }:
        return get_sp500_constituents(
            db=db,
            date=date,
        )

    try:
        return get_compustat_index_constituents(
            db=db,
            index=index,
            date=date,
        )

    except ValueError:
        return None


def get_index_constituents(
    db,
    index,
    date,
    membership=None,
    tickers=None,
):
    """
    Resolve historical constituents.

    Priority:
        1. explicit ticker universe
        2. automatic WRDS historical membership
        3. CSV historical membership fallback
    """
    index = str(index).upper().strip()
    date = pd.Timestamp(date).date()

    if tickers:
        return resolve_tickers_to_permnos(
            db=db,
            tickers=tickers,
            date=date,
        )

    wrds_result = get_wrds_index_constituents(
        db=db,
        index=index,
        date=date,
    )
    if wrds_result is not None and not wrds_result.empty:
        return wrds_result

    if membership is not None:
        csv_result = get_csv_constituents(
            db=db,
            membership=membership,
            index=index,
            date=date,
        )
        if csv_result is not None and not csv_result.empty:
            return csv_result

    raise ValueError(
        f"Could not determine historical constituents for {index} on {date}."
    )
