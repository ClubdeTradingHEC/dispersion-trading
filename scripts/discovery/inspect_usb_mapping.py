from wrds_connection import get_wrds_connection


SECIDS = [104866, 111306]


def main():
    db = get_wrds_connection()

    try:
        secid_list = ", ".join(str(x) for x in SECIDS)

        print("\n=== securd ===")

        securd = db.raw_sql(f"""
            SELECT
                secid,
                cusip,
                ticker,
                sic,
                index_flag,
                exchange_d,
                class,
                issue_type,
                industry_group
            FROM optionm.securd
            WHERE secid IN ({secid_list})
            ORDER BY secid
        """)

        print(securd.to_string(index=False))

        print("\n=== secnmd history ===")

        secnmd = db.raw_sql(f"""
            SELECT
                secid,
                effect_date,
                cusip,
                ticker,
                class,
                issuer,
                issue
            FROM optionm.secnmd
            WHERE secid IN ({secid_list})
            ORDER BY secid, effect_date
        """, date_cols=["effect_date"])

        print(secnmd.to_string(index=False))

        print("\n=== 2024-01-03 Vol Surface Availability ===")

        surface = db.raw_sql(f"""
            SELECT
                secid,
                COUNT(*) AS n_surface_rows
            FROM optionm.vsurfd2024
            WHERE secid IN ({secid_list})
              AND date = '2024-01-03'
              AND days = 30
              AND (
                    (cp_flag = 'C' AND delta = 50)
                 OR (cp_flag = 'P' AND delta = -50)
              )
            GROUP BY secid
            ORDER BY secid
        """)

        print(surface.to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()