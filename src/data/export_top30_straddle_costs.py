
import argparse
from pathlib import Path

import pandas as pd

from .wrds_connection import get_wrds_connection
from .option_quotes import (
    build_straddle_pairs,
    select_straddle_pair,
    calculate_straddle_cost,
)


SPX_SECID = 108105
METHODS = ("closest_30d", "liquidity_aware")


def get_args():
    parser = argparse.ArgumentParser(
        description="Export historical SPX and top-N constituent straddle costs"
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--output", default="data/transaction_costs/top30")
    parser.add_argument("--min-open-interest", type=int, default=100)
    parser.add_argument("--max-maturity-distance", type=int, default=10)
    parser.add_argument("--commission", type=float, default=0.65)
    return parser.parse_args()


# ============================================================
# 1. HISTORICAL S&P 500 CONSTITUENTS AND MARKET CAPS
# ============================================================

def get_historical_top_constituents(db, start, end, top_n):
    """
    Point-in-time SPX membership from CRSP.

    Rank active constituents by observed daily market cap.
    No current-constituent list is used.
    """

    sql = f"""
        WITH eligible AS (
            SELECT
                d.dlycaldt AS date,
                d.permno,
                d.ticker,
                d.dlycap AS market_cap,
                ROW_NUMBER() OVER (
                    PARTITION BY d.dlycaldt
                    ORDER BY d.dlycap DESC, d.permno
                ) AS cap_rank
            FROM crsp.dsf_v2 d
            WHERE d.dlycaldt >= '{start}'
              AND d.dlycaldt <= '{end}'
              AND d.dlycap > 0
              AND EXISTS (
                  SELECT 1
                  FROM crsp.dsp500list_v2 m
                  WHERE m.permno = d.permno
                    AND d.dlycaldt >= m.mbrstartdt
                    AND d.dlycaldt <= m.mbrenddt
              )
        )
        SELECT
            date, permno, ticker, market_cap, cap_rank
        FROM eligible
        WHERE cap_rank <= {int(top_n)}
        ORDER BY date, cap_rank
    """

    df = db.raw_sql(sql, date_cols=["date"])

    if df.empty:
        raise ValueError("No historical SPX constituents found.")

    df["permno"] = df["permno"].astype(int)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    return df


# ============================================================
# 2. HISTORICAL CRSP -> OPTIONMETRICS MAPPING
# ============================================================

def get_historical_links(db, permnos):
    """
    Retrieve historical OptionMetrics / CRSP links.

    Mapping is subsequently filtered by each observation date.
    Lower WRDS linkage scores are preferred.
    """

    ids = sorted(set(int(p) for p in permnos))

    if not ids:
        return pd.DataFrame()

    sql_ids = ",".join(map(str, ids))

    df = db.raw_sql(
        f"""
        SELECT
            permno,
            secid,
            sdate,
            edate,
            score
        FROM wrdsapps_link_crsp_optionm.opcrsphist
        WHERE permno IN ({sql_ids})
        """,
        date_cols=["sdate", "edate"],
    )

    if df.empty:
        raise ValueError("No CRSP-OptionMetrics links found.")

    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    df["secid"] = pd.to_numeric(df["secid"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")

    return df.dropna(subset=["permno", "secid"]).copy()


def attach_historical_secids(members, links):
    """
    Match PERMNO to SECID only when the historical link
    is valid on the observation date.
    """

    merged = members.merge(
        links,
        on="permno",
        how="left",
    )

    valid = (
        merged["secid"].notna()
        & (
            merged["sdate"].isna()
            | (merged["date"] >= merged["sdate"])
        )
        & (
            merged["edate"].isna()
            | (merged["date"] <= merged["edate"])
        )
    )

    matched = merged.loc[valid].copy()

    matched["score"] = matched["score"].fillna(float("inf"))

    matched = (
        matched.sort_values(
            ["date", "permno", "score", "secid"]
        )
        .drop_duplicates(["date", "permno"])
    )

    matched["secid"] = matched["secid"].astype(int)

    # Keep a record of mapping coverage.
    coverage = (
        members[["date", "permno"]]
        .merge(
            matched[["date", "permno"]],
            on=["date", "permno"],
            how="left",
            indicator=True,
        )
    )

    print(
        "Historical SECID mapping coverage: "
        f"{(coverage['_merge'] == 'both').mean():.2%}"
    )

    return matched


# ============================================================
# 3. BATCH OPTION QUOTES FOR ALL SECIDS ON ONE DATE
# ============================================================

def get_daily_option_quotes(db, secids, date):
    """
    One OptionMetrics query per trading date, rather than
    one query for every security and selection method.
    """

    ids = sorted(set(int(s) for s in secids))

    if not ids:
        return pd.DataFrame()

    date = pd.Timestamp(date).date()
    year = date.year
    sql_ids = ",".join(map(str, ids))

    sql = f"""
        SELECT
            secid,
            date,
            optionid,
            exdate,
            cp_flag,
            strike_price,
            best_bid,
            best_offer,
            delta,
            vega,
            volume,
            open_interest,
            contract_size,
            ss_flag,
            am_settlement,
            expiry_indicator
        FROM optionm.opprcd{year}
        WHERE date = '{date}'
          AND secid IN ({sql_ids})
          AND exdate BETWEEN
              DATE '{date}' + 20
              AND DATE '{date}' + 45
          AND (
                 (cp_flag = 'C' AND delta BETWEEN 0.40 AND 0.60)
              OR (cp_flag = 'P' AND delta BETWEEN -0.60 AND -0.40)
          )
          AND best_bid > 0
          AND best_offer > best_bid
          AND vega > 0
          AND ss_flag = '0'
    """

    df = db.raw_sql(
        sql,
        date_cols=["date", "exdate"],
    )

    if not df.empty:
        df["secid"] = df["secid"].astype(int)

    return df


# ============================================================
# 4. STRADDLE SELECTION AND TRANSACTION COSTS
# ============================================================

def calculate_methods(
    quotes,
    date,
    secid,
    ticker,
    permno,
    market_cap,
    cap_rank,
    min_open_interest,
    max_maturity_distance,
):
    """
    Build call/put pairs once and evaluate both strategies.
    """

    results = []
    errors = []

    if quotes.empty:
        for method in METHODS:
            errors.append({
                "date": str(pd.Timestamp(date).date()),
                "ticker": ticker,
                "secid": secid,
                "selection_method": method,
                "reason": "No eligible quotes",
            })
        return results, errors

    try:
        pairs = build_straddle_pairs(
            quotes=quotes,
            date=date,
            target_days=30,
        )
    except ValueError as exc:
        for method in METHODS:
            errors.append({
                "date": str(pd.Timestamp(date).date()),
                "ticker": ticker,
                "secid": secid,
                "selection_method": method,
                "reason": str(exc),
            })
        return results, errors

    for method in METHODS:
        try:
            pair = select_straddle_pair(
                pairs=pairs,
                selection_method=method,
                min_open_interest=min_open_interest,
                max_maturity_distance=max_maturity_distance,
            )

            result = calculate_straddle_cost(
                pair=pair,
                date=date,
                secid=secid,
                selection_method=method,
            )

            result.update({
                "ticker": ticker,
                "permno": permno,
                "market_cap": market_cap,
                "cap_rank": cap_rank,
                "is_index": ticker == "SPX",
            })

            results.append(result)

        except ValueError as exc:
            errors.append({
                "date": str(pd.Timestamp(date).date()),
                "ticker": ticker,
                "secid": secid,
                "selection_method": method,
                "reason": str(exc),
            })

    return results, errors


# ============================================================
# 5. SUMMARY AND SIMULATOR OUTPUT
# ============================================================

def build_annual_summary(daily):
    df = daily.copy()
    df["year"] = pd.to_datetime(df["date"]).dt.year
    df["security_type"] = df["is_index"].map({
        True: "SPX",
        False: "Constituent",
    })

    return (
        df.groupby(
            ["year", "security_type", "ticker", "secid",
             "selection_method"],
            as_index=False,
        )
        .agg(
            observations=("cost_vol_points", "size"),
            median_cost_vol_pts=("cost_vol_points", "median"),
            mean_cost_vol_pts=("cost_vol_points", "mean"),
            p95_cost_vol_pts=(
                "cost_vol_points",
                lambda x: x.quantile(0.95),
            ),
            median_half_spread_pct=(
                "half_spread_pct", "median"
            ),
            median_dte=("dte", "median"),
            wide_spread_count=("wide_spread_flag", "sum"),
        )
    )


def build_simulator_costs(daily, commission):
    """
    Base: half the full bid-ask spread per execution.
    Stress: the full bid-ask spread per execution.

    Commission: charged for both option legs.
    """
    df = daily.loc[
        daily["selection_method"] == "closest_30d"
    ].copy()

    df["base_cost_vol_points"] = df["cost_vol_points"]
    df["stress_cost_vol_points"] = df["full_spread_vol_points"]

    df["base_cost_usd"] = df[
        "one_way_cost_per_straddle_usd"
    ]

    df["stress_cost_usd"] = (
        df["round_trip_cost_per_straddle_usd"]
    )

    # One straddle contains two option contracts.
    df["commission_usd"] = 2 * commission

    df["base_cost_with_commission_usd"] = (
        df["base_cost_usd"] + df["commission_usd"]
    )

    df["stress_cost_with_commission_usd"] = (
        df["stress_cost_usd"] + df["commission_usd"]
    )

    cols = [
        "date", "ticker", "secid", "permno",
        "call_optionid", "put_optionid",
        "expiration", "strike", "dte",
        "contract_size",
        "vega_usd_per_vol_point",
        "call_bid", "call_ask", "put_bid", "put_ask",
        "base_cost_vol_points",
        "stress_cost_vol_points",
        "base_cost_usd",
        "stress_cost_usd",
        "commission_usd",
        "base_cost_with_commission_usd",
        "stress_cost_with_commission_usd",
        "wide_spread_flag",
    ]

    return df[cols].copy()


# ============================================================
# 6. EXPORT PIPELINE
# ============================================================

def export_costs(
    start,
    end,
    top_n=30,
    output="data/transaction_costs/top30",
    min_open_interest=100,
    max_maturity_distance=10,
    commission=0.65,
):
    start = pd.Timestamp(start).date()
    end = pd.Timestamp(end).date()

    if end < start:
        raise ValueError("End date precedes start date.")

    if start.year != end.year:
        raise ValueError("Run one calendar year at a time.")

    if top_n < 1:
        raise ValueError("--top must be positive.")

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    db = get_wrds_connection()
    rows = []
    errors = []
    mapping_gaps = []

    try:
        print("\nFetching historical SPX membership and market caps...")

        members = get_historical_top_constituents(
            db, start, end, top_n
        )

        links = get_historical_links(
            db, members["permno"].unique()
        )

        members = attach_historical_secids(members, links)

        dates = sorted(members["date"].unique())

        print(f"Trading dates: {len(dates)}")
        print(f"Top constituents per day: {top_n}")
        print("Option selection methods:", METHODS)

        for i, date in enumerate(dates, start=1):
            date = pd.Timestamp(date)
            daily_members = members[
                members["date"] == date
            ].copy()

            secids = (
                daily_members["secid"].astype(int).tolist()
                + [SPX_SECID]
            )

            quotes = get_daily_option_quotes(
                db=db,
                secids=secids,
                date=date,
            )

            print(
                f"[{i}/{len(dates)}] {date.date()} | "
                f"{len(daily_members)} constituents | "
                f"{len(quotes)} option quotes"
            )

            # Always include SPX itself.
            securities = [{
                "ticker": "SPX",
                "permno": None,
                "secid": SPX_SECID,
                "market_cap": None,
                "cap_rank": 0,
            }]

            for member in daily_members.itertuples():
                securities.append({
                    "ticker": member.ticker,
                    "permno": int(member.permno),
                    "secid": int(member.secid),
                    "market_cap": float(member.market_cap),
                    "cap_rank": int(member.cap_rank),
                })

            for security in securities:
                secid = security["secid"]

                security_quotes = (
                    quotes[quotes["secid"] == secid]
                    if not quotes.empty
                    else pd.DataFrame()
                )

                results, failures = calculate_methods(
                    quotes=security_quotes,
                    date=date,
                    secid=secid,
                    ticker=security["ticker"],
                    permno=security["permno"],
                    market_cap=security["market_cap"],
                    cap_rank=security["cap_rank"],
                    min_open_interest=min_open_interest,
                    max_maturity_distance=max_maturity_distance,
                )

                rows.extend(results)
                errors.extend(failures)

    finally:
        db.close()

    if not rows:
        raise ValueError("No valid straddle costs calculated.")

    daily = pd.DataFrame(rows)
    daily = daily.sort_values(
        ["date", "ticker", "selection_method"]
    ).reset_index(drop=True)

    annual = build_annual_summary(daily)
    simulator = build_simulator_costs(daily, commission)

    quality = daily[[
        "date", "ticker", "secid", "selection_method",
        "dte", "min_open_interest", "total_volume",
        "half_spread_pct", "wide_spread_flag",
        "zero_volume_flag", "zero_oi_flag",
    ]].copy()

    skipped = pd.DataFrame(
        errors,
        columns=[
            "date", "ticker", "secid",
            "selection_method", "reason",
        ],
    )

    files = {
        "straddle_costs_daily.csv": daily,
        "straddle_costs_annual.csv": annual,
        "straddle_costs_quality.csv": quality,
        "simulator_costs.csv": simulator,
        "straddle_costs_skipped.csv": skipped,
    }

    for filename, frame in files.items():
        path = output_dir / filename
        frame.to_csv(path, index=False)
        print(f"Saved: {path} ({len(frame):,} rows)")

    print("\n=== Annual Summary ===")
    print(
        annual[
            annual["selection_method"] == "closest_30d"
        ][[
            "ticker",
            "observations",
            "median_cost_vol_pts",
            "median_half_spread_pct",
        ]]
        .sort_values("median_cost_vol_pts")
        .to_string(index=False)
    )

    print("\nTotal successful rows:", len(daily))
    print("Total skipped combinations:", len(skipped))

    return daily, annual, simulator


def main():
    args = get_args()

    export_costs(
        start=args.start,
        end=args.end,
        top_n=args.top,
        output=args.output,
        min_open_interest=args.min_open_interest,
        max_maturity_distance=args.max_maturity_distance,
        commission=args.commission,
    )


if __name__ == "__main__":
    main()
