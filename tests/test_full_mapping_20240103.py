from wrds_connection import get_wrds_connection


TEST_DATE = "2024-01-03"


def main():
    db = get_wrds_connection()

    try:
        # -----------------------------------
        # 1. Get active S&P 500 members + market caps
        # -----------------------------------
        weights = db.raw_sql(f"""
            WITH members AS (
                SELECT permno
                FROM crsp.dsp500list_v2
                WHERE mbrstartdt <= '{TEST_DATE}'
                  AND mbrenddt >= '{TEST_DATE}'
            )

            SELECT
                d.permno,
                d.ticker,
                d.dlycap
            FROM crsp.dsf_v2 d
            INNER JOIN members m
                ON d.permno = m.permno
            WHERE d.dlycaldt = '{TEST_DATE}'
              AND d.dlycap IS NOT NULL
            ORDER BY d.dlycap DESC
        """)

        # Compute weights BEFORE link-table merge
        weights["weight"] = (
            weights["dlycap"]
            / weights["dlycap"].sum()
        )

        # -----------------------------------
        # 2. Get all valid OptionMetrics links
        # -----------------------------------
        links = db.raw_sql(f"""
            SELECT
                permno,
                secid,
                score,
                sdate,
                edate
            FROM wrdsapps_link_crsp_optionm.opcrsphist
            WHERE sdate <= '{TEST_DATE}'
              AND edate >= '{TEST_DATE}'
        """, date_cols=["sdate", "edate"])

        # -----------------------------------
        # 3. Keep only minimum-score links
        # -----------------------------------
        min_score = (
            links.groupby("permno")["score"]
            .transform("min")
        )

        best_links = links[
            links["score"] == min_score
        ].copy()

        # -----------------------------------
        # 4. Detect ties at the best score
        # -----------------------------------
        tie_counts = (
            best_links.groupby("permno")["secid"]
            .nunique()
        )

        ties = tie_counts[tie_counts > 1]

        print("\n=== Ties at Best Score ===")

        tied_rows = best_links[
            best_links["permno"].isin(ties.index)
        ].sort_values(["permno", "secid"])

        print(tied_rows.to_string(index=False))

        # -----------------------------------
        # 5. Keep only unambiguous best links for now
        # -----------------------------------
        clean_links = best_links[
            ~best_links["permno"].isin(ties.index)
        ].copy()

        # -----------------------------------
        # 6. Merge weights with cleaned links
        # -----------------------------------
        df = weights.merge(
            clean_links[
                ["permno", "secid", "score", "sdate", "edate"]
            ],
            on="permno",
            how="left",
        )

        print("\n=== Clean Mapping Sample ===")
        print(df.head(20).to_string(index=False))

        print("\n=== QA ===")
        print(f"Unique S&P 500 PERMNOs: {weights['permno'].nunique()}")
        print(f"Ties at best score: {len(ties)}")
        print(
            f"Mapped without ambiguity: "
            f"{df['secid'].notna().sum()}"
        )

        print(
            f"Weight sum before mapping: "
            f"{weights['weight'].sum():.10f}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()