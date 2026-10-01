from wrds_connection import get_wrds_connection


LIBRARY = "wrdsapps_link_crsp_optionm"


def main():
    db = get_wrds_connection()

    try:
        tables = db.list_tables(library=LIBRARY)

        print(f"\n=== Tables in {LIBRARY} ===")
        for table in tables:
            print(table)

        print("\n=== Candidate linking tables ===")

        for table in tables:
            try:
                schema = db.describe_table(
                    library=LIBRARY,
                    table=table,
                )

                cols = set(schema["name"].str.lower())

                has_permno = "permno" in cols
                has_secid = "secid" in cols

                if has_permno or has_secid:
                    print(f"\n--- {LIBRARY}.{table} ---")
                    print(schema.to_string(index=False))

            except Exception as e:
                print(f"Could not inspect {table}: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()