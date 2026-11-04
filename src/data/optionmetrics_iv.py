import pandas as pd

import numpy as np
from .rates import zero_rate


def _rate_unit(db=None, unit=None):
    import os
    from src.research.errors import DataError
    selected = unit or getattr(db, "rate_unit", None) or os.environ.get("OPTIONMETRICS_RATE_UNIT") or "kevin"
    if selected not in ("percent", "decimal", "kevin"):
        raise DataError("RATE_UNIT_UNDECLARED", "Set OPTIONMETRICS_RATE_UNIT from vendor documentation.")
    return selected


def _normalize_rate(rate, unit=None):
    from .rates import rate_convert
    return rate_convert(float(rate), _rate_unit(unit=unit))


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
            impl_premium, dispersion
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

    if len(call) != 1 or len(put) != 1:
        raise ValueError(
            "Missing or duplicate +/-50 delta surface legs."
        )

    if len(df) != 2:
        raise ValueError("Invalid or duplicate +/-50 delta surface legs.")
    for leg in (call, put):
        values = leg[["impl_volatility", "impl_strike", "impl_premium"]].to_numpy(float)
        if not np.isfinite(values).all() or (values[:, :2] <= 0).any() or (values[:, 2] < 0).any():
            raise ValueError("Invalid option leg.")
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

    if not np.isfinite(pd.to_numeric(df.forward_price, errors="coerce")).all() or (values <= 0).any():
        raise ValueError("Invalid forward price.")
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


def get_zero_rate(db, date, days=30, rate_unit=None):
    date = pd.Timestamp(date).normalize()
    curve = db.raw_sql(f"SELECT days, rate FROM optionm.zerocd WHERE date = '{date.date()}' ORDER BY days").copy()
    curve["date"] = date
    return zero_rate(curve, date, days, _rate_unit(db, rate_unit))[1]


def get_average_50delta_iv(
    surface,
):
    return (
        surface["call_iv"]
        + surface["put_iv"]
    ) / 2


def get_combined_50delta_iv(db, secid, date, days=30, return_diagnostics=False):
    """Keep Kevin's float return by default; expose pricing diagnostics on request."""
    from src.research.config import Config
    from src.research.pricing import package
    date = pd.Timestamp(date).normalize()
    year = date.year
    surface = db.raw_sql(f"SELECT secid, date, days, cp_flag, delta, impl_volatility, impl_strike, impl_premium, dispersion FROM optionm.vsurfd{year} WHERE secid={int(secid)} AND date='{date.date()}' AND days={int(days)} AND ((cp_flag='C' AND delta=50) OR (cp_flag='P' AND delta=-50))", date_cols=["date"])
    forwards = db.raw_sql(f"SELECT secid, date, days, forward_price FROM optionm.stdopd{year} WHERE secid={int(secid)} AND date='{date.date()}' AND days={int(days)}", date_cols=["date"])
    curve = db.raw_sql(f"SELECT date, days, rate FROM optionm.zerocd WHERE date='{date.date()}' ORDER BY days", date_cols=["date"])
    for frame in (surface, forwards, curve):
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    result = package(surface, forwards, curve, int(secid), date, days, Config(rate_unit=_rate_unit(db)))
    result["zero_rate"] = result["rate"]
    return (result["iv"], result) if return_diagnostics else result["iv"]


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
