from difflib import SequenceMatcher
import re

import pandas as pd


# ============================================================
# MATCHING CONSTANTS
# ============================================================


NAME_SEQUENCE_WEIGHT = 0.70
NAME_TOKEN_WEIGHT = 0.30

DEFAULT_MIN_SCORE = 0.72
HIGH_CONFIDENCE_SCORE = 0.95
AMBIGUITY_MARGIN = 0.03


# ============================================================
# HELPERS
# ============================================================


def normalize_index_name(value):
    """
    Normalize index names so OptionMetrics and Compustat
    names can be compared consistently.
    """

    if value is None:
        return ""

    value = (
        str(value)
        .upper()
        .strip()
    )

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        value,
    )

    removable_words = {
        "INDEX",
        "IDX",
    }

    tokens = [
        token
        for token in value.split()
        if token not in removable_words
    ]

    return " ".join(
        tokens
    )


def similarity_score(a, b):
    """
    Combined sequence similarity and token overlap.

    Score:
        70% sequence similarity
        30% token Jaccard overlap
    """

    a = normalize_index_name(
        a
    )

    b = normalize_index_name(
        b
    )

    if not a or not b:
        return 0.0

    sequence_score = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()

    a_tokens = set(
        a.split()
    )

    b_tokens = set(
        b.split()
    )

    if (
        not a_tokens
        or not b_tokens
    ):
        token_score = 0.0

    else:
        token_score = (
            len(
                a_tokens
                & b_tokens
            )
            / len(
                a_tokens
                | b_tokens
            )
        )

    return (
        NAME_SEQUENCE_WEIGHT
        * sequence_score
        + NAME_TOKEN_WEIGHT
        * token_score
    )


# ============================================================
# OPTIONMETRICS INDEX DISCOVERY
# ============================================================


def discover_optionmetrics_index(
    db,
    ticker,
):
    """
    Resolve an index ticker to OptionMetrics metadata.

    Returns:
        {
            "secid": int,
            "ticker": str,
            "indexnam": str | None,
            "cusip": str | None,
        }

    Search order:
        1. optionm.indexd
        2. optionm.securd fallback
    """

    ticker = (
        str(ticker)
        .upper()
        .strip()
    )

    # --------------------------------------------------------
    # Preferred source: optionm.indexd
    # --------------------------------------------------------

    df = db.raw_sql(
        f"""
        SELECT
            secid,
            ticker,
            indexnam,
            cusip,
            exchange_d,
            issue_type,
            class
        FROM optionm.indexd
        WHERE UPPER(ticker) = '{ticker}'
        ORDER BY secid
        """
    )

    # --------------------------------------------------------
    # Fallback: optionm.securd
    # --------------------------------------------------------

    if df.empty:
        df = db.raw_sql(
            f"""
            SELECT
                secid,
                ticker,
                NULL AS indexnam,
                cusip,
                exchange_d,
                issue_type,
                class
            FROM optionm.securd
            WHERE UPPER(ticker) = '{ticker}'
              AND index_flag = '1'
            ORDER BY secid
            """
        )

    if df.empty:
        raise ValueError(
            f"Index ticker {ticker} was not found "
            f"in OptionMetrics."
        )

    df["secid"] = pd.to_numeric(
        df["secid"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["secid"]
    )

    if df.empty:
        raise ValueError(
            f"OptionMetrics returned no valid SECID "
            f"for index ticker {ticker}."
        )

    if len(df) > 1:
        raise ValueError(
            f"Multiple OptionMetrics index rows found "
            f"for {ticker}: "
            f"{df['secid'].astype(int).tolist()}"
        )

    row = df.iloc[0]

    return {
        "secid": int(
            row["secid"]
        ),

        "ticker": (
            str(
                row["ticker"]
            )
            .upper()
            .strip()
        ),

        "indexnam": (
            str(
                row["indexnam"]
            )
            if pd.notna(
                row["indexnam"]
            )
            else None
        ),

        "cusip": (
            str(
                row["cusip"]
            )
            if pd.notna(
                row["cusip"]
            )
            else None
        ),
    }


# ============================================================
# OPTIONMETRICS PRICE AVAILABILITY
# ============================================================


def has_optionmetrics_index_prices(
    db,
    ticker,
    start=None,
    end=None,
):
    """
    Check whether OptionMetrics secprd contains price
    observations for an index.

    Optional date bounds may be provided.
    """

    info = discover_optionmetrics_index(
        db=db,
        ticker=ticker,
    )

    secid = info[
        "secid"
    ]

    conditions = [
        f"secid = {secid}",
    ]

    if start is not None:
        conditions.append(
            f"date >= "
            f"'{pd.Timestamp(start).date()}'"
        )

    if end is not None:
        conditions.append(
            f"date <= "
            f"'{pd.Timestamp(end).date()}'"
        )

    where_sql = " AND ".join(
        conditions
    )

    df = db.raw_sql(
        f"""
        SELECT
            COUNT(*) AS n
        FROM optionm.secprd
        WHERE {where_sql}
        """
    )

    if df.empty:
        return False

    return (
        int(
            df.iloc[0]["n"]
        )
        > 0
    )


# ============================================================
# COMPUSTAT INDEX CANDIDATES
# ============================================================


def get_compustat_index_candidates(
    db,
):
    """
    Retrieve Compustat indices for which constituent
    history is indicated as available.
    """

    df = db.raw_sql(
        """
        SELECT
            gvkeyx,
            conm,
            tic,
            tici,
            idxcstflg,
            idxstat,
            indexcat,
            indexgeo,
            indextype
        FROM comp.idx_index
        WHERE idxcstflg = 'Y'
        """
    )

    if df.empty:
        raise ValueError(
            "No Compustat constituent indices were found."
        )

    return df


# ============================================================
# COMPUSTAT MATCHING
# ============================================================


def _score_compustat_candidates(
    candidates,
    index_ticker,
    optionmetrics_name,
):
    """
    Add name/ticker matching scores to the Compustat
    candidate table.
    """

    candidates = candidates.copy()

    candidates[
        "name_score"
    ] = (
        candidates[
            "conm"
        ]
        .apply(
            lambda x: similarity_score(
                optionmetrics_name,
                x,
            )
        )
    )

    candidates[
        "ticker_score"
    ] = 0.0

    for column in [
        "tic",
        "tici",
    ]:
        exact = (
            candidates[
                column
            ]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
            == index_ticker
        )

        candidates.loc[
            exact,
            "ticker_score",
        ] = 1.0

    candidates[
        "score"
    ] = (
        candidates[
            [
                "name_score",
                "ticker_score",
            ]
        ]
        .max(
            axis=1
        )
    )

    return (
        candidates
        .sort_values(
            "score",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )


def _candidate_preview(
    candidates,
    n=5,
):
    """
    Small candidate table for error messages.
    """

    columns = [
        "gvkeyx",
        "conm",
        "tic",
        "tici",
        "score",
    ]

    available_columns = [
        column
        for column in columns
        if column in candidates.columns
    ]

    return candidates[
        available_columns
    ].head(
        n
    )


# ============================================================
# GENERIC COMPUSTAT INDEX DISCOVERY
# ============================================================


def discover_compustat_index(
    db,
    index_ticker,
    min_score=DEFAULT_MIN_SCORE,
    verbose=False,
):
    """
    Map an OptionMetrics index ticker to a Compustat GVKEYX.

    Example:
        NDX
            ->
        OptionMetrics:
            NASDAQ 100 INDEX
            ->
        Compustat:
            Nasdaq 100
            ->
        gvkeyx = 000208
    """

    index_ticker = (
        str(index_ticker)
        .upper()
        .strip()
    )

    optionm = discover_optionmetrics_index(
        db=db,
        ticker=index_ticker,
    )

    optionmetrics_name = (
        optionm["indexnam"]
        or index_ticker
    )

    candidates = (
        get_compustat_index_candidates(
            db=db,
        )
        .copy()
    )

    if candidates.empty:
        raise ValueError(
            "No Compustat index candidates available."
        )

    candidates = _score_compustat_candidates(
        candidates=candidates,
        index_ticker=index_ticker,
        optionmetrics_name=optionmetrics_name,
    )

    best = candidates.iloc[0]

    best_score = float(
        best["score"]
    )

    # --------------------------------------------------------
    # Minimum confidence check
    # --------------------------------------------------------

    if (
        best_score
        < min_score
    ):
        preview = _candidate_preview(
            candidates
        )

        raise ValueError(
            f"Could not confidently map "
            f"{index_ticker} "
            f"({optionmetrics_name}) "
            f"to a Compustat index.\n"
            f"Best candidates:\n"
            f"{preview.to_string(index=False)}"
        )

    # --------------------------------------------------------
    # Ambiguity check
    # --------------------------------------------------------

    if len(
        candidates
    ) > 1:
        second = (
            candidates
            .iloc[1]
        )

        second_score = float(
            second["score"]
        )

        if (
            best_score
            < HIGH_CONFIDENCE_SCORE
            and abs(
                best_score
                - second_score
            )
            < AMBIGUITY_MARGIN
        ):
            preview = _candidate_preview(
                candidates
            )

            raise ValueError(
                f"Compustat index mapping for "
                f"{index_ticker} is ambiguous.\n"
                f"{preview.to_string(index=False)}"
            )

    if verbose:
        print(
            f"Compustat index match: "
            f"{index_ticker} -> "
            f"{best['conm']} "
            f"(gvkeyx={best['gvkeyx']}, "
            f"score={best_score:.3f})"
        )

    return {
        "index_ticker": (
            index_ticker
        ),

        "optionmetrics_name": (
            optionmetrics_name
        ),

        "optionmetrics_secid": (
            int(
                optionm[
                    "secid"
                ]
            )
        ),

        "gvkeyx": (
            str(
                best[
                    "gvkeyx"
                ]
            )
        ),

        "compustat_name": (
            str(
                best[
                    "conm"
                ]
            )
        ),

        "score": (
            best_score
        ),
    }


# ============================================================
# GENERIC DISCOVERY WRAPPER
# ============================================================


def discover_index(
    db,
    ticker,
    verbose=False,
):
    """
    Return combined OptionMetrics and, when available,
    Compustat index metadata.
    """

    optionm = (
        discover_optionmetrics_index(
            db=db,
            ticker=ticker,
        )
    )

    result = {
        "ticker": (
            optionm[
                "ticker"
            ]
        ),

        "secid": (
            optionm[
                "secid"
            ]
        ),

        "optionmetrics_name": (
            optionm[
                "indexnam"
            ]
        ),

        "cusip": (
            optionm[
                "cusip"
            ]
        ),

        "gvkeyx": None,
        "compustat_name": None,
        "compustat_score": None,
    }

    try:
        comp = (
            discover_compustat_index(
                db=db,
                index_ticker=ticker,
                verbose=verbose,
            )
        )

    except ValueError:
        return result

    result.update(
        {
            "gvkeyx": (
                comp[
                    "gvkeyx"
                ]
            ),

            "compustat_name": (
                comp[
                    "compustat_name"
                ]
            ),

            "compustat_score": (
                comp[
                    "score"
                ]
            ),
        }
    )

    return result