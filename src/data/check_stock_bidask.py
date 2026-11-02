
from .wrds_connection import get_wrds_connection


def main():
    db = get_wrds_connection()

    try:
        columns = db.describe_table(
            library="crsp",
            table="dsf_v2",
        )

        print("\n=== CRSP BID/ASK COLUMNS ===")

        matches = columns[
            columns["name"].str.contains(
                "bid|ask|prc|cap|permno|caldt",
                case=False,
                na=False,
            )
        ]

        print(matches[["name", "type"]].to_string(index=False))

        names = set(columns["name"].str.lower())

        if {"dlybid", "dlyask"}.issubset(names):
            print("\nDaily bid/ask columns are available.")

            sample = db.raw_sql("""
                SELECT
                    permno,
                    dlycaldt,
                    dlyprc,
                    dlybid,
                    dlyask
                FROM crsp.dsf_v2
                WHERE dlycaldt BETWEEN
                    '2019-06-03' AND '2019-06-07'
                  AND dlybid > 0
                  AND dlyask > dlybid
                LIMIT 10
            """)

            print("\n=== SAMPLE STOCK BID/ASK ===")
            print(sample.to_string(index=False))

        else:
            print("\nDaily bid/ask columns not found.")
            print("We need to investigate an alternative source.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
