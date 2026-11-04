import numpy as np
from .errors import DataError
# Compute package-IV-based pairwise IC without clamping raw estimates.

def implied_correlation(index_iv, w, iv):
    """Compute package-IV-based pairwise IC without clamping raw estimates."""
    w = np.asarray(w, float)
    iv = np.asarray(iv, float)
    if not np.isfinite(index_iv) or index_iv <= 0 or w.ndim != 1 or (iv.shape != w.shape) or (not np.isfinite(w).all()) or (not np.isfinite(iv).all()) or (w <= 0).any() or (iv <= 0).any() or (not np.isclose(w.sum(), 1)):
        raise DataError('INVALID_IC_INPUT')
    a = w * iv
    diag = a @ a
    den = a.sum() ** 2 - diag
    if den <= 1e-15:
        raise DataError('INVALID_IC_DENOMINATOR')
    num = index_iv ** 2 - diag
    ic = num / den
    return {
        'ic': float(ic),
        'ic_numerator': float(num),
        'ic_denominator': float(den),
        'ic_denominator_ratio': float(den / a.sum() ** 2),
        'ic_out_of_bounds': bool(abs(ic) > 1)
    }
# Matched Pearson aggregate, O(TN) on a complete common grid.

def pair_rc(x, a, explicit=False):
    """Matched Pearson aggregate, O(TN) on a complete common grid."""
    x = np.asarray(x, float)
    a = np.asarray(a, float)
    if x.ndim != 2 or x.shape[1] != len(a) or len(a) < 2 or (not np.isfinite(x).all()):
        raise DataError('INCOMPLETE_PAIR_GRID')
    if not np.isfinite(a).all() or (a <= 0).any():
        raise DataError('INVALID_PAIR_WEIGHT')
    z = x - x.mean(0)
    norm = np.linalg.norm(z, axis=0)
    if (norm <= 1e-15).any():
        raise DataError('ZERO_VARIANCE_RETURNS')
    z = z / norm
    den = a.sum() ** 2 - a @ a
    if den <= 1e-15:
        raise DataError('INVALID_IC_DENOMINATOR')
    if explicit:
        total = sum((a[i] * a[j] * float(np.corrcoef(x[:, i], x[:, j])[0, 1]) for i in range(len(a)) for j in range(i + 1, len(a))))
        return float(2 * total / den)
    return float((z @ a @ (z @ a) - a @ a) / den)
# Available-observation Pearson pairs, with explicit coverage and normalization.

def available_pair_rc(x, a, min_sessions=10):
    """Keep the entry basket; omit unavailable pairs rather than the whole date.

    Complete columns use the exact fast identity. Only pairs involving an
    incomplete/constant column need pairwise matching. Each Pearson correlation
    requires min_sessions common returns and nonzero variance. Entry pair weights
    are never replaced; the available-pair estimate explicitly divides by their
    covered mass. Missing returns are never zero-filled.
    """
    x, a = np.asarray(x, float), np.asarray(a, float)
    if x.ndim != 2 or a.shape != (x.shape[1],) or len(a) < 2 or len(x) < min_sessions:
        raise DataError('INSUFFICIENT_PAIR_OVERLAP')
    if not np.isfinite(a).all() or (a <= 0).any():
        raise DataError('INVALID_PAIR_WEIGHT')
    total = (a.sum() ** 2 - a @ a) / 2
    if total <= 5e-16:
        raise DataError('INVALID_IC_DENOMINATOR')
    complete = np.isfinite(x).all(axis=0)
    complete[complete] &= np.linalg.norm(x[:, complete] - x[:, complete].mean(0), axis=0) > 1e-15
    good = np.flatnonzero(complete)
    covered = (a[good].sum() ** 2 - a[good] @ a[good]) / 2
    numerator = covered * pair_rc(x[:, good], a[good]) if len(good) >= 2 else 0.0
    count = len(good) * (len(good) - 1) // 2
    minimum_overlap = len(x) if count else len(x) + 1
    # Avoid O(N^2) Python work for the common fully observed panel.
    for i in np.flatnonzero(~complete):
        for j in range(len(a)):
            if j == i or (not complete[j] and j < i):
                continue
            valid = np.isfinite(x[:, i]) & np.isfinite(x[:, j])
            n = int(valid.sum())
            if n < min_sessions:
                continue
            u, v = x[valid, i], x[valid, j]
            u, v = u - u.mean(), v - v.mean()
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu <= 1e-15 or nv <= 1e-15:
                continue
            norm = nu * nv
            mass = a[i] * a[j]
            numerator += mass * float(u @ v / norm)
            covered += mass
            count += 1
            minimum_overlap = min(minimum_overlap, n)
    if count == 0 or covered <= 0:
        raise DataError('INSUFFICIENT_PAIR_OVERLAP')
    coverage = float(np.clip(covered / total, 0, 1))
    missing = 1 - coverage
    contribution = float(numerator / total)
    return {
        'rc': float(numerator / covered),
        'pair_weight_coverage': coverage,
        'n_pairs_used': int(count),
        'n_pairs_total': len(a) * (len(a) - 1) // 2,
        'n_stocks_incomplete_or_constant': int((~complete).sum()),
        'n_missing_return_observations': int((~np.isfinite(x)).sum()),
        'minimum_pair_observations': int(minimum_overlap),
        'rc_method': 'complete_fast' if complete.all() else 'available_pair_proxy',
        'rc_available_pair_contribution': contribution,
        'rc_available_pair_lower_bound': contribution - missing,
        'rc_available_pair_upper_bound': contribution + missing,
    }

# Conservative complete-grid bounds with original entry pair weights.

def pair_rc_bounds(x, a):
    """Conservative bounds with original entry pair weights and missing columns.

    A pair is covered only if both columns contain the entire declared grid and
    have nonzero variance. Unknown correlations contribute their original mass
    times [-1, 1]; the covered contribution is never promoted to primary RC.
    """
    x, a = (np.asarray(x, float), np.asarray(a, float))
    if x.ndim != 2 or len(x) < 3 or a.shape != (x.shape[1],) or (len(a) < 2):
        raise DataError('INCOMPLETE_PAIR_GRID')
    if not np.isfinite(a).all() or (a <= 0).any():
        raise DataError('INVALID_PAIR_WEIGHT')
    den = a.sum() ** 2 - a @ a
    if den <= 1e-15:
        raise DataError('INVALID_IC_DENOMINATOR')
    usable = np.isfinite(x).all(axis=0)
    usable[usable] &= np.linalg.norm(x[:, usable] - x[:, usable].mean(axis=0), axis=0) > 1e-15
    good = a[usable]
    covered_den = good.sum() ** 2 - good @ good
    mass = float(np.clip(covered_den / den, 0, 1))
    contribution = mass * pair_rc(x[:, usable], good / good.sum()) if len(good) >= 2 and covered_den > 0 else 0.0
    missing = 1 - mass
    return {
        'rc_future_lower_bound': contribution - missing,
        'rc_future_upper_bound': contribution + missing,
        'rc_covered_pair_contribution': contribution,
        'missing_pair_mass': missing,
        'n_return_complete_nonconstant': int(usable.sum()),
        'rc_bounds_status': 'COMPLETE' if missing <= 1e-12 else 'PARTIAL_BOUNDS'
    }
# Compare MIC with definitionally matched stock-index realized measures.

def mic_comparators(x, index_returns, w, iv):
    """Compare MIC with definitionally matched stock-index realized measures."""
    x = np.asarray(x, float)
    y = np.asarray(index_returns, float)
    w = np.asarray(w, float)
    iv = np.asarray(iv, float)
    if x.ndim != 2 or len(x) < 2 or y.shape != (len(x),) or (w.shape != (x.shape[1],)) or (iv.shape != w.shape) or (not np.isfinite(x).all()) or (not np.isfinite(y).all()) or (not np.isfinite(w).all()) or (not np.isfinite(iv).all()) or (w <= 0).any() or (iv <= 0).any() or (not np.isclose(w.sum(), 1)):
        raise DataError('INVALID_MIC_INPUT')
    xc = x - x.mean(0)
    yc = y - y.mean()
    sx = np.linalg.norm(xc, axis=0)
    sy = np.linalg.norm(yc)
    if (sx <= 1e-15).any() or sy <= 1e-15:
        raise DataError('ZERO_VARIANCE_RETURNS')
    rho = xc.T @ yc / (sx * sy)
    a = w * iv
    basket = x @ w
    b = basket - basket.mean()
    sb = np.linalg.norm(b)
    valid_basket = sb > 1e-15
    rb = xc.T @ b / (sx * sb) if valid_basket else np.full(len(w), np.nan)
    realized_ratio = sb / (w @ sx)
    annual = np.sqrt(252 / (len(x) - 1))
    tracking = b - yc
    return {
        'mic_rc_future': float(a @ rho / a.sum()),
        'mic_rc_realized_vol_official': float(w * sx @ rho / (w @ sx)),
        'mic_rc_basket': float(w * sx @ rb / (w @ sx)),
        'mic_basket_vol_ratio': float(realized_ratio),
        'mic_identity_residual': float(w * sx @ rb / (w @ sx) - realized_ratio),
        'mic_basket_status': 'PASS' if valid_basket else 'ZERO_VARIANCE_BASKET',
        'reconstructed_basket_realized_vol': float(sb * annual),
        'official_index_realized_vol': float(sy * annual),
        'return_tracking_error_annual': float(np.linalg.norm(tracking) * annual),
        'return_tracking_correlation': float(b @ yc / (sb * sy)) if valid_basket else np.nan
    }
# Intentionally unmatched full-index IV; never use as a primary IC identity.

def original_weight_subset_diagnostic(index_iv, original_weights, iv):
    """Intentionally unmatched full-index IV; never use as a primary IC identity."""
    a = np.asarray(original_weights, float) * np.asarray(iv, float)
    den = a.sum() ** 2 - a @ a
    if den <= 1e-15:
        raise DataError('INVALID_IC_DENOMINATOR')
    return float((index_iv ** 2 - a @ a) / den)
# Compute historical stock-index MIV in volatility units, separately from pairwise IC.

def miv(w, iv, rho):
    """Compute historical stock-index MIV in volatility units, separately from pairwise IC."""
    if not np.isfinite(rho).all() or (abs(rho) > 1 + 1e-12).any():
        raise DataError('INVALID_HISTORICAL_CORRELATION')
    contributions = np.asarray(w) * np.asarray(iv) * np.asarray(rho)
    return (float(contributions.sum()), contributions)
