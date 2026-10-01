from wrds_connection import get_wrds_connection


TEST_DATE = "2024-01-03"


def main():
    db = get_wrds_connection()

    try:
        query = f"""
            WITH members AS (
                SELECT permno
                FROM crsp.dsp500list_v2
                WHERE mbrstartdt <= '{TEST_DATE}'
                  AND mbrenddt >= '{TEST_DATE}'
            )

            SELECT
                d.permno,
                d.ticker,
                d.dlycaldt AS date,
                d.dlycap,
                d.dlyret
            FROM crsp.dsf_v2 d
            INNER JOIN members m
                ON d.permno = m.permno
            WHERE d.dlycaldt = '{TEST_DATE}'
              AND d.dlycap IS NOT NULL
            ORDER BY d.dlycap DESC
        """

        df = db.raw_sql(
            query,
            date_cols=["date"],
        )

        print(f"\n=== S&P 500 Data on {TEST_DATE} ===")
        print(df.head(20).to_string(index=False))

        print("\n=== QA ===")
        print(f"Rows: {len(df)}")
        print(f"Unique PERMNOs: {df['permno'].nunique()}")
        print(f"Missing market caps: {df['dlycap'].isna().sum()}")

        # Compute weights
        df["weight"] = df["dlycap"] / df["dlycap"].sum()

        print("\n=== Top 20 Weights ===")
        print(
            df[
                ["ticker", "permno", "dlycap", "weight"]
            ]
            .sort_values("weight", ascending=False)
            .head(20)
            .to_string(index=False)
        )

        print("\n=== Weight QA ===")
        print(f"Sum of weights: {df['weight'].sum():.10f}")
        print(f"Largest weight: {df['weight'].max():.6f}")

    finally:
        db.close()


if __name__ == "__main__":
    main()