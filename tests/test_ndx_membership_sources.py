from .wrds_connection import get_wrds_connection


NDX_GVKEYX = "000208"
TEST_DATE = "2024-01-03"


def print_df(df):
    if df is None or df.empty:
        print("No rows.")
    else:
        print(df.to_string(index=False))


def describe(db, table):
    print()
    print("=" * 80)
    print(f"DESCRIBE comp.{table}")
    print("=" * 80)

    try:
        df = db.describe_table(
            library="comp",
            table=table,
        )

        print_df(df)

    except Exception as e:
        print(f"FAILED: {e}")


def sample(db, table):
    print()
    print("=" * 80)
    print(f"SAMPLE comp.{table}")
    print("=" * 80)

    try:
        df = db.raw_sql(
            f"""
            SELECT *
            FROM comp.{table}
            LIMIT 10
            """
        )

        print_df(df)

    except Exception as e:
        print(f"FAILED: {e}")


def main():
    db = get_wrds_connection()

    try:

        candidate_tables = [
            "idxcst_his",
            "names_ix_cst",
            "spidx_cst",
            "wrds_idx_cst_current",
        ]

        # ====================================================
        # 1. Inspect structures
        # ====================================================

        for table in candidate_tables:
            describe(
                db=db,
                table=table,
            )

            sample(
                db=db,
                table=table,
            )

        # ====================================================
        # 2. Check NDX in idxcst_his
        # ====================================================

        print()
        print("=" * 80)
        print("NDX SEARCH: comp.idxcst_his")
        print("=" * 80)

        try:
            df = db.raw_sql(
                f"""
                SELECT *
                FROM comp.idxcst_his
                WHERE gvkeyx = '{NDX_GVKEYX}'
                LIMIT 200
                """
            )

            print_df(df)

        except Exception as e:
            print(f"FAILED: {e}")

        # ====================================================
        # 3. Check active NDX membership
        #    assuming same date field names as indexcst_his
        # ====================================================

        print()
        print("=" * 80)
        print(
            f"ACTIVE NDX MEMBERSHIP ON {TEST_DATE}: "
            f"comp.idxcst_his"
        )
        print("=" * 80)

        try:
            df = db.raw_sql(
                f"""
                SELECT *
                FROM comp.idxcst_his
                WHERE gvkeyx = '{NDX_GVKEYX}'
                  AND fromdate <= '{TEST_DATE}'
                  AND (
                        thrudate IS NULL
                        OR thrudate >= '{TEST_DATE}'
                      )
                ORDER BY gvkey
                """
            )

            print_df(df)

            print()
            print(
                f"Rows returned: {len(df)}"
            )

        except Exception as e:
            print(f"FAILED: {e}")

        # ====================================================
        # 4. Search current WRDS constituent table
        # ====================================================

        print()
        print("=" * 80)
        print("NDX SEARCH: comp.wrds_idx_cst_current")
        print("=" * 80)

        try:
            df = db.raw_sql(
                f"""
                SELECT *
                FROM comp.wrds_idx_cst_current
                WHERE gvkeyx = '{NDX_GVKEYX}'
                LIMIT 200
                """
            )

            print_df(df)

        except Exception as e:
            print(f"FAILED: {e}")

        # ====================================================
        # 5. Search names_ix_cst
        # ====================================================

        print()
        print("=" * 80)
        print("NDX SEARCH: comp.names_ix_cst")
        print("=" * 80)

        try:
            df = db.raw_sql(
                f"""
                SELECT *
                FROM comp.names_ix_cst
                WHERE gvkeyx = '{NDX_GVKEYX}'
                LIMIT 200
                """
            )

            print_df(df)

        except Exception as e:
            print(f"FAILED: {e}")

        # ====================================================
        # 6. Search spidx_cst
        # ====================================================

        print()
        print("=" * 80)
        print("NDX SEARCH: comp.spidx_cst")
        print("=" * 80)

        try:
            df = db.raw_sql(
                f"""
                SELECT *
                FROM comp.spidx_cst
                WHERE gvkeyx = '{NDX_GVKEYX}'
                LIMIT 200
                """
            )

            print_df(df)

        except Exception as e:
            print(f"FAILED: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()