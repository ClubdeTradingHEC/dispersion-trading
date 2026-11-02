
from src.data.wrds_connection import get_wrds_connection


def main():
    db = get_wrds_connection()

    try:
        print("\n=== Checking OptionMetrics access ===")

        df = db.raw_sql("""
            SELECT *
            FROM optionm.opprcd2019
            LIMIT 10
        """)

        print("\nAccess successful.")
        print("\nColumns:")
        print(df.columns.tolist())

        print("\nSample:")
        print(df.to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()
