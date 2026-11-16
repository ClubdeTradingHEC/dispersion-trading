"""Optional index-level Marshall replication hurdle, independent of costs."""
from math import isfinite


def passes_marshall_hurdle(ioiv, miv, *, enabled=False, iv_unit='decimal'):
    """Evaluate once per index signal, never per leg, execution or hedge.

    Repository index_atm_iv/index_iv and miv are decimals; percentage-point
    inputs must be explicitly declared. Equality passes the hurdle.
    This is only hurdle eligibility, not a complete trading-entry rule.
    """
    thresholds = {'decimal': 0.0409, 'percentage_points': 4.09}
    if iv_unit not in thresholds:
        raise ValueError('IV unit must be decimal or percentage_points')
    if not (isfinite(ioiv) and isfinite(miv)):
        raise ValueError('Index IV and MIV must be finite')
    return not enabled or abs(ioiv - miv) >= thresholds[iv_unit]
