from wrds_connection import get_wrds_connection


TEST_DATE = "2024-01-03"


def main():
    db = get_wrds_connection()

    try:
        members = db.raw_sql(f"""
            SELECT
                permno,
                indno,
                mbrstartdt,
                mbrenddt,
                mbrflg,
                indfam
            FROM crsp.dsp500list_v2
            WHERE mbrstartdt <= '{TEST_DATE}'
              AND mbrenddt >= '{TEST_DATE}'
            ORDER BY permno
        """, date_cols=["mbrstartdt", "mbrenddt"])

        print(f"\n=== Active S&P 500 Members on {TEST_DATE} ===")
        print(members.head(20).to_string(index=False))

        print("\n=== QA ===")
        print(f"Rows: {len(members)}")
        print(f"Unique PERMNOs: {members['permno'].nunique()}")

        print("\nMembership flags:")
        print(members["mbrflg"].value_counts(dropna=False))

        print("\nIndex numbers:")
        print(members["indno"].value_counts(dropna=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()