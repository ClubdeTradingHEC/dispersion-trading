from wrds_connection import get_wrds_connection


SECID = 102456
TEST_DATE = "2024-01-03"


def main():
    db = get_wrds_connection()

    try:
        df = db.raw_sql(f"""
            SELECT
                secid,
                date,
                days,
                delta,
                cp_flag,
                impl_volatility,
                impl_strike,
                dispersion
            FROM optionm.vsurfd2024
            WHERE secid = {SECID}
              AND date = '{TEST_DATE}'
              AND days = 30
              AND (
                    (cp_flag = 'C' AND delta = 50)
                 OR (cp_flag = 'P' AND delta = -50)
              )
            ORDER BY cp_flag
        """)

        print("\n=== DJX 30D +/-50 Delta Surface ===")
        print(df.to_string(index=False))

        if len(df) == 2:
            atm_iv = df["impl_volatility"].mean()

            print(f"\nDJX 30D ATM IV: {atm_iv:.6f}")
            print(f"DJX 30D ATM IV (%): {atm_iv * 100:.4f}%")

    finally:
        db.close()


if __name__ == "__main__":
    main()