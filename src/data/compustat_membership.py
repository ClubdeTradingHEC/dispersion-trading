import pandas as pd

from .index_discovery import (
    discover_compustat_index,
)

from .security_lookup import (
    normalize_ticker,
    sql_quote,
    resolve_compustat_tickers_to_permnos,
    resolve_cusips_to_permnos,
    attach_crsp_tickers,
)


def get_compustat_index_constituents(
    db,
    index,
    date,
    verbose=False,
):
    """
    Resolve historical index constituents through Compustat.

    Pipeline:

        index ticker
            ↓
        Compustat index discovery
            ↓
        GVKEYX
            ↓
        historical Compustat membership
            ↓
        Compustat ticker mapping
            ↓
        CRSP PERMNO
            ↓
        CUSIP fallback for unresolved names
            ↓
        contemporaneous CRSP ticker

    Returns
    -------
    pd.DataFrame
        Columns:
            ticker
            permno
    """

    date = pd.Timestamp(
        date
    ).date()

    # ========================================================
    # 1. Discover Compustat index
    # ========================================================

    discovery = discover_compustat_index(
        db=db,
        index_ticker=index,
    )

    gvkeyx = discovery[
        "gvkeyx"
    ]

    # ========================================================
    # 2. Historical membership
    # ========================================================

    membership = db.raw_sql(
        f"""
        SELECT DISTINCT
            gvkey,
            iid,
            cusip,
            conm_cst,
            "from",
            "thru"
        FROM comp.names_ix_cst
        WHERE gvkeyx = '{gvkeyx}'
          AND "from" <= '{date}'
          AND (
                "thru" IS NULL
                OR "thru" >= '{date}'
              )
          AND gvkey IS NOT NULL
          AND iid IS NOT NULL
        ORDER BY
            gvkey,
            iid
        """
    )

    if membership.empty:
        raise ValueError(
            f"No Compustat membership found for "
            f"{index} / gvkeyx={gvkeyx} "
            f"on {date}."
        )

    membership["gvkey"] = (
        membership["gvkey"]
        .astype(str)
        .str.strip()
    )

    membership["iid"] = (
        membership["iid"]
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # 3. Attach Compustat ticker
    # ========================================================

    gvkeys = (
        membership[
            "gvkey"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if not gvkeys:
        raise ValueError(
            f"No valid GVKEYs found for {index} on {date}."
        )

    gvkey_sql = ",".join(
        sql_quote(
            gvkey
        )
        for gvkey in gvkeys
    )

    securities = db.raw_sql(
        f"""
        SELECT DISTINCT
            gvkey,
            iid,
            tic
        FROM comp.security
        WHERE gvkey IN ({gvkey_sql})
        """
    )

    if securities.empty:
        raise ValueError(
            f"No Compustat security records found "
            f"for {index} on {date}."
        )

    securities["gvkey"] = (
        securities["gvkey"]
        .astype(str)
        .str.strip()
    )

    securities["iid"] = (
        securities["iid"]
        .astype(str)
        .str.strip()
    )

    securities["tic"] = (
        securities["tic"]
        .apply(
            normalize_ticker
        )
    )

    membership = membership.merge(
        securities,
        on=[
            "gvkey",
            "iid",
        ],
        how="left",
    )

    # ========================================================
    # 4. Ticker -> PERMNO
    # ========================================================

    compustat_tickers = (
        membership[
            "tic"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    ticker_map = (
        resolve_compustat_tickers_to_permnos(
            db=db,
            constituent_tickers=compustat_tickers,
            date=date,
        )
    )

    if not ticker_map.empty:
        membership = membership.merge(
            ticker_map[
                [
                    "compustat_ticker",
                    "ticker",
                    "permno",
                ]
            ],
            left_on="tic",
            right_on="compustat_ticker",
            how="left",
        )

    else:
        membership["compustat_ticker"] = None
        membership["ticker"] = None
        membership["permno"] = None

    # ========================================================
    # 5. CUSIP fallback
    # ========================================================

    unresolved_mask = (
        membership[
            "permno"
        ]
        .isna()
    )

    unresolved_cusips = (
        membership.loc[
            unresolved_mask,
            "cusip",
        ]
        .dropna()
        .astype(str)
        .str.upper()
        .str.strip()
        .unique()
        .tolist()
    )

    if unresolved_cusips:

        cusip_map = (
            resolve_cusips_to_permnos(
                db=db,
                cusips=unresolved_cusips,
                date=date,
            )
        )

        if not cusip_map.empty:

            membership["cusip"] = (
                membership[
                    "cusip"
                ]
                .astype(str)
                .str.upper()
                .str.strip()
            )

            membership = membership.merge(
                cusip_map.rename(
                    columns={
                        "permno":
                            "cusip_permno",
                    }
                ),
                on="cusip",
                how="left",
            )

            membership["permno"] = (
                membership[
                    "permno"
                ]
                .fillna(
                    membership[
                        "cusip_permno"
                    ]
                )
            )

    # ========================================================
    # 6. Keep resolved PERMNOs
    # ========================================================

    resolved = membership.dropna(
        subset=[
            "permno",
        ]
    ).copy()

    if resolved.empty:
        raise ValueError(
            f"No Compustat constituents for {index} "
            f"could be mapped to CRSP PERMNOs on {date}."
        )

    resolved["permno"] = (
        pd.to_numeric(
            resolved[
                "permno"
            ],
            errors="coerce",
        )
    )

    resolved = resolved.dropna(
        subset=[
            "permno"
        ]
    )

    resolved["permno"] = (
        resolved[
            "permno"
        ]
        .astype(int)
    )

    # ========================================================
    # 7. Attach final contemporaneous CRSP tickers
    # ========================================================

    crsp_tickers = attach_crsp_tickers(
        db=db,
        permnos=(
            resolved[
                "permno"
            ]
            .unique()
            .tolist()
        ),
        date=date,
    )

    if crsp_tickers.empty:
        raise ValueError(
            f"Resolved PERMNOs for {index} on {date}, "
            f"but no contemporaneous CRSP tickers were found."
        )

    result = (
        resolved[
            [
                "permno",
            ]
        ]
        .drop_duplicates()
        .merge(
            crsp_tickers,
            on="permno",
            how="inner",
        )
    )

    result = (
        result[
            [
                "ticker",
                "permno",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "ticker",
                "permno",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # 8. QA
    # ========================================================

    if verbose:

        n_members = len(
            membership
        )

        n_resolved = (
            membership[
                "permno"
            ]
            .notna()
            .sum()
        )

        n_final = len(
            result
        )

        print()

        print(
            f"Compustat historical membership: "
            f"{n_members} securities"
        )

        print(
            f"Mapped to PERMNO: "
            f"{n_resolved} / {n_members}"
        )

        print(
            f"Final CRSP membership: "
            f"{n_final} securities"
        )

        unresolved = membership[
            membership[
                "permno"
            ]
            .isna()
        ]

        if not unresolved.empty:

            print(
                f"WARNING: "
                f"{len(unresolved)} constituent(s) "
                f"remain unmapped:"
            )

            columns = [
                "gvkey",
                "iid",
                "tic",
                "cusip",
            ]

            available_columns = [
                column
                for column in columns
                if column in unresolved.columns
            ]

            print(
                unresolved[
                    available_columns
                ]
                .to_string(
                    index=False
                )
            )

    return result