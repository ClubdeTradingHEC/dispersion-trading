from wrds_connection import get_wrds_connection


KEYWORDS = [
    "dow",
    "djia",
    "industrial",
    "30",
]


def main():
    db = get_wrds_connection()

    try:
        libraries = [
            "crsp",
            "crsp_a_indexes",
            "comp",
        ]

        for library in libraries:
            print(f"\n=== {library} ===")

            try:
                tables = db.list_tables(library=library)

                matches = [
                    table
                    for table in tables
                    if any(
                        keyword in table.lower()
                        for keyword in KEYWORDS
                    )
                ]

                for table in matches:
                    print(table)

            except Exception as e:
                print(f"Could not inspect {library}: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()