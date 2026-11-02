
from .wrds_connection import get_wrds_connection

SECIDS = {
    "SPX": 108105,
    "AAPL": 101594,
}

def main():
    db = get_wrds_connection()

    try:
        for ticker, secid in SECIDS.items():
            print(f"\n=== {ticker}: 2019-06-28 ===")

            df = db.raw_sql(f"""
                SELECT
                    optionid,
                    exdate,
                    cp_flag,
                    strike_price / 1000.0 AS strike,
                    best_bid,
                    best_offer,
                    delta,
                    vega,
                    volume,
                    open_interest,
                    contract_size,
                    root,
                    expiry_indicator,
                    am_settlement,
                    ss_flag
                FROM optionm.opprcd2019
                WHERE secid = {secid}
                  AND date = '2019-06-28'
                  AND exdate BETWEEN
                      DATE '2019-06-28' + 20
                      AND DATE '2019-06-28' + 45
                  AND delta BETWEEN -0.60 AND 0.60
                  AND best_bid > 0
                  AND best_offer > best_bid
                ORDER BY
                    exdate,
                    strike_price,
                    cp_flag
            """)

            print(df.to_string(index=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()
