from wrds_connection import get_wrds_connection


TEST_DATE = "2024-01-03"

TEST_PERMNOS = {
    14593: "AAPL",
    10107: "MSFT",
    84788: "AMZN",
}


def main():
    db = get_wrds_connection()

    try:
        permno_list = ", ".join(
            str(p) for p in TEST_PERMNOS.keys()
        )

        links = db.raw_sql(f"""
            SELECT
                permno,
                secid,
                sdate,
                edate,
                score
            FROM wrdsapps_link_crsp_optionm.opcrsphist
            WHERE permno IN ({permno_list})
              AND sdate <= '{TEST_DATE}'
              AND edate >= '{TEST_DATE}'
            ORDER BY permno, score
        """, date_cols=["sdate", "edate"])

        print("\n=== CRSP ↔ OptionMetrics Mapping ===")
        print(links.to_string(index=False))

        expected = {
            14593: 101594,
            10107: 107525,
            84788: 101310,
        }

        print("\n=== Validation ===")

        for permno, expected_secid in expected.items():
            rows = links[links["permno"] == permno]

            if rows.empty:
                print(
                    f"{TEST_PERMNOS[permno]}: "
                    f"NO MAPPING FOUND"
                )
                continue

            found_secids = (
                rows["secid"]
                .astype(int)
                .tolist()
            )

            result = (
                expected_secid in found_secids
            )

            print(
                f"{TEST_PERMNOS[permno]} | "
                f"PERMNO {permno} | "
                f"expected SECID {expected_secid} | "
                f"found {found_secids} | "
                f"{'OK' if result else 'MISMATCH'}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()