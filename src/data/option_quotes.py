
import argparse

import pandas as pd

from .wrds_connection import get_wrds_connection


# ============================================================
# FETCH OPTION QUOTES
# ============================================================

def get_option_quotes(
    db,
    secid,
    date,
    min_dte=20,
    max_dte=45,
):
    """
    Retrieve eligible near-ATM option contracts from OptionMetrics.

    Filters:
        - Maturity between min_dte and max_dte
        - Call delta between +0.40 and +0.60
        - Put delta between -0.60 and -0.40
        - Positive bid
        - Ask greater than bid
        - Positive vega
        - Standard contracts (ss_flag = '0')
    """

    date = pd.Timestamp(date).date()
    year = date.year

    query = f"""
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

        WHERE secid = {int(secid)}
          AND date = '{date}'

          AND exdate BETWEEN
              DATE '{date}' + {int(min_dte)}
              AND DATE '{date}' + {int(max_dte)}

          AND (
                (
                    cp_flag = 'C'
                    AND delta BETWEEN 0.40 AND 0.60
                )
                OR
                (
                    cp_flag = 'P'
                    AND delta BETWEEN -0.60 AND -0.40
                )
          )

          AND best_bid > 0
          AND best_offer > best_bid
          AND vega > 0
          AND ss_flag = '0'

        ORDER BY
            exdate,
            strike_price,
            cp_flag
    """

    df = db.raw_sql(
        query,
        date_cols=["date", "exdate"],
    )

    if df.empty:
        raise ValueError(
            f"No eligible quotes for secid={secid}, date={date}"
        )

    return df


# ============================================================
# BUILD CALL/PUT PAIRS
# ============================================================

def build_straddle_pairs(
    quotes,
    date,
    target_days=30,
):
    """
    Match calls and puts with identical:
        - expiration
        - strike
        - contract multiplier
        - settlement convention

    Calculate maturity distance, delta distance, and liquidity.
    """

    calls = quotes[
        quotes["cp_flag"] == "C"
    ].copy()

    puts = quotes[
        quotes["cp_flag"] == "P"
    ].copy()

    if calls.empty or puts.empty:
        raise ValueError(
            "Missing eligible calls or puts."
        )

    # Include settlement characteristics to avoid pairing
    # incompatible SPX contract series.
    pair_keys = [
        "exdate",
        "strike_price",
        "contract_size",
        "am_settlement",
        "expiry_indicator",
    ]

    pairs = calls.merge(
        puts,
        on=pair_keys,
        how="inner",
        suffixes=("_c", "_p"),
    )

    if pairs.empty:
        raise ValueError(
            "No compatible same-strike call/put pairs."
        )

    date = pd.Timestamp(date)

    # --------------------------------------------------------
    # Maturity
    # --------------------------------------------------------

    pairs["dte"] = (
        pairs["exdate"] - date
    ).dt.days

    pairs["maturity_distance"] = (
        pairs["dte"] - target_days
    ).abs()

    # --------------------------------------------------------
    # Delta distance
    # --------------------------------------------------------

    pairs["delta_distance"] = (
        (pairs["delta_c"] - 0.50).abs()
        + (pairs["delta_p"] + 0.50).abs()
    )

    # --------------------------------------------------------
    # Liquidity
    # --------------------------------------------------------

    pairs["min_open_interest"] = (
        pairs[
            ["open_interest_c", "open_interest_p"]
        ]
        .fillna(0)
        .min(axis=1)
    )

    pairs["total_volume"] = (
        pairs[
            ["volume_c", "volume_p"]
        ]
        .fillna(0)
        .sum(axis=1)
    )

    pairs["min_volume"] = (
        pairs[
            ["volume_c", "volume_p"]
        ]
        .fillna(0)
        .min(axis=1)
    )

    # --------------------------------------------------------
    # Spread metrics
    # --------------------------------------------------------

    pairs["call_mid"] = (
        pairs["best_bid_c"] + pairs["best_offer_c"]
    ) / 2

    pairs["put_mid"] = (
        pairs["best_bid_p"] + pairs["best_offer_p"]
    ) / 2

    pairs["straddle_mid"] = (
        pairs["call_mid"] + pairs["put_mid"]
    )

    pairs["half_spread_usd"] = (
        (pairs["best_offer_c"] - pairs["best_bid_c"])
        + (pairs["best_offer_p"] - pairs["best_bid_p"])
    ) / 2

    pairs["half_spread_pct"] = (
        100
        * pairs["half_spread_usd"]
        / pairs["straddle_mid"]
    )

    return pairs


# ============================================================
# SELECT STRADDLE
# ============================================================

def select_straddle_pair(
    pairs,
    selection_method="closest_30d",
    min_open_interest=100,
    max_maturity_distance=10,
):
    """
    Supported selection methods:

    closest_30d:
        1. Maturity closest to 30 days
        2. Delta pair closest to ATM

    liquidity_aware:
        1. Both legs have sufficient open interest
        2. Maturity within max_maturity_distance of 30 days
        3. Highest minimum open interest
        4. Highest combined volume
        5. Closest maturity
        6. Closest ATM delta

    Neither method chooses the cheapest bid/ask spread.
    """

    if selection_method == "closest_30d":

        selected = pairs.sort_values(
            by=[
                "maturity_distance",
                "delta_distance",
                "optionid_c",
                "optionid_p",
            ],
            ascending=[
                True,
                True,
                True,
                True,
            ],
        )

    elif selection_method == "liquidity_aware":

        selected = pairs[
            (pairs["min_open_interest"] >= min_open_interest)
            & (
                pairs["maturity_distance"]
                <= max_maturity_distance
            )
        ].copy()

        if selected.empty:
            raise ValueError(
                "No sufficiently liquid straddle near 30 days."
            )

        selected = selected.sort_values(
            by=[
                "min_open_interest",
                "total_volume",
                "maturity_distance",
                "delta_distance",
                "optionid_c",
                "optionid_p",
            ],
            ascending=[
                False,
                False,
                True,
                True,
                True,
                True,
            ],
        )

    else:
        raise ValueError(
            f"Unknown selection method: {selection_method}"
        )

    return selected.iloc[0]


# ============================================================
# CALCULATE TRANSACTION COSTS
# ============================================================

def calculate_straddle_cost(
    pair,
    date,
    secid,
    selection_method,
):
    """
    Calculate straddle transaction costs.

    OptionMetrics vega is interpreted as cents of option
    premium per 1 volatility percentage point.

    Divide by 100 to obtain dollars per vol point.

    Outputs:
        - One-way half-spread cost in dollars
        - Cost as percentage of straddle mid
        - One-way cost in volatility points
        - Full bid/ask spread cost
        - Contract-level dollar costs
    """

    call_bid = float(pair["best_bid_c"])
    call_ask = float(pair["best_offer_c"])

    put_bid = float(pair["best_bid_p"])
    put_ask = float(pair["best_offer_p"])

    call_mid = (call_bid + call_ask) / 2
    put_mid = (put_bid + put_ask) / 2

    straddle_bid = call_bid + put_bid
    straddle_ask = call_ask + put_ask

    straddle_mid = call_mid + put_mid

    full_spread = (
        straddle_ask - straddle_bid
    )

    half_spread = full_spread / 2

    # Convert OptionMetrics vega from cents to USD
    # for one percentage point of volatility.
    call_vega = float(pair["vega_c"]) / 100
    put_vega = float(pair["vega_p"]) / 100

    total_vega = call_vega + put_vega

    if straddle_mid <= 0:
        raise ValueError("Invalid straddle midpoint.")

    if total_vega <= 0:
        raise ValueError("Invalid straddle vega.")

    multiplier = float(
        pair["contract_size"]
    )

    cost_vol_points = (
        half_spread / total_vega
    )

    # --------------------------------------------------------
    # Liquidity flags
    # --------------------------------------------------------

    wide_spread_flag = (
        100 * half_spread / straddle_mid > 5
    )

    zero_volume_flag = (
        float(pair["volume_c"] or 0) == 0
        and float(pair["volume_p"] or 0) == 0
    )

    zero_oi_flag = (
        float(pair["open_interest_c"] or 0) == 0
        or float(pair["open_interest_p"] or 0) == 0
    )

    return {
        # Identification
        "date": str(pd.Timestamp(date).date()),
        "secid": int(secid),
        "selection_method": selection_method,

        # Expiration and strike
        "expiration": str(pair["exdate"].date()),
        "dte": int(pair["dte"]),
        "strike": float(pair["strike_price"]) / 1000,

        # Contract IDs
        "call_optionid": int(pair["optionid_c"]),
        "put_optionid": int(pair["optionid_p"]),

        # Delta
        "call_delta": float(pair["delta_c"]),
        "put_delta": float(pair["delta_p"]),
        "delta_distance": float(pair["delta_distance"]),

        # Individual bid/ask
        "call_bid": call_bid,
        "call_ask": call_ask,
        "put_bid": put_bid,
        "put_ask": put_ask,

        # Midpoints
        "call_mid": call_mid,
        "put_mid": put_mid,
        "straddle_bid": straddle_bid,
        "straddle_ask": straddle_ask,
        "straddle_mid": straddle_mid,

        # Spread costs
        "full_spread_usd": full_spread,
        "half_spread_usd": half_spread,
        "half_spread_pct": (
            100 * half_spread / straddle_mid
        ),

        # Vega
        "call_vega_usd_per_vol_point": call_vega,
        "put_vega_usd_per_vol_point": put_vega,
        "vega_usd_per_vol_point": total_vega,

        # Cost expressed in volatility points
        "cost_vol_points": cost_vol_points,
        "full_spread_vol_points": (
            full_spread / total_vega
        ),

        # Liquidity
        "call_volume": float(pair["volume_c"]),
        "put_volume": float(pair["volume_p"]),
        "call_open_interest": float(pair["open_interest_c"]),
        "put_open_interest": float(pair["open_interest_p"]),
        "min_open_interest": float(pair["min_open_interest"]),
        "total_volume": float(pair["total_volume"]),

        # Contract multiplier
        "contract_size": multiplier,

        # One straddle = one call + one put
        "one_way_cost_per_straddle_usd": (
            half_spread * multiplier
        ),
        "round_trip_cost_per_straddle_usd": (
            full_spread * multiplier
        ),

        # Quality flags
        "wide_spread_flag": bool(wide_spread_flag),
        "zero_volume_flag": bool(zero_volume_flag),
        "zero_oi_flag": bool(zero_oi_flag),
    }


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def get_atm_straddle_quotes(
    db,
    secid,
    date,
    target_days=30,
    selection_method="closest_30d",
    min_open_interest=100,
    max_maturity_distance=10,
):
    """
    Fetch, pair, select, and price an ATM straddle.
    """

    # 1. Get contracts
    quotes = get_option_quotes(
        db=db,
        secid=secid,
        date=date,
    )

    # 2. Form compatible call/put pairs
    pairs = build_straddle_pairs(
        quotes=quotes,
        date=date,
        target_days=target_days,
    )

    # 3. Select a pair
    pair = select_straddle_pair(
        pairs=pairs,
        selection_method=selection_method,
        min_open_interest=min_open_interest,
        max_maturity_distance=max_maturity_distance,
    )

    # 4. Calculate costs
    return calculate_straddle_cost(
        pair=pair,
        date=date,
        secid=secid,
        selection_method=selection_method,
    )


# ============================================================
# COMMAND-LINE INTERFACE
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compare historical ATM straddle transaction costs."
        )
    )

    parser.add_argument(
        "--secid",
        type=int,
        default=108105,
        help="OptionMetrics SECID (default: SPX 108105)",
    )

    parser.add_argument(
        "--date",
        default="2019-06-28",
        help="Quote date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--selection-method",
        choices=[
            "closest_30d",
            "liquidity_aware",
            "both",
        ],
        default="both",
    )

    parser.add_argument(
        "--min-open-interest",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--max-maturity-distance",
        type=int,
        default=10,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    methods = (
        ["closest_30d", "liquidity_aware"]
        if args.selection_method == "both"
        else [args.selection_method]
    )

    db = get_wrds_connection()

    try:
        for method in methods:
            print(
                f"\n{'=' * 55}"
                f"\nSECID {args.secid} | {args.date} | {method}"
                f"\n{'=' * 55}"
            )

            try:
                result = get_atm_straddle_quotes(
                    db=db,
                    secid=args.secid,
                    date=args.date,
                    selection_method=method,
                    min_open_interest=args.min_open_interest,
                    max_maturity_distance=args.max_maturity_distance,
                )

                print(
                    f"Expiration:          {result['expiration']}"
                )
                print(
                    f"Days to expiration:  {result['dte']}"
                )
                print(
                    f"Strike:              {result['strike']}"
                )
                print(
                    f"Call delta:          {result['call_delta']:.4f}"
                )
                print(
                    f"Put delta:           {result['put_delta']:.4f}"
                )
                print(
                    f"Minimum OI:          {result['min_open_interest']:.0f}"
                )
                print(
                    f"Total volume:        {result['total_volume']:.0f}"
                )
                print(
                    f"Straddle mid:        ${result['straddle_mid']:.4f}"
                )
                print(
                    f"Half-spread:         ${result['half_spread_usd']:.4f}"
                )
                print(
                    f"Half-spread / mid:   {result['half_spread_pct']:.4f}%"
                )
                print(
                    f"Cost (vol points):   {result['cost_vol_points']:.4f}"
                )
                print(
                    f"One-way contract TC: ${result['one_way_cost_per_straddle_usd']:.2f}"
                )
                print(
                    f"Wide spread flag:    {result['wide_spread_flag']}"
                )

            except ValueError as error:
                print(f"Skipped: {error}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
