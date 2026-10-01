import argparse

from wrds_connection import get_wrds_connection


def get_args():
    parser = argparse.ArgumentParser(
        description="Find OptionMetrics tables containing underlying prices."
    )

    parser.add_argument(
        "--ticker",
        required=True,
        type=str,
        help="Ticker to investigate, e.g. DJX, SPX, AAPL",
    )

    return parser.parse_args()


def main():
    args = get_args()
    ticker = args.ticker.upper()

    db = get_wrds_connection()

    try:
        print(f"\n=== Searching OptionMetrics tables for {ticker} ===")

        tables = db.list_tables(library="optionm")

        keywords = [
            "secpr",
            "price",
            "secur",
            "under",
        ]

        matches = [
            table
            for table in tables
            if any(
                keyword in table.lower()
                for keyword in keywords
            )
        ]

        print("\n=== Candidate Tables ===")

        for table in matches:
            print(f"\n--- optionm.{table} ---")

            try:
                schema = db.describe_table(
                    library="optionm",
                    table=table,
                )

                print(schema.to_string(index=False))

            except Exception as e:
                print(f"Could not inspect: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()