from wrds_connection import get_wrds_connection


CANDIDATES = [
    ("crsp", "dsf"),
    ("crsp", "dsf_v2"),
    ("crsp_a_stock", "dsf"),
    ("crsp_a_stock", "dsf_v2"),
]


def main():
    db = get_wrds_connection()

    try:
        for library, table in CANDIDATES:
            print(f"\n=== {library}.{table} ===")

            try:
                schema = db.describe_table(
                    library=library,
                    table=table,
                )

                print(schema)

            except Exception as e:
                print(f"Could not inspect {library}.{table}: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()