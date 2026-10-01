import pandas as pd

from ...src.data.wrds_connection import get_wrds_connection


SEARCH_LIBRARIES = [
    "crsp",
    "comp",
    "optionm",
    "wrdsapps",
]


SEARCH_TERMS = [
    "nasdaq",
    "ndx",
    "index",
    "const",
    "member",
]


# ============================================================
# TABLE DISCOVERY
# ============================================================

def search_table_names(db):
    """
    Search WRDS libraries for tables whose names suggest
    index / constituent / Nasdaq membership data.

    Uses WRDS list_tables() rather than information_schema.
    """

    results = []

    for library in SEARCH_LIBRARIES:

        print(
            f"Scanning library: {library}"
        )

        try:
            tables = db.list_tables(
                library=library
            )

        except Exception as e:
            print(
                f"  Could not list {library}: {e}"
            )
            continue

        for table in tables:

            table_lower = (
                str(table)
                .lower()
            )

            if any(
                term in table_lower
                for term in SEARCH_TERMS
            ):
                results.append(
                    {
                        "library": library,
                        "table": table,
                    }
                )

    return pd.DataFrame(
        results
    )


# ============================================================
# COLUMN DISCOVERY
# ============================================================

def inspect_candidate_columns(
    db,
    tables,
):
    """
    Inspect candidate tables using WRDS describe_table().
    """

    results = []

    interesting_terms = [
        "permno",
        "ticker",
        "cusip",
        "gvkey",
        "index",
        "indno",
        "weight",
        "member",
        "start",
        "end",
        "date",
    ]

    for _, row in tables.iterrows():

        library = row["library"]
        table = row["table"]

        try:
            description = db.describe_table(
                library=library,
                table=table,
            )

            if description is None:
                continue

            # WRDS usually returns a DataFrame with a name column
            if isinstance(
                description,
                pd.DataFrame,
            ):

                if "name" in description.columns:
                    columns = (
                        description["name"]
                        .astype(str)
                        .str.lower()
                        .tolist()
                    )

                elif "column_name" in description.columns:
                    columns = (
                        description["column_name"]
                        .astype(str)
                        .str.lower()
                        .tolist()
                    )

                else:
                    columns = [
                        str(x).lower()
                        for x in description.index
                    ]

            else:
                continue

            score = sum(
                any(
                    term in column
                    for column in columns
                )
                for term in interesting_terms
            )

            if score > 0:
                results.append(
                    {
                        "library": library,
                        "table": table,
                        "score": score,
                        "columns": ", ".join(
                            columns
                        ),
                    }
                )

        except Exception as e:
            results.append(
                {
                    "library": library,
                    "table": table,
                    "score": -1,
                    "columns": (
                        f"ERROR: {e}"
                    ),
                }
            )

    if not results:
        return pd.DataFrame()

    return (
        pd.DataFrame(
            results
        )
        .sort_values(
            [
                "score",
                "library",
                "table",
            ],
            ascending=[
                False,
                True,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# OPTIONMETRICS NDX CHECK
# ============================================================

def inspect_ndx_optionmetrics(
    db,
):
    """
    Verify that NDX exists in OptionMetrics and retrieve
    its SECID.
    """

    print()
    print("=" * 80)
    print("OPTIONMETRICS NDX LOOKUP")
    print("=" * 80)

    try:
        df = db.raw_sql(
            """
            SELECT
                secid,
                cusip,
                ticker,
                index_flag,
                exchange_d,
                class,
                issue_type
            FROM optionm.securd
            WHERE UPPER(ticker) = 'NDX'
              AND index_flag = '1'
            ORDER BY secid
            """
        )

        if df.empty:
            print(
                "No NDX index found in optionm.securd."
            )
        else:
            print(
                df.to_string(
                    index=False
                )
            )

    except Exception as e:
        print(
            f"FAILED: {e}"
        )


# ============================================================
# SAMPLE CANDIDATE TABLES
# ============================================================

def try_candidate_samples(
    db,
    candidates,
    limit=5,
):
    """
    Try small SELECTs against high-scoring tables.

    This determines whether a table is actually queryable
    with the current WRDS permissions.
    """

    if candidates.empty:
        return

    print()
    print("=" * 80)
    print("CANDIDATE TABLE SAMPLES")
    print("=" * 80)

    top = (
        candidates[
            candidates["score"] >= 3
        ]
        .head(30)
    )

    for _, row in top.iterrows():

        library = row["library"]
        table = row["table"]

        print()
        print("-" * 80)
        print(
            f"{library}.{table}"
        )
        print("-" * 80)

        try:
            df = db.raw_sql(
                f"""
                SELECT *
                FROM {library}.{table}
                LIMIT {limit}
                """
            )

            if df.empty:
                print(
                    "No rows."
                )
            else:
                print(
                    df.to_string(
                        index=False
                    )
                )

        except Exception as e:
            print(
                f"FAILED: {e}"
            )


# ============================================================
# MAIN
# ============================================================

def main():
    db = get_wrds_connection()

    try:

        # ----------------------------------------------------
        # 1. Confirm NDX in OptionMetrics
        # ----------------------------------------------------

        inspect_ndx_optionmetrics(
            db
        )

        # ----------------------------------------------------
        # 2. Discover candidate tables
        # ----------------------------------------------------

        print()
        print("=" * 80)
        print("SEARCHING TABLE NAMES")
        print("=" * 80)

        tables = search_table_names(
            db
        )

        if tables.empty:
            print(
                "No candidate table names found."
            )
            return

        print()
        print(
            tables.to_string(
                index=False
            )
        )

        # ----------------------------------------------------
        # 3. Inspect columns
        # ----------------------------------------------------

        print()
        print("=" * 80)
        print("INSPECTING CANDIDATE COLUMNS")
        print("=" * 80)

        candidates = inspect_candidate_columns(
            db=db,
            tables=tables,
        )

        if candidates.empty:
            print(
                "No useful candidates found."
            )
            return

        print(
            candidates.to_string(
                index=False
            )
        )

        # ----------------------------------------------------
        # 4. Test query permissions
        # ----------------------------------------------------

        try_candidate_samples(
            db=db,
            candidates=candidates,
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()