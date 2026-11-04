"""Daily-return dependence predictors; no WRDS calls or pricing changes."""
import numpy as np
# Require complete finite histories and positive frozen entry pair weights.

def validate_inputs(returns, a):
    """Require complete finite histories and positive frozen entry pair weights."""
    x = np.asarray(returns, float)
    a = np.asarray(a, float)
    if x.ndim != 2 or x.shape[0] < 2 or x.shape[1] < 2 or (a.shape != (x.shape[1],)):
        raise ValueError('INVALID_FEATURE_SHAPE')
    if not np.isfinite(x).all():
        raise ValueError('MISSING_OR_NONFINITE_HISTORY')
    if not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError('INVALID_ENTRY_PAIR_WEIGHTS')
    if a.sum() ** 2 - a @ a <= 1e-15:
        raise ValueError('INVALID_PAIR_DENOMINATOR')
    return (x, a)
# Exact weighted mean of off-diagonal inner products of unit columns.

def aggregate_normalized(z, a):
    """Exact weighted mean of off-diagonal inner products of unit columns."""
    diagonal = float(a @ a)
    den = float(a.sum() ** 2 - diagonal)
    basket = z @ a
    return float((basket @ basket - diagonal) / den)
# Aggregate time-weighted Pearson pairs after weighted demeaning.

def exponential_correlation(returns, a, half_life):
    """Aggregate time-weighted Pearson pairs after weighted demeaning."""
    x, a = validate_inputs(returns, a)
    if not np.isfinite(half_life) or half_life <= 0:
        raise ValueError('INVALID_HALF_LIFE')
    ages = np.arange(len(x) - 1, -1, -1, dtype=float)
    p = 2.0 ** (-ages / half_life)
    p /= p.sum()
    centered = x - p @ x
    z = np.sqrt(p[:, None]) * centered
    norm = np.linalg.norm(z, axis=0)
    if (norm <= 1e-15).any():
        raise ValueError('ZERO_VARIANCE_HISTORY')
    return aggregate_normalized(z / norm, a)
# Aggregate normalized negative-return products without demeaning.

def downside_comovement(returns, a, minimum_negative=10):
    """Aggregate normalized negative-return products without demeaning."""
    x, a = validate_inputs(returns, a)
    if minimum_negative < 1:
        raise ValueError('INVALID_NEGATIVE_COUNT')
    counts = (x < 0).sum(axis=0)
    if (counts < minimum_negative).any():
        raise ValueError('INSUFFICIENT_NEGATIVE_OBSERVATIONS')
    negative = np.minimum(x, 0.0)
    norm = np.linalg.norm(negative, axis=0)
    if (norm <= 1e-15).any():
        raise ValueError('ZERO_DOWNSIDE_NORM')
    # Deliberately uncentered. This is a semicorrelation-like cosine measure.
    return aggregate_normalized(negative / norm, a)
# Read exactly the required entry-or-earlier sessions for the frozen basket.

def entry_features(wide, calendar, date, identifiers, a, cfg):
    """Read exactly the required entry-or-earlier sessions for the frozen basket."""
    history = calendar[calendar <= date][-cfg['slow_history_sessions']:]
    if len(history) != cfg['slow_history_sessions']:
        raise ValueError('INSUFFICIENT_HISTORY_SESSIONS')
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('DUPLICATE_ENTRY_IDENTIFIER')
    x = wide.reindex(index=history, columns=identifiers).to_numpy(float)
    if not np.isfinite(x).all():
        raise ValueError('MISSING_HISTORY_252')
    n = cfg['downside_sessions']
    minimum = cfg['minimum_negative_sessions_per_stock']
    result = {
        'slow_rc': exponential_correlation(x, a, cfg['slow_half_life_sessions']),
        'downside_rc': downside_comovement(x[-n:], a, minimum),
        'feature_first_session': history[0],
        'feature_last_session': history[-1],
        'minimum_negative_count': int((x[-n:] < 0).sum(axis=0).min()),
        'feature_member_count': len(identifiers)
    }
    if not (-1 - 1e-12 <= result['slow_rc'] <= 1 + 1e-12 and -1e-12 <= result['downside_rc'] <= 1 + 1e-12):
        raise ValueError('FEATURE_OUT_OF_BOUNDS')
    return result
