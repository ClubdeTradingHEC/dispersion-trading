"""Package adapter; Black/rate calculations are shared with Kevin data APIs."""
from math import exp, log, sqrt, pi
import numpy as np
from .errors import DataError
from src.data.option_pricing import black_price, invert_combined_iv
from src.data.rates import zero_rate
# Solve a common two-leg package IV using the preserved vendor input conventions.

def package(surface, forwards, curve, secid, date, days, config):
    """Solve a common two-leg package IV using the preserved vendor input conventions."""
    s = surface.loc[(surface.secid == secid) & (surface.date == date) & (surface.days == days)]
    legs = []
    for flag, delta in (('C', 50), ('P', -50)):
        leg = s.loc[(s.cp_flag == flag) & (s.delta == delta)]
        if len(leg) == 0:
            raise DataError('MISSING_OPTION_LEG', flag)
        if len(leg) != 1:
            raise DataError('DUPLICATE_OPTION_LEG', flag)
        v = leg.iloc[0]
        v = v.copy()
        for field in ('impl_volatility', 'impl_strike', 'impl_premium', 'dispersion'):
            if field in v:
                try:
                    v[field] = float(v[field])
                except (TypeError, ValueError):
                    raise DataError('INVALID_OPTION_SENTINEL', field)
        if not np.isfinite(v[['impl_volatility', 'impl_strike', 'impl_premium']].astype(float)).all() or v.impl_volatility <= 0 or v.impl_strike <= 0 or (v.impl_premium < 0):
            raise DataError('INVALID_OPTION_SENTINEL', flag)
        if 'dispersion' in v:
            if not np.isfinite(v.dispersion) or v.dispersion < 0:
                raise DataError('INVALID_DISPERSION', flag)
            if config.max_dispersion is not None and v.dispersion > config.max_dispersion:
                raise DataError('EXCESSIVE_DISPERSION', flag)
        legs.append(v)
    f = forwards.loc[
        (forwards.secid == secid) & (forwards.date == date) & (forwards.days == days),
        'forward_price'
    ].to_numpy(float)
    if len(f) == 0:
        raise DataError('MISSING_FORWARD')
    if not np.isfinite(f).all() or (f <= 0).any():
        raise DataError('INVALID_FORWARD')
    if np.ptp(f) > max(1e-08, abs(f.min()) * 1e-08):
        raise DataError('CONFLICTING_FORWARD')
    forward = float(f.mean())
    raw, rate = zero_rate(curve, date, days, config.rate_unit)
    c, p = legs
    t = days / 365
    residuals = [
        black_price(forward, v.impl_strike, t, rate, v.impl_volatility, flag) - v.impl_premium for v,
        flag in zip(legs, ('C', 'P'))
    ]
    rel = [abs(e) / max(float(v.impl_premium), 1e-12) for e, v in zip(residuals, legs)]
    bad = any((
        abs(e) > config.repricing_abs_tol and r > config.repricing_rel_tol for e,
        r in zip(residuals, rel)
    ))
    if bad and config.quarantine_repricing:
        raise DataError('EXCESSIVE_REPRICING_RESIDUAL', str(residuals))
    iv = invert_combined_iv(
        c.impl_premium,
        p.impl_premium,
        c.impl_strike,
        p.impl_strike,
        forward,
        rate,
        days
    )
    premium_sum = float(c.impl_premium + p.impl_premium)
    package_residual = black_price(forward, c.impl_strike, t, rate, iv, 'C') + black_price(forward, p.impl_strike, t, rate, iv, 'P') - premium_sum
    vegas = []
    for v in legs:
        d1 = (log(forward / v.impl_strike) + 0.5 * v.impl_volatility ** 2 * t) / (v.impl_volatility * sqrt(t))
        vegas.append(exp(-rate * t) * forward * sqrt(t) * exp(-0.5 * d1 * d1) / sqrt(2 * pi))
    return {
        'iv': iv,
        'raw_rate': raw,
        'rate': rate,
        'rate_unit': config.rate_unit,
        'rate_compounding': config.rate_compounding,
        'day_count': config.day_count,
        'forward': forward,
        'call_strike': float(c.impl_strike),
        'put_strike': float(p.impl_strike),
        'call_premium': float(c.impl_premium),
        'put_premium': float(p.impl_premium),
        'call_iv': float(c.impl_volatility),
        'put_iv': float(p.impl_volatility),
        'call_dispersion': float(c.get('dispersion', np.nan)),
        'put_dispersion': float(p.get('dispersion', np.nan)),
        'average_iv': float((c.impl_volatility + p.impl_volatility) / 2),
        'vega_average_iv': float(np.average([c.impl_volatility, p.impl_volatility], weights=vegas)),
        'call_residual': residuals[0],
        'put_residual': residuals[1],
        'call_relative_residual': rel[0],
        'put_relative_residual': rel[1],
        'max_relative_residual': max(rel),
        'package_residual': package_residual,
        'package_relative_residual': abs(package_residual) / max(premium_sum, 1e-12),
        'quality_flag': bad,
        'strike_difference': float(c.impl_strike - p.impl_strike),
        'relative_strike_gap': float(abs(c.impl_strike - p.impl_strike) / forward),
        'call_forward_moneyness': float(c.impl_strike / forward - 1),
        'put_forward_moneyness': float(p.impl_strike / forward - 1)
    }
