"""Overlap-aware inference on the original exchange-session grid."""
import numpy as np
import pandas as pd
from scipy.stats import norm
# Estimate a mean and HAC uncertainty on the original session grid.

def hac_mean(values, lag):
    """Estimate a mean and HAC uncertainty on the original session grid."""
    x = np.asarray(values, float)
    ok = np.isfinite(x)
    n = int(ok.sum())
    T = len(x)
    if n < 3:
        return {'n': n, 'status': 'INSUFFICIENT_SAMPLE'}
    mu = float(x[ok].mean())
    u = np.where(ok, x - mu, 0.0)
    lag = min(int(lag), max(0, T - 1))
    s = float(u @ u)
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * float(u[k:] @ u[:-k])
    se = np.sqrt(max(0, s * n / (n - 1))) / n
    z = mu / se if se > 0 else np.inf * np.sign(mu) if mu != 0 else 0.0
    return {
        'status': 'PASS',
        'n': n,
        'grid_n': T,
        'excluded': T - n,
        'mean': mu,
        'median': float(np.median(x[ok])),
        'sd': float(np.std(x[ok], ddof=1)),
        'se_hac': float(se),
        'lag_sessions': lag,
        'ci_low': mu - 1.96 * se,
        'ci_high': mu + 1.96 * se,
        'p_one_sided_positive': float(norm.sf(z))
    }
# Draw stationary-bootstrap blocks with a fixed expected block length.

def stationary_indices(T, block, rng):
    """Draw stationary-bootstrap blocks with a fixed expected block length."""
    pieces = []
    count = 0
    while count < T:
        length = min(int(rng.geometric(1 / block)), T - count)
        pieces.append((int(rng.integers(T)) + np.arange(length)) % T)
        count += length
    return np.concatenate(pieces)
# Bootstrap sample means while retaining missing-session positions.

def bootstrap_means(values, block, B, seed):
    """Bootstrap sample means while retaining missing-session positions."""
    x = np.asarray(values, float)
    if x.ndim == 1:
        x = x[:, None]
    rng = np.random.default_rng(seed)
    out = np.full((B, x.shape[1]), np.nan)
    for b in range(B):
        z = x[stationary_indices(len(x), max(1, block), rng)]
        sums = np.nansum(z, axis=0)
        counts = np.isfinite(z).sum(0)
        np.divide(sums, counts, out=out[b], where=counts > 0)
    return out
# Combine overlap-aware mean inference and declared equivalence diagnostics.

def mean_test(values, h, config, equivalence=None):
    """Combine overlap-aware mean inference and declared equivalence diagnostics."""
    x = np.asarray(values, float)
    res = hac_mean(x, h)
    if res['n'] < 3:
        return res
    boot = bootstrap_means(x, 2 * h, config.bootstrap_repetitions, config.seed).ravel()
    boot = boot[np.isfinite(boot)]
    if not len(boot):
        return {**res, 'bootstrap_status': 'NO_VALID_REPLICATES'}
    # Basic interval; centered bootstrap simulates the null of zero mean.
    q = np.quantile(boot, [0.025, 0.975])
    mu = res['mean']
    res.update(
        bootstrap_B=len(boot),
        bootstrap_block_sessions=2 * h,
        bootstrap_ci_low=float(2 * mu - q[1]),
        bootstrap_ci_high=float(2 * mu - q[0]),
        bootstrap_p_positive=float((1 + sum(boot - mu >= mu)) / (len(boot) + 1))
    )
    if equivalence is not None:
        q90 = np.quantile(boot, [0.05, 0.95])
        lo, hi = (2 * mu - q90[1], 2 * mu - q90[0])
        res.update(
            equivalence_margin=equivalence,
            equivalent_bias_90pct=bool(lo > -equivalence and hi < equivalence),
            equivalence_ci_low=float(lo),
            equivalence_ci_high=float(hi)
        )
    return res
# Assign the fixed descriptive historical regimes without outcome tuning.

def regime(date):
    """Assign the fixed descriptive historical regimes without outcome tuning."""
    date = pd.Timestamp(date)
    if pd.Timestamp('2007-07-01') <= date <= pd.Timestamp('2009-06-30'):
        return 'GFC'
    if pd.Timestamp('2020-02-01') <= date <= pd.Timestamp('2020-06-30'):
        return 'COVID'
    return 'other'
# Construct declared historical samples and exclusion sensitivities.

def sample_masks(grid, config):
    """Construct declared historical samples and exclusion sensitivities."""
    end = pd.Timestamp(config.entry_end)
    start = pd.Timestamp(config.entry_start)
    masks = {'full': (grid >= start) & (grid <= end)}
    for years in (10, 5, 2):
        masks[f'last_{years}y'] = (grid > end - pd.DateOffset(years=years)) & (grid <= end)
    masks['exclude_recent_2y'] = (grid >= start) & (grid <= end - pd.DateOffset(years=2))
    masks['exclude_oldest_2y'] = (grid >= start + pd.DateOffset(years=2)) & (grid <= end)
    for name, ranges in config.exclusions.items():
        mask = masks['full'].copy()
        for a, b in ranges:
            mask &= ~((grid >= pd.Timestamp(a)) & (grid <= pd.Timestamp(b)))
        masks[name] = mask
    for year in sorted(set(grid.year)):
        masks[f'year_{year}'] = grid.year == year
    for name in ('GFC', 'COVID', 'other'):
        masks[f'regime_{name}'] = np.array([regime(d) == name for d in grid])
    return masks
# Analyze financial gaps using coverage-aware chronological sample definitions.

def analyze(panel, calendar, config):
    """Analyze financial gaps using coverage-aware chronological sample definitions."""
    grid = pd.DatetimeIndex(calendar)
    grid = grid[(grid >= pd.Timestamp(config.entry_start)) & (grid <= pd.Timestamp(config.entry_end))]
    rows = []
    for (index, h, basket), d in panel.groupby(['index', 'horizon', 'basket']):
        d = d.set_index('date').reindex(grid)
        for target in ('gap', 'mic_gap'):
            if target not in d:
                continue
            x = d[target].to_numpy(float)
            if target == 'gap' and 'ic_status' in d:
                x[d.ic_status != 'PASS'] = np.nan
            for name, mask in sample_masks(grid, config).items():
                # Exclusions remain missing slots inside the original session grid.
                # Trim only sample endpoints, never compress internal missing dates.
                if not mask.any():
                    continue
                positions = np.flatnonzero(mask)
                a, b = (positions[0], positions[-1] + 1)
                v = np.where(mask[a:b], x[a:b], np.nan)
                result = mean_test(
                    v,
                    h,
                    config,
                    config.mic_equivalence_margin if target == 'mic_gap' else None
                )
                paired = d.iloc[a:b]
                if target == 'mic_gap' and {'mic', 'mic_rc_future'} <= set(paired):
                    good = mask[a:b] & np.isfinite(paired.mic) & np.isfinite(paired.mic_rc_future)
                    delta = (paired.mic - paired.mic_rc_future).to_numpy()[good]
                    result.update(
                        tracking_mae=float(np.abs(delta).mean()) if len(delta) else np.nan,
                        tracking_rmse=float(np.sqrt((delta ** 2).mean())) if len(delta) else np.nan,
                        tracking_correlation=float(paired.loc[good, ['mic', 'mic_rc_future']].corr().iloc[0, 1]) if good.sum() > 2 else np.nan
                    )
                rows.append({
                    'index': index,
                    'horizon': h,
                    'basket': basket,
                    'target': target,
                    'sample': name,
                    **result
                })
                if name == 'full':
                    for lag in sorted(set([max(1, h // 2), 2 * h])):
                        rows.append({
                            'index': index,
                            'horizon': h,
                            'basket': basket,
                            'target': target,
                            'sample': f'hac_lag_{lag}',
                            **hac_mean(v, lag)
                        })
                    for block in (h, 3 * h):
                        boot = bootstrap_means(v, block, config.bootstrap_repetitions, config.seed).ravel()
                        boot = boot[np.isfinite(boot)]
                        if len(boot):
                            rows.append({
                                'index': index,
                                'horizon': h,
                                'basket': basket,
                                'target': target,
                                'sample': f'bootstrap_block_{block}',
                                'n': int(np.isfinite(v).sum()),
                                'mean': float(np.nanmean(v)),
                                'bootstrap_ci_low': float(2 * np.nanmean(v) - np.quantile(boot, 0.975)),
                                'bootstrap_ci_high': float(2 * np.nanmean(v) - np.quantile(boot, 0.025))
                            })
                    for offset in (0, 5, 10):
                        selected = []
                        last = pd.Timestamp.min
                        for j, date in enumerate(grid[offset:]):
                            if date >= last and np.isfinite(x[j + offset]):
                                selected.append(x[j + offset])
                                last = date + pd.Timedelta(days=int(h))
                        rows.append({
                            'index': index,
                            'horizon': h,
                            'basket': basket,
                            'target': target,
                            'sample': f'nonoverlap_offset_{offset}',
                            **hac_mean(selected, 1)
                        })
    return pd.DataFrame(rows)
