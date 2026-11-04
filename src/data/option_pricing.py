"""Kevin Black formulas with explicit input, root and identification checks."""

from math import erf, exp, log, sqrt, pi

import numpy as np

from scipy.optimize import brentq

from src.research.errors import DataError



def normal_cdf(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))



def black_price(forward, strike, maturity, rate, sigma, cp_flag):
    if (
        not all(np.isfinite([forward, strike, maturity, rate, sigma]))
        or min(forward, strike, maturity, sigma) <= 0
    ):
        raise DataError("INVALID_PRICING_INPUT")
    if cp_flag not in ("C", "P"):
        raise DataError("INVALID_CP_FLAG")
    d1 = (log(forward / strike) + 0.5 * sigma * sigma * maturity) / (
        sigma * sqrt(maturity)
    )
    d2 = d1 - sigma * sqrt(maturity)
    n = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    return exp(-rate * maturity) * (
        forward * n(d1) - strike * n(d2)
        if cp_flag == "C"
        else strike * n(-d2) - forward * n(-d1)
    )

def invert_combined_iv(
    call_premium, put_premium, call_strike, put_strike, forward, rate, days
):
    if (
        not all(np.isfinite([call_premium, put_premium]))
        or min(call_premium, put_premium) < 0
    ):
        raise DataError("INVALID_PREMIUM")
    t = days / 365.0
    target = call_premium + put_premium
    f = lambda s: (
        black_price(forward, call_strike, t, rate, s, "C")
        + black_price(forward, put_strike, t, rate, s, "P")
        - target
    )
    try:
        root = brentq(f, 1e-6, 5.0, xtol=1e-12)
    except (ValueError, OverflowError) as e:
        raise DataError("PACKAGE_INVERSION_FAILURE", e) from e
    if abs(f(root)) > max(1e-8, target * 1e-9):
        raise DataError("PACKAGE_REPRICING_FAILURE")
    vega = 0.0
    for strike in (call_strike, put_strike):
        d1 = (log(forward / strike) + 0.5 * root * root * t) / (root * sqrt(t))
        vega += exp(-rate * t) * forward * sqrt(t) * exp(-0.5 * d1 * d1) / sqrt(2 * pi)
    if vega < 1e-8 * max(1.0, forward):
        raise DataError("PACKAGE_WEAK_IDENTIFICATION", vega)
    return float(root)
