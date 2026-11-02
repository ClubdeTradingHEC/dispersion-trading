import argparse
from pathlib import Path

import pandas as pd

from .wrds_connection import get_wrds_connection
from .index_constituents import get_index_constituents
from .index_weights import get_index_weights
from .membership_csv import load_membership_file


# ============================================================
# CLI
# ============================================================


def get_args():
    parser = argparse.ArgumentParser(
        description=(
            "Export daily constituent returns and index weights."
        )
    )

    parser.add_argument(
        "--index",
        required=True,
        type=str,
        help="Index ticker, e.g. DJIA, SPX, NDX",
    )

    parser.add_argument(
        "--start",
        required=True,
        type=str,
        help="Start date in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--end",
        required=True,
        type=str,
        help="End date in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--weighting",
        choices=[
            "price",
            "market_cap",
            "equal",
        ],
        required=True,
        help=(
            "Index weighting method. "
            "Use price for DJIA, market_cap for SPX/NDX."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        type=str,
        help="Output CSV path",
    )

    parser.add_argument(
        "--membership-file",
        default="data/index_membership.csv",
        type=str,
        help=(
            "Optional historical membership CSV. "
            "Used as fallback when applicable."
        ),
    )

    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help=(
            "Optional explicit constituent tickers. "
            "If supplied, these override automatic membership."
        ),
    )

    return parser.parse_args()


# ============================================================
# TRADING DATES
# ============================================================


def get_trading_dates(
    db,
    start,
    end,
):
    """
    Return CRSP trading dates in the requested interval.
    """

    df = db.raw_sql(
        f"""
        SELECT DISTINCT
            dlycaldt AS date
        FROM crsp.dsf_v2
        WHERE dlycaldt >= '{start}'
          AND dlycaldt <= '{end}'
        ORDER BY dlycaldt
        """,
        date_cols=["date"],
    )

    if df.empty:
        return []

    return (
        df["date"]
        .dt.date
        .tolist()
    )


# ============================================================
# DAILY RETURNS
# ============================================================


def get_daily_returns(
    db,
    permnos,
    date,
):
    """
    Pull CRSP same-day returns for the requested PERMNOs.
    """

    permnos = [
        int(x)
        for x in permnos
        if pd.notna(x)
    ]

    permnos = list(
        dict.fromkeys(
            permnos
        )
    )

    if not permnos:
        return pd.DataFrame(
            columns=[
                "permno",
                "daily_return",
            ]
        )

    permno_sql = ",".join(
        str(x)
        for x in permnos
    )

    df = db.raw_sql(
        f"""
        SELECT
            permno,
            dlyret AS daily_return
        FROM crsp.dsf_v2
        WHERE dlycaldt = '{date}'
          AND permno IN ({permno_sql})
          AND dlyret IS NOT NULL
        """
    )

    if df.empty:
        return pd.DataFrame(
            columns=[
                "permno",
                "daily_return",
            ]
        )

    df["permno"] = pd.to_numeric(
        df["permno"],
        errors="coerce",
    )

    df["daily_return"] = pd.to_numeric(
        df["daily_return"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "permno",
            "daily_return",
        ]
    ).copy()

    df["permno"] = (
        df["permno"]
        .astype(int)
    )

    return (
        df[
            [
                "permno",
                "daily_return",
            ]
        ]
        .drop_duplicates(
            subset=[
                "permno"
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# EXPORT ENGINE
# ============================================================


def export_returns_weights(
    index,
    start,
    end,
    weighting,
    output,
    membership_file="data/index_membership.csv",
    tickers=None,
):
    """
    Export a long-format daily dataset containing:

        date
        index
        ticker
        permno
        daily_return
        weight

    Plus price / dlycap when available.
    """

    index = (
        str(index)
        .upper()
        .strip()
    )

    start_date = pd.Timestamp(
        start
    ).date()

    end_date = pd.Timestamp(
        end
    ).date()

    if end_date < start_date:
        raise ValueError(
            "--end must be greater than or equal to --start."
        )

    # --------------------------------------------------------
    # Optional membership CSV
    # --------------------------------------------------------

    membership = None

    if (
        tickers is None
        and membership_file is not None
    ):
        membership_path = Path(
            membership_file
        )

        if membership_path.exists():
            membership = load_membership_file(
                membership_file
            )

    # --------------------------------------------------------
    # WRDS connection
    # --------------------------------------------------------

    db = get_wrds_connection()

    try:
        trading_dates = get_trading_dates(
            db=db,
            start=start_date,
            end=end_date,
        )

        if not trading_dates:
            raise ValueError(
                "No CRSP trading dates found in the requested interval."
            )

        print(
            "\n=== Returns / Weights Export ==="
        )

        print(
            f"Index:       {index}"
        )

        print(
            f"Weighting:   {weighting}"
        )

        print(
            f"Start:       {start_date}"
        )

        print(
            f"End:         {end_date}"
        )

        print(
            f"Trading days:{len(trading_dates)}"
        )

        print()

        rows = []

        # ====================================================
        # Process each date
        # ====================================================

        for i, date in enumerate(
            trading_dates,
            start=1,
        ):
            print(
                f"[{i}/{len(trading_dates)}] {date}"
            )

            try:
                # --------------------------------------------
                # Historical constituents
                # --------------------------------------------

                constituents = get_index_constituents(
                    db=db,
                    index=index,
                    date=date,
                    membership=membership,
                    tickers=tickers,
                )

                if constituents.empty:
                    print(
                        "    skipped: no constituents"
                    )
                    continue

                # --------------------------------------------
                # Same-day index weights
                # --------------------------------------------

                weights = get_index_weights(
                    db=db,
                    constituents=constituents,
                    date=date,
                    method=weighting,
                )

                if weights.empty:
                    print(
                        "    skipped: no weights"
                    )
                    continue

                # --------------------------------------------
                # Same-day CRSP returns
                # --------------------------------------------

                returns = get_daily_returns(
                    db=db,
                    permnos=(
                        weights[
                            "permno"
                        ]
                        .astype(int)
                        .tolist()
                    ),
                    date=date,
                )

                # --------------------------------------------
                # Combine
                # --------------------------------------------

                daily = weights.merge(
                    returns,
                    on="permno",
                    how="left",
                )

                daily["date"] = date
                daily["index"] = index

                # --------------------------------------------
                # QA
                # --------------------------------------------

                n_constituents = len(
                    weights
                )

                n_returns = (
                    daily[
                        "daily_return"
                    ]
                    .notna()
                    .sum()
                )

                weight_sum = (
                    daily[
                        "weight"
                    ]
                    .sum()
                )

                print(
                    f"    constituents: "
                    f"{n_constituents}"
                )

                print(
                    f"    returns:      "
                    f"{n_returns}/{n_constituents}"
                )

                print(
                    f"    weight sum:   "
                    f"{weight_sum:.6f}"
                )

                # --------------------------------------------
                # Output columns
                # --------------------------------------------

                keep_columns = [
                    "date",
                    "index",
                    "ticker",
                    "permno",
                    "daily_return",
                    "weight",
                ]

                if "price" in daily.columns:
                    keep_columns.append(
                        "price"
                    )

                if "dlycap" in daily.columns:
                    keep_columns.append(
                        "dlycap"
                    )

                rows.append(
                    daily[
                        keep_columns
                    ]
                )

            except ValueError as e:
                print(
                    f"    skipped: {e}"
                )

        # ====================================================
        # Build output
        # ====================================================

        if not rows:
            raise ValueError(
                "No successful daily observations."
            )

        result = pd.concat(
            rows,
            ignore_index=True,
        )

        result = (
            result
            .sort_values(
                [
                    "date",
                    "ticker",
                ]
            )
            .reset_index(
                drop=True
            )
        )

        # ====================================================
        # Save
        # ====================================================

        output_path = Path(
            output
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        result.to_csv(
            output_path,
            index=False,
        )

        # ====================================================
        # Final summary
        # ====================================================

        print(
            "\n=== Export Summary ==="
        )

        print(
            f"Rows:              "
            f"{len(result):,}"
        )

        print(
            f"Dates:             "
            f"{result['date'].nunique()}"
        )

        print(
            f"Unique securities: "
            f"{result['permno'].nunique()}"
        )

        print(
            f"Missing returns:   "
            f"{result['daily_return'].isna().sum():,}"
        )

        print(
            f"Saved to:          "
            f"{output_path}"
        )

        return result

    finally:
        db.close()


# ============================================================
# MAIN
# ============================================================


def main():
    args = get_args()

    export_returns_weights(
        index=args.index,
        start=args.start,
        end=args.end,
        weighting=args.weighting,
        output=args.output,
        membership_file=args.membership_file,
        tickers=args.tickers,
    )


if __name__ == "__main__":
    main()