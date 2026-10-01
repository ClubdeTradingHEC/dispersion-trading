from pathlib import Path

import pandas as pd

from .security_lookup import (
    resolve_tickers_to_permnos,
)


DEFAULT_MEMBERSHIP_FILE = (
    "data/index_membership.csv"
)


def load_membership_file(
    path=DEFAULT_MEMBERSHIP_FILE,
):
    """
    Load interval-based historical index membership CSV.

    Required columns:
        index
        ticker
        start_date
        end_date
    """

    path = Path(
        path
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Membership file not found: {path}"
        )

    df = pd.read_csv(
        path
    )

    required = {
        "index",
        "ticker",
        "start_date",
        "end_date",
    }

    missing = (
        required
        - set(
            df.columns
        )
    )

    if missing:
        raise ValueError(
            "Membership CSV is missing columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    df["index"] = (
        df["index"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df["ticker"] = (
        df["ticker"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df["start_date"] = pd.to_datetime(
        df["start_date"],
        errors="coerce",
    )

    df["end_date"] = pd.to_datetime(
        df["end_date"],
        errors="coerce",
    )

    return df


def get_csv_constituents(
    db,
    membership,
    index,
    date,
):
    """
    Return constituents active in a historical CSV membership
    file on the requested date.

    The active ticker set is then mapped to CRSP PERMNOs.
    """

    if membership is None:
        return None

    index = (
        str(index)
        .upper()
        .strip()
    )

    date = pd.Timestamp(
        date
    )

    active = membership[
        (
            membership["index"]
            .astype(str)
            .str.upper()
            .str.strip()
            == index
        )
        & (
            membership["start_date"]
            <= date
        )
        & (
            membership["end_date"].isna()
            | (
                membership["end_date"]
                >= date
            )
        )
    ].copy()

    if active.empty:
        return None

    return resolve_tickers_to_permnos(
        db=db,
        tickers=(
            active["ticker"]
            .tolist()
        ),
        date=date,
    )