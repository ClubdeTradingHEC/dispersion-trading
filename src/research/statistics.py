"""Calendar-aware sample masks and multiple-testing utilities."""
import numpy as np
import pandas as pd
# Family-wise adjustment; no independence assumption is required.

def holm(pvalues):
    """Family-wise adjustment; no independence assumption is required."""
    p = np.asarray(pvalues, float)
    out = np.full(len(p), np.nan)
    valid = np.flatnonzero(np.isfinite(p))
    order = valid[np.argsort(p[valid])]
    if len(order):
        out[order] = np.minimum(1, np.maximum.accumulate(p[order] * (len(order) - np.arange(len(order)))))
    return out
# Exclude entry crashes and future-window crashes from fitting only.

def training_mask(dates, crash_dates, horizon=30):
    """Exclude entry crashes and future-window crashes from fitting only."""
    dates = pd.DatetimeIndex(dates)
    crashes = pd.DatetimeIndex(crash_dates)
    reasons = [','.join((c.strftime('%Y-%m-%d') for c in crashes[(crashes >= t) & (crashes <= t + pd.Timedelta(days=horizon))])) for t in dates]
    return pd.DataFrame({
        'date': dates,
        'eligible_B': [not r for r in reasons],
        'excluded_crash_dates': reasons
    }).set_index('date')
# Return a consecutive exchange-session run, never compress missing dates.

def longest_run(frame, calendar):
    """Return a consecutive exchange-session run, never compress missing dates."""
    positions = pd.Index(calendar).get_indexer(frame.date)
    starts = np.r_[0, np.flatnonzero(np.diff(positions) != 1) + 1, len(frame)]
    if not len(frame):
        return frame
    i = int(np.argmax(np.diff(starts)))
    return frame.iloc[starts[i]:starts[i + 1]]
