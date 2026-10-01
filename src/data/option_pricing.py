from math import erf, exp, log, sqrt

from scipy.optimize import brentq


def normal_cdf(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def black_price(
    forward,
    strike,
    maturity,
    rate,
    sigma,
    cp_flag,
):
    sqrt_t = sqrt(maturity)

    d1 = (
        log(forward / strike)
        + 0.5 * sigma**2 * maturity
    ) / (sigma * sqrt_t)

    d2 = d1 - sigma * sqrt_t
    discount = exp(-rate * maturity)

    if cp_flag == "C":
        return discount * (
            forward * normal_cdf(d1)
            - strike * normal_cdf(d2)
        )

    if cp_flag == "P":
        return discount * (
            strike * normal_cdf(-d2)
            - forward * normal_cdf(-d1)
        )

    raise ValueError(
        f"Invalid cp_flag: {cp_flag}"
    )


def invert_combined_iv(
    call_premium,
    put_premium,
    call_strike,
    put_strike,
    forward,
    rate,
    days,
):
    maturity = days / 365.0

    target = (
        call_premium
        + put_premium
    )

    def objective(sigma):
        call = black_price(
            forward,
            call_strike,
            maturity,
            rate,
            sigma,
            "C",
        )

        put = black_price(
            forward,
            put_strike,
            maturity,
            rate,
            sigma,
            "P",
        )

        return (
            call
            + put
            - target
        )

    return brentq(
        objective,
        1e-6,
        5.0,
    )