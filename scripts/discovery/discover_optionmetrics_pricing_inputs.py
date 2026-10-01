from ...src.data.wrds_connection import get_wrds_connection


TABLE_KEYWORDS = [
    "rate",
    "zero",
    "curve",
    "yield",
    "div",
    "dist",
    "price",
    "secpr",
]

COLUMN_KEYWORDS = [
    "rate",
    "zero",
    "yield",
    "div",
    "dist",
    "amount",
    "price",
    "close",
    "forward",
]


def contains_keyword(value, keywords):
    value = str(value).lower()
    return any(keyword in value for keyword in keywords)


def main():
    db = get_wrds_connection()

    try:
        # --------------------------------------------------
        # 1. All OptionMetrics tables
        # --------------------------------------------------
        tables = db.raw_sql(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'optionm'
            ORDER BY table_name
            """
        )

        table_names = tables["table_name"].astype(str).tolist()

        print("\n=== Candidate OptionMetrics tables ===")

        candidate_tables = [
            table
            for table in table_names
            if contains_keyword(table, TABLE_KEYWORDS)
        ]

        for table in candidate_tables:
            print(table)

        # --------------------------------------------------
        # 2. Search OptionMetrics columns
        # --------------------------------------------------
        columns = db.raw_sql(
            """
            SELECT
                table_name,
                column_name,
                data_type
            FROM information_schema.columns
            WHERE table_schema = 'optionm'
            ORDER BY table_name, ordinal_position
            """
        )

        matches = columns[
            columns["column_name"].apply(
                lambda x: contains_keyword(
                    x,
                    COLUMN_KEYWORDS,
                )
            )
        ].copy()

        print("\n=== Candidate pricing-input columns ===")
        print(
            matches.to_string(
                index=False
            )
        )

        # --------------------------------------------------
        # 3. Inspect particularly interesting tables
        # --------------------------------------------------
        interesting = set(candidate_tables)

        # Known useful table already used by the project
        if "secprd" in table_names:
            interesting.add("secprd")

        print("\n=== Schemas of candidate tables ===")

        for table in sorted(interesting):
            table_cols = columns[
                columns["table_name"] == table
            ]

            print(f"\n--- optionm.{table} ---")
            print(
                table_cols.to_string(
                    index=False
                )
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()