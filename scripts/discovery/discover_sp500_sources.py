from wrds_connection import get_wrds_connection


TABLES = [
    ("crsp", "dsp500list_v2"),
    ("crsp", "dsp500p"),
    ("crsp", "idx_const_close_v2"),
    ("crsp", "idx_const_close_pf_v2"),
    ("comp", "indexcst_his"),
]


def main():
    db = get_wrds_connection()

    try:
        for library, table in TABLES:
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