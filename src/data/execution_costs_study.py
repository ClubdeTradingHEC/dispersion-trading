"""WRDS execution costs for SPX, its daily top 30 securities, DJX and DIA."""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd


INDEX_SECIDS = {"SPX": 108105, "DJX": 102456}
PAIR_COLUMNS = ["exdate", "contract_size", "am_settlement", "expiry_indicator"]
COST_COLUMNS = [
    "date", "group", "ticker", "permno", "secid", "strategy", "expiration", "dte",
    "call_optionid", "put_optionid", "call_strike", "put_strike", "call_delta",
    "put_delta", "call_bid", "call_ask", "put_bid", "put_ask", "call_vega",
    "put_vega", "call_volume", "put_volume", "call_open_interest", "put_open_interest",
    "contract_size", "am_settlement", "expiry_indicator", "straddle_or_strangle_mid",
    "half_spread_usd", "half_spread_pct", "vega_usd_per_vol_point",
    "cost_vol_points", "one_way_cost_per_pair_usd", "full_spread_cost_per_pair_usd",
]
FAIL_COLUMNS = ["date", "group", "ticker", "permno", "secid", "strategy", "reason"]


def write_csv(frame, path):
    temp = path.with_suffix(".tmp")
    frame.to_csv(temp, index=False)
    temp.replace(path)


def get_calendar(db, start, end):
    rows = db.raw_sql(f"""
        SELECT DISTINCT date FROM optionm.secprd
        WHERE secid = {INDEX_SECIDS["SPX"]}
          AND date BETWEEN '{start}' AND '{end}' AND close > 0
        ORDER BY date
    """, date_cols=["date"])
    return pd.to_datetime(rows["date"]).dt.date


def get_dia_secid(db, override):
    if override is not None:
        return override
    rows = db.raw_sql("""
        SELECT DISTINCT secid FROM optionm.securd
        WHERE UPPER(TRIM(ticker)) = 'DIA'
    """)
    secids = rows["secid"].dropna().astype(int).unique()
    if len(secids) != 1:
        raise ValueError(f"DIA SECIDs: {secids.tolist()}. Verify and pass --dia-secid.")
    return int(secids[0])


def get_top30(db, start, end):
    """Rank same-day historical members by CRSP daily security capitalization."""
    rows = db.raw_sql(f"""
        WITH ranked AS (
            SELECT d.dlycaldt AS date, d.permno, d.ticker, d.dlycap,
                   ROW_NUMBER() OVER (
                       PARTITION BY d.dlycaldt ORDER BY d.dlycap DESC, d.permno
                   ) AS rank
            FROM crsp.dsf_v2 d
            WHERE d.dlycaldt BETWEEN '{start}' AND '{end}'
              AND d.dlycap > 0
              AND EXISTS (
                  SELECT 1 FROM crsp.dsp500list_v2 m
                  WHERE m.permno = d.permno AND m.mbrstartdt <= d.dlycaldt
                    AND (m.mbrenddt >= d.dlycaldt OR m.mbrenddt IS NULL)
              )
        ), best_links AS (
            SELECT r.date, r.permno, r.ticker, l.secid,
                   DENSE_RANK() OVER (
                       PARTITION BY r.date, r.permno ORDER BY l.score NULLS LAST
                   ) AS link_rank
            FROM ranked r
            LEFT JOIN wrdsapps_link_crsp_optionm.opcrsphist l
              ON l.permno = r.permno AND l.secid IS NOT NULL
             AND (l.sdate IS NULL OR l.sdate <= r.date)
             AND (l.edate IS NULL OR l.edate >= r.date)
            WHERE r.rank <= 30
        )
        SELECT date, permno, ticker, COUNT(DISTINCT secid) AS link_count,
               CASE WHEN COUNT(DISTINCT secid) = 1 THEN MIN(secid) END AS secid
        FROM best_links
        WHERE link_rank = 1
        GROUP BY date, permno, ticker
        ORDER BY date, permno
    """, date_cols=["date"])
    rows["date"] = pd.to_datetime(rows["date"]).dt.date
    rows["group"] = "SPX_constituents"
    return rows


def get_quotes(db, start, end, secids):
    ids = ",".join(str(int(secid)) for secid in sorted(secids))
    rows = db.raw_sql(f"""
        SELECT secid, date, optionid, exdate, cp_flag, strike_price,
               best_bid, best_offer, delta, vega, volume, open_interest,
               contract_size, ss_flag, am_settlement, expiry_indicator
        FROM optionm.opprcd{start.year}
        WHERE secid IN ({ids}) AND date BETWEEN '{start}' AND '{end}'
          AND exdate BETWEEN date + 20 AND date + 45
          AND (
                (cp_flag = 'C' AND (delta BETWEEN .40 AND .60 OR delta BETWEEN .15 AND .35))
             OR (cp_flag = 'P' AND (delta BETWEEN -.60 AND -.40 OR delta BETWEEN -.35 AND -.15))
          )
          AND best_bid > 0 AND best_offer > best_bid AND vega > 0
          AND ss_flag = '0' AND contract_size > 0 AND strike_price > 0
    """, date_cols=["date", "exdate"])
    rows["date"] = pd.to_datetime(rows["date"]).dt.date
    rows["exdate"] = pd.to_datetime(rows["exdate"])
    return rows


def select_pair(quotes, day, wing, expiration=None):
    low, high = (.15, .35) if wing else (.40, .60)
    target = .25 if wing else .50
    eligible = quotes.loc[quotes["delta"].abs().between(low, high)]
    if expiration is not None:
        eligible = eligible.loc[eligible["exdate"].eq(expiration)]
    keys = PAIR_COLUMNS if wing else [*PAIR_COLUMNS, "strike_price"]
    # Retain the closest distinct OTM strikes within each compatible series.
    if wing:
        calls = eligible.loc[eligible.cp_flag.eq("C")].copy()
        puts = eligible.loc[eligible.cp_flag.eq("P")].copy()
        if calls.empty or puts.empty:
            return None
        pairs = calls.merge(puts, on=keys, suffixes=("_c", "_p"))
        pairs = pairs.loc[pairs.strike_price_c.gt(pairs.strike_price_p)].copy()
    else:
        pairs = eligible.loc[eligible.cp_flag.eq("C")].merge(
            eligible.loc[eligible.cp_flag.eq("P")], on=keys, suffixes=("_c", "_p")
        )
        pairs["strike_price_c"] = pairs["strike_price"]
        pairs["strike_price_p"] = pairs["strike_price"]
    if pairs.empty:
        return None
    pairs["dte"] = (pairs["exdate"] - pd.Timestamp(day)).dt.days
    pairs["maturity_error"] = (pairs["dte"] - 30).abs()
    pairs["delta_error"] = (pairs.delta_c - target).abs() + (pairs.delta_p + target).abs()
    return pairs.sort_values(
        ["maturity_error", "delta_error", "exdate", "strike_price_c", "strike_price_p",
         "optionid_c", "optionid_p"]
    ).iloc[0]


def price_pair(pair):
    mid = (pair.best_bid_c + pair.best_offer_c + pair.best_bid_p + pair.best_offer_p) / 2
    half = ((pair.best_offer_c - pair.best_bid_c) + (pair.best_offer_p - pair.best_bid_p)) / 2
    # IvyDB US vega is in quoted cents per one volatility point.
    vega = (pair.vega_c + pair.vega_p) / 100
    row = {
        "expiration": pair.exdate.date(), "dte": int(pair.dte),
        "contract_size": pair.contract_size, "am_settlement": pair.am_settlement,
        "expiry_indicator": pair.expiry_indicator, "straddle_or_strangle_mid": mid,
        "half_spread_usd": half, "half_spread_pct": 100 * half / mid,
        "vega_usd_per_vol_point": vega, "cost_vol_points": half / vega,
        "one_way_cost_per_pair_usd": half * pair.contract_size,
        "full_spread_cost_per_pair_usd": 2 * half * pair.contract_size,
    }
    for leg, side in (("call", "c"), ("put", "p")):
        for label, field in (
            ("optionid", "optionid"), ("strike", "strike_price"), ("delta", "delta"),
            ("bid", "best_bid"), ("ask", "best_offer"), ("vega", "vega"),
            ("volume", "volume"), ("open_interest", "open_interest"),
        ):
            value = pair[f"{field}_{side}"]
            row[f"{leg}_{label}"] = (
                int(value) if label == "optionid" else value / 1000 if label == "strike" else value
            )
    return row


def process_month(db, start, end, benchmarks, include_wings):
    calendar = get_calendar(db, start, end)
    constituents = get_top30(db, start, end)
    constituents = constituents.loc[constituents["date"].isin(calendar)]
    benchmark_rows = [
        {"date": day, "group": symbol, "ticker": symbol, "permno": None,
         "secid": secid, "link_count": 1}
        for day in calendar for symbol, secid in benchmarks.items()
    ]
    universe = pd.concat([constituents, pd.DataFrame(benchmark_rows)], ignore_index=True)
    secids = set(universe["secid"].dropna().astype(int))
    quotes = get_quotes(db, start, end, secids) if secids else pd.DataFrame()
    groups = {
        (day, int(secid)): frame
        for (day, secid), frame in quotes.groupby(["date", "secid"], sort=False)
    } if not quotes.empty else {}
    expected = constituents.groupby("date").size().reindex(calendar, fill_value=0)
    costs, skipped = [], []
    strategies = ["ATM_50D"] + (["OTM_25D"] if include_wings else [])
    for item in universe.to_dict("records"):
        link_count = item.pop("link_count")
        if pd.notna(item["secid"]):
            item["secid"] = int(item["secid"])
        day, secid = item["date"], item["secid"]
        group = groups.get((day, secid))
        atm = None
        for strategy in strategies:
            key = {**item, "strategy": strategy}
            if pd.isna(secid):
                reason = "ambiguous SECID" if link_count > 1 else "missing SECID"
            elif group is None:
                reason = "no eligible quotes"
            elif strategy == "ATM_50D":
                atm = select_pair(group, day, wing=False)
                if atm is not None:
                    costs.append({**key, **price_pair(atm)})
                    continue
                reason = "no compatible same-strike pair"
            elif atm is None:
                reason = "no ATM expiration for paired comparison"
            else:
                # Hold expiry and series terms fixed for the ATM/wing comparison.
                series = group.loc[group["exdate"].eq(atm.exdate)]
                for field in PAIR_COLUMNS[1:]:
                    value = atm[field]
                    series = series.loc[series[field].isna() if pd.isna(value) else series[field].eq(value)]
                wing = select_pair(series, day, wing=True, expiration=atm.exdate)
                if wing is not None:
                    costs.append({**key, **price_pair(wing)})
                    continue
                reason = "no compatible 25-delta wings on ATM expiry"
            skipped.append({**key, "reason": reason})
    calendar_frame = pd.DataFrame({
        "date": calendar.to_list(),
        "ranked_constituents": expected.to_numpy(),
    })
    return pd.DataFrame(costs, columns=COST_COLUMNS), pd.DataFrame(skipped, columns=FAIL_COLUMNS), calendar_frame


def grouped_costs(frame, keys):
    return frame.groupby(keys, as_index=False).agg(
        observations=("cost_vol_points", "size"),
        median_cost_vol_pts=("cost_vol_points", "median"),
        median_half_spread_pct=("half_spread_pct", "median"),
    )


def summarize(daily, calendar, include_wings, output, years):
    daily["year"] = pd.to_datetime(daily["date"]).dt.year
    calendar["year"] = pd.to_datetime(calendar["date"]).dt.year
    if calendar.empty:
        raise ValueError("No SPX calendar sessions returned from OptionMetrics.")
    write_csv(daily, output / "daily_execution_costs.csv")
    observed = grouped_costs(daily, ["year", "group", "strategy"])
    expected = []
    for year in years:
        days = calendar.loc[calendar.year.eq(year)]
        for group in ["SPX", "SPX_constituents", "DJX", "DIA"]:
            count = len(days) * (30 if group == "SPX_constituents" else 1)
            ranked = days["ranked_constituents"].sum() if group == "SPX_constituents" else count
            for strategy in ["ATM_50D"] + (["OTM_25D"] if include_wings else []):
                expected.append({"year": year, "group": group, "strategy": strategy,
                                 "expected_observations": count, "universe_rows": ranked})
    annual = pd.DataFrame(expected).merge(observed, how="left")
    annual["observations"] = annual["observations"].fillna(0).astype(int)
    annual["coverage_pct"] = 100 * annual["observations"] / annual["expected_observations"].replace(0, float("nan"))
    write_csv(annual, output / "annual_costs.csv")
    write_csv(grouped_costs(daily, ["year", "group", "ticker", "strategy"]),
              output / "annual_costs_by_ticker.csv")

    # Compare only dates where both DJX and DIA have valid observations.
    metrics = ["cost_vol_points", "half_spread_pct"]
    keys = ["year", "date", "strategy"]
    djx = daily.loc[daily.group.eq("DJX"), keys + metrics + ["dte"]]
    dia = daily.loc[daily.group.eq("DIA"), keys + metrics + ["dte"]]
    matched = djx.merge(dia, on=keys, suffixes=("_djx", "_dia"), validate="one_to_one")
    matched["dia_minus_djx_vol_pts"] = matched.cost_vol_points_dia - matched.cost_vol_points_djx
    matched["dia_minus_djx_price_pct_pts"] = matched.half_spread_pct_dia - matched.half_spread_pct_djx
    matched["same_dte"] = matched.dte_djx.eq(matched.dte_dia)
    summary = matched.groupby(["year", "strategy"], as_index=False).agg(
        matched_dates=("date", "size"),
        same_dte_dates=("same_dte", "sum"),
        median_djx_vol_pts=("cost_vol_points_djx", "median"),
        median_dia_vol_pts=("cost_vol_points_dia", "median"),
        median_djx_half_spread_pct=("half_spread_pct_djx", "median"),
        median_dia_half_spread_pct=("half_spread_pct_dia", "median"),
        median_dia_minus_djx_vol_pts=("dia_minus_djx_vol_pts", "median"),
        median_dia_minus_djx_price_pct_pts=("dia_minus_djx_price_pct_pts", "median"),
    )
    write_csv(summary, output / "annual_djx_vs_dia.csv")
    if include_wings:
        keys = ["year", "date", "group", "permno", "secid", "expiration"]
        atm = daily.loc[daily.strategy.eq("ATM_50D"), keys + metrics]
        wing = daily.loc[daily.strategy.eq("OTM_25D"), keys + metrics]
        matched = atm.merge(wing, on=keys, suffixes=("_atm", "_wing"), validate="one_to_one")
        matched["wing_minus_atm_vol_pts"] = matched.cost_vol_points_wing - matched.cost_vol_points_atm
        matched["wing_minus_atm_price_pct_pts"] = matched.half_spread_pct_wing - matched.half_spread_pct_atm
        summary = matched.groupby(["year", "group"], as_index=False).agg(
            matched_pairs=("date", "size"),
            median_atm_vol_pts=("cost_vol_points_atm", "median"),
            median_wing_vol_pts=("cost_vol_points_wing", "median"),
            median_atm_half_spread_pct=("half_spread_pct_atm", "median"),
            median_wing_half_spread_pct=("half_spread_pct_wing", "median"),
            median_wing_minus_atm_vol_pts=("wing_minus_atm_vol_pts", "median"),
            median_wing_minus_atm_price_pct_pts=("wing_minus_atm_price_pct_pts", "median"),
        )
        write_csv(summary, output / "annual_wings_vs_atm.csv")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2010, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dia-secid", type=int)
    parser.add_argument("--include-wings", action="store_true")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must be on or before --end")

    from src.data.wrds_connection import get_wrds_connection

    args.output.mkdir(parents=True, exist_ok=True)
    shards = args.output / "months"
    shards.mkdir(exist_ok=True)
    parts = {"quotes": [], "skipped": [], "calendar": []}
    db = get_wrds_connection()
    try:
        benchmarks = {**INDEX_SECIDS, "DIA": get_dia_secid(db, args.dia_secid)}
        if len(set(benchmarks.values())) != len(benchmarks):
            raise ValueError(f"Benchmark SECIDs must be distinct: {benchmarks}")
        for month in pd.period_range(args.start, args.end, freq="M"):
            first = max(args.start, month.start_time.date())
            last = min(args.end, month.end_time.date())
            tag = f"{first}_{last}_dia{benchmarks['DIA']}_wings{int(args.include_wings)}"
            paths = {label: shards / f"{tag}_{label}.csv" for label in parts}
            if not all(path.is_file() for path in paths.values()):
                frames = process_month(db, first, last, benchmarks, args.include_wings)
                for path, frame in zip(paths.values(), frames):
                    write_csv(frame, path)
            for label, path in paths.items():
                parts[label].append(pd.read_csv(path))
            print(f"{month}: {len(parts['quotes'][-1]):,} pairs", flush=True)
    finally:
        db.close()
    frames = {label: pd.concat(values, ignore_index=True) for label, values in parts.items()}
    write_csv(frames["skipped"], args.output / "skipped_execution_costs.csv")
    write_csv(frames["calendar"], args.output / "daily_universe_coverage.csv")
    summarize(frames["quotes"], frames["calendar"], args.include_wings, args.output,
              range(args.start.year, args.end.year + 1))


if __name__ == "__main__":
    main()
