"""Explicit annual rate units and bracketed continuous ACT/365 curve interpolation."""

import numpy as np

from src.research.errors import DataError

def rate_convert(raw, unit, legacy=False):
    if not np.isfinite(raw) or raw <= -99:
        raise DataError("INVALID_RATE")
    if legacy or unit == "kevin":
        return raw / 100 if abs(raw) > 1 else raw
    if unit not in ("percent", "decimal"):
        raise DataError("RATE_UNIT_UNDECLARED")
    return raw / 100 if unit == "percent" else raw

def zero_rate(curve, date, days, unit, legacy=False):
    c = curve.loc[curve.date == date, ["days", "rate"]].sort_values("days")
    if c.empty:
        raise DataError("MISSING_ZERO_CURVE")
    if c.days.duplicated().any():
        raise DataError("DUPLICATE_ZERO_CURVE")
    x = c.days.to_numpy(float)
    y = c.rate.to_numpy(float)
    if (
        not np.isfinite(x).all()
        or (x <= 0).any()
        or not np.isfinite(y).all()
        or (y <= -99).any()
        or not np.isfinite(days)
        or days <= 0
    ):
        raise DataError("INVALID_ZERO_CURVE")
    if days < x.min() or days > x.max():
        raise DataError("UNBRACKETED_ZERO_CURVE")
    raw = float(np.interp(days, x, y))
    # Legacy converts nodes before interpolation, matching Kevin's old behavior.
    rate = (
        float(np.interp(days, x, [rate_convert(v, unit, legacy) for v in y]))
        if legacy or unit == "kevin"
        else rate_convert(raw, unit)
    )
    return raw, rate
