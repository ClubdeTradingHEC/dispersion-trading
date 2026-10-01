from ...src.data.wrds_connection import get_wrds_connection


def main():
    db = get_wrds_connection()

    try:
        for table in [
            "fwdprd2024",
            "stdopd2024",
            "zerocd",
            "zero_curve",
        ]:
            print(f"\n=== optionm.{table} ===")

            cols = db.raw_sql(f"""
                SELECT
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE table_schema = 'optionm'
                  AND table_name = '{table}'
                ORDER BY ordinal_position
            """)

            print(cols.to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()