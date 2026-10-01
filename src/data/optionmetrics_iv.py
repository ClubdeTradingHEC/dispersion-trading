import pandas as pd

from .option_pricing import invert_combined_iv


def _normalize_rate(rate):
    rate = float(rate)

    if abs(rate) > 1:
        return rate / 100.0

    return rate


def get_50delta_surface(
    db,
    secid,
    date,
    days=30,
):
    date = pd.Timestamp(date).date()
    year = date.year

    df = db.raw_sql(
        f"""
        SELECT
            cp_flag,
            delta,
            impl_volatility,
            impl_strike,
            impl_premium
        FROM optionm.vsurfd{year}
        WHERE secid = {int(secid)}
          AND date = '{date}'
          AND days = {int(days)}
          AND (
                (cp_flag = 'C' AND delta = 50)
             OR (cp_flag = 'P' AND delta = -50)
          )
        """
    )

    if df.empty:
        raise ValueError(
            f"No {days}D +/-50 delta surface "
            f"for SECID {secid} on {date}."
        )

    for column in ["delta", "impl_volatility", "impl_strike", "impl_premium"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    call = df[(df["cp_flag"] == "C") & (df["delta"] == 50)].dropna(
        subset=["impl_volatility", "impl_strike", "impl_premium"]
    )
    put = df[(df["cp_flag"] == "P") & (df["delta"] == -50)].dropna(
        subset=["impl_volatility", "impl_strike", "impl_premium"]
    )

    if call.empty or put.empty:
        raise ValueError(
            "Incomplete +/-50 delta surface."
        )

    call = call.iloc[0]
    put = put.iloc[0]

    return {
        "call_iv": float(
            call["impl_volatility"]
        ),
        "put_iv": float(
            put["impl_volatility"]
        ),
        "call_strike": float(
            call["impl_strike"]
        ),
        "put_strike": float(
            put["impl_strike"]
        ),
        "call_premium": float(
            call["impl_premium"]
        ),
        "put_premium": float(
            put["impl_premium"]
        ),
    }


def get_forward(
    db,
    secid,
    date,
    days=30,
):
    date = pd.Timestamp(date).date()
    year = date.year

    df = db.raw_sql(
        f"""
        SELECT DISTINCT forward_price
        FROM optionm.stdopd{year}
        WHERE secid = {int(secid)}
          AND date = '{date}'
          AND days = {int(days)}
          AND forward_price IS NOT NULL
        """
    )

    if df.empty:
        raise ValueError(
            f"No {days}D forward for "
            f"SECID {secid} on {date}."
        )

    values = (
        pd.to_numeric(
            df["forward_price"],
            errors="coerce",
        )
        .dropna()
        .unique()
    )

    if len(values) == 0:
        raise ValueError(
            "No valid forward found."
        )

    forward_min = float(values.min())
    forward_max = float(values.max())
    tolerance = max(1e-8, abs(forward_min) * 1e-8)

    if forward_max - forward_min > tolerance:
        raise ValueError(
            f"Multiple inconsistent {days}D standardized forwards found "
            f"for SECID {secid} on {date}: "
            f"{forward_min} to {forward_max}."
        )

    return float(values.mean())


def get_zero_rate(
    db,
    date,
    days=30,
):
    date = pd.Timestamp(date).date()

    curve = db.raw_sql(
        f"""
        SELECT days, rate
        FROM optionm.zerocd
        WHERE date = '{date}'
        ORDER BY days
        """
    )

    if curve.empty:
        raise ValueError(
            f"No zero curve for {date}."
        )

    curve["days"] = pd.to_numeric(curve["days"], errors="coerce")
    curve["rate"] = pd.to_numeric(curve["rate"], errors="coerce")
    curve = curve.dropna(subset=["days", "rate"]).copy()
    curve["rate"] = curve["rate"].map(_normalize_rate)

    if curve.empty:
        raise ValueError(f"No valid zero-curve observations for {date}.")

    exact = curve[
        curve["days"] == days
    ]

    if not exact.empty:
        return float(
            exact.iloc[0]["rate"]
        )

    lower_rows = curve[curve["days"] < days]
    upper_rows = curve[curve["days"] > days]

    if lower_rows.empty or upper_rows.empty:
        raise ValueError(
            f"Cannot interpolate a {days}D zero rate on {date}; "
            f"the curve does not bracket that maturity."
        )

    lower = lower_rows.iloc[-1]
    upper = upper_rows.iloc[0]

    d1 = float(
        lower["days"]
    )

    d2 = float(
        upper["days"]
    )

    r1 = float(
        lower["rate"]
    )

    r2 = float(
        upper["rate"]
    )

    w = (
        days - d1
    ) / (
        d2 - d1
    )

    return (
        r1
        + w * (r2 - r1)
    )


def get_average_50delta_iv(
    surface,
):
    return (
        surface["call_iv"]
        + surface["put_iv"]
    ) / 2


def get_combined_50delta_iv(
    db,
    secid,
    date,
    days=30,
):
    surface = get_50delta_surface(
        db,
        secid,
        date,
        days,
    )

    forward = get_forward(
        db,
        secid,
        date,
        days,
    )

    rate = get_zero_rate(
        db,
        date,
        days,
    )

    iv = invert_combined_iv(
        call_premium=surface[
            "call_premium"
        ],
        put_premium=surface[
            "put_premium"
        ],
        call_strike=surface[
            "call_strike"
        ],
        put_strike=surface[
            "put_strike"
        ],
        forward=forward,
        rate=rate,
        days=days,
    )

    return iv


def get_iv(
    db,
    secid,
    date,
    days=30,
    method="combined_50delta",
):
    if method == "combined_50delta":
        return get_combined_50delta_iv(
            db,
            secid,
            date,
            days,
        )

    if method == "average_50delta":
        surface = get_50delta_surface(
            db,
            secid,
            date,
            days,
        )

        return get_average_50delta_iv(
            surface
        )

    raise ValueError(
        f"Unknown IV method: {method}"
    )