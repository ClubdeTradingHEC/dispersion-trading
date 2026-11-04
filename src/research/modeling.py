"""Four retained OLS equations, paired A/B fitting and dependence-aware diagnostics."""
from pathlib import Path
from .store import dump
import warnings
import numpy as np
import pandas as pd
from scipy.stats import norm, chi2
from .statistics import holm, longest_run
from .inference import hac_mean, bootstrap_means
def fit_least_squares(X, y):
    """Fit standardized OLS and return coefficients in the original input units."""
    X, y = (np.asarray(X, float), np.asarray(y, float))
    if X.ndim != 2 or y.shape != (len(X),) or len(X) < X.shape[1] + 1:
        raise ValueError('INVALID_LINEAR_FIT_SHAPE')
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError('NONFINITE_LINEAR_INPUT')
    mu, sd = (X.mean(0), X.std(0))
    if (sd <= 1e-12).any():
        raise ValueError('CONSTANT_LINEAR_PREDICTOR')
    A = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    condition = np.linalg.cond(A)
    beta, _, rank, _ = np.linalg.lstsq(A, y, rcond=None)
    if rank != A.shape[1] or not np.isfinite(condition) or condition > 100000000.0:
        raise ValueError('ILL_CONDITIONED_LINEAR_FIT')
    raw = np.r_[beta[0] - np.sum(beta[1:] * mu / sd), beta[1:] / sd]
    return {
        'mu': mu,
        'sd': sd,
        'beta': beta,
        'coefficients': raw,
        'condition_number': float(condition)
    }


# Construct an intercept plus predictors in their original input units.

def design(frame, features):
    """Construct an intercept plus predictors in their original input units."""
    return np.column_stack([np.ones(len(frame)), frame[features].to_numpy(float)])
# Apply standardized fitted coefficients consistently with the shared solver.

def predict(fit, frame, features):
    """Apply standardized fitted coefficients consistently with the shared solver."""
    # Standardized evaluation matches the authoritative fitting path.
    return np.column_stack([
        np.ones(len(frame)),
        (frame[features].to_numpy(float) - fit['mu']) / fit['sd']
    ]) @ fit['beta']
# Score sandwich on real exchange positions, including missing-session gaps.

def hac_covariance(X, residual, dates, calendar, lag=30):
    """Score sandwich on real exchange positions, including missing-session gaps."""
    X = np.asarray(X, float)
    e = np.asarray(residual, float)
    dates = pd.DatetimeIndex(dates)
    grid = pd.DatetimeIndex(calendar)
    grid = grid[(grid >= dates.min()) & (grid <= dates.max())]
    positions = grid.get_indexer(dates)
    if len(set(dates)) != len(dates) or (positions < 0).any():
        raise ValueError('INVALID_HAC_DATES')
    scores = np.zeros((len(grid), X.shape[1]))
    scores[positions] = X * e[:, None]
    meat = scores.T @ scores
    for k in range(1, min(lag, len(grid) - 1) + 1):
        cross = scores[k:].T @ scores[:-k]
        meat += (1 - k / (lag + 1)) * (cross + cross.T)
    bread = np.linalg.inv(X.T @ X)
    return bread @ meat @ bread * len(e) / (len(e) - X.shape[1])
# Test declared coefficient restrictions using the supplied robust covariance.

def wald(beta, cov, indices):
    """Test declared coefficient restrictions using the supplied robust covariance."""
    ix = np.asarray(indices, int)
    if not len(ix):
        return {'df': 0, 'statistic': np.nan, 'pvalue': np.nan}
    sub = cov[np.ix_(ix, ix)]
    if np.linalg.matrix_rank(sub) != len(ix):
        return {'df': len(ix), 'statistic': np.nan, 'pvalue': np.nan}
    stat = float(beta[ix] @ np.linalg.solve(sub, beta[ix]))
    return {'df': len(ix), 'statistic': max(0, stat), 'pvalue': float(chi2.sf(max(0, stat), len(ix)))}
# Keep disjoint *actual* label windows, not a compressed session count.

def nonoverlap(frame, offset=0):
    """Keep disjoint *actual* label windows, not a compressed session count."""
    chosen = []
    last = pd.Timestamp.min
    for row in frame.sort_values('date').iloc[offset:].itertuples():
        if row.date > last:
            chosen.append(row.Index)
            last = pd.Timestamp(row.label_end)
    return frame.loc[chosen].copy()
# Select matured labels before cutoff, applying Model B exclusions only to training.

def train_for(frame, cutoff, model, cfg):
    """Select matured labels before cutoff, applying Model B exclusions only to training."""
    if model not in {'A', 'B'}:
        raise ValueError('UNKNOWN_TRAINING_DESIGN')
    if frame.date.duplicated().any():
        raise ValueError('DUPLICATE_ENTRY_DATE')
    cutoff = pd.Timestamp(cutoff)
    eligible = (frame.date >= pd.Timestamp(cfg['training_start'])) & (frame.date <= cutoff) & (frame.label_available_at <= cutoff) & frame.complete_features
    if model == 'B':
        eligible &= frame.eligible_B
    return frame.loc[eligible].sort_values('date').copy()
# Fit one approved OLS equation after checking the minimum training count.

def fit_one(train, features, cfg):
    """Fit one approved OLS equation after checking the minimum training count."""
    if len(train) < cfg['minimum_training_rows']:
        raise ValueError('INSUFFICIENT_TRAINING')
    return fit_least_squares(train[features], train.rc_future)


# A single chronological forecast block supports both the workflow and timing tests.
def forecast_block(frame, cutoff, first, last, model, features, cfg, development=False):
    """Fit on matured earlier outcomes and predict the declared later block."""
    if pd.Timestamp(cutoff) >= pd.Timestamp(first):
        raise ValueError('TRAINING_OVERLAPS_PREDICTION_BLOCK')
    train = train_for(frame, cutoff, model, cfg)
    fit = fit_one(train, features, cfg)
    test = frame.loc[frame.date.between(first, last) & frame.complete_features].copy()
    if development:
        test = test.loc[test.label_available_at <= pd.Timestamp(cfg['training_end'])]
    pred = test[['date', 'label_end', 'label_available_at', 'rc_future', 'ic']].copy()
    pred = pred.rename(columns={'rc_future': 'actual'})
    pred['prediction'] = predict(fit, test, features)
    pred['training_mean'] = train.rc_future.mean()
    return fit, train, pred
# Measure forecast errors on identical dates and retain yearly comparisons.

def scores(predictions):
    """Measure forecast errors on identical dates and retain yearly comparisons."""
    rows = []
    for (phase, model, spec), d in predictions.groupby(['phase', 'model', 'specification']):
        for period, part in [('all', d), *[(str(y), g) for y, g in d.groupby(d.date.dt.year)]]:
            e = part.prediction - part.actual
            base = part.training_mean - part.actual
            rows.append({
                'phase': phase,
                'model': model,
                'specification': spec,
                'period': period,
                'n': len(part),
                'rmse': np.sqrt(np.mean(e ** 2)),
                'mae': np.mean(abs(e)),
                'bias': np.mean(e),
                'r2_vs_training_mean': 1 - np.mean(e ** 2) / np.mean(base ** 2),
                'outside_correlation_bounds': int((abs(part.prediction) > 1).sum())
            })
    return pd.DataFrame(rows)
# Compare paired squared errors using HAC and block-bootstrap uncertainty.

def compare_losses(predictions, calendar, cfg):
    """Compare paired squared errors using HAC and block-bootstrap uncertainty."""
    rows = []
    for (phase, model), group in predictions.groupby(['phase', 'model']):
        p = group.pivot(index='date', columns='specification', values='prediction')
        y = group.drop_duplicates('date').set_index('date').actual
        for spec in p.columns:
            for ref in ['baseline', 'ic_only']:
                if spec == ref:
                    continue
                pair = p[[spec, ref]].dropna()
                actual = y.reindex(pair.index)
                diff = (pair[spec] - actual) ** 2 - (pair[ref] - actual) ** 2
                grid = pd.DatetimeIndex(calendar)
                grid = grid[(grid >= pair.index.min()) & (grid <= pair.index.max())]
                values = diff.reindex(grid).to_numpy()
                h = hac_mean(values, 30)
                boot = bootstrap_means(
                    values,
                    cfg['bootstrap_block_sessions'],
                    cfg['bootstrap_repetitions'],
                    cfg['seed']
                ).ravel()
                q = np.nanquantile(boot, [0.025, 0.975])
                mu = diff.mean()
                se = h.get('se_hac', np.nan)
                rows.append({
                    'phase': phase,
                    'model': model,
                    'specification': spec,
                    'benchmark': ref,
                    'n': len(pair),
                    'mean_mse_difference': mu,
                    'ci_low': h.get('ci_low'),
                    'ci_high': h.get('ci_high'),
                    'bootstrap_ci_low': 2 * mu - q[1],
                    'bootstrap_ci_high': 2 * mu - q[0],
                    'p_two_sided': 2 * norm.sf(abs(mu / se)) if se > 0 else np.nan
                })
    out = pd.DataFrame(rows)
    out['p_holm'] = out.groupby(['phase', 'model']).p_two_sided.transform(lambda x: holm(x))
    return out
# Report HAC coefficient and joint added-variable tests at fixed bandwidths.

def coefficient_tests(fit, train, features, calendar, model, spec, phase, fold):
    """Report HAC coefficient and joint added-variable tests at fixed bandwidths."""
    X = design(train, features)
    e = train.rc_future.to_numpy() - predict(fit, train, features)
    rows = []
    for lag in [15, 30, 60]:
        cov = hac_covariance(X, e, train.date, calendar, lag=lag)
        se = np.sqrt(np.maximum(np.diag(cov), 0))
        beta = fit['coefficients']
        for i, term in enumerate(['intercept', *features]):
            ratio = beta[i] / se[i] if se[i] > 0 else np.nan
            rows.append({
                'model': model,
                'specification': spec,
                'phase': phase,
                'fold': fold,
                'lag': lag,
                'term': term,
                'coefficient': beta[i],
                'se_hac': se[i],
                'robust_t_ratio': ratio,
                'p_two_sided': 2 * norm.sf(abs(ratio)),
                'ci_low': beta[i] - 1.96 * se[i],
                'ci_high': beta[i] + 1.96 * se[i],
                'added_term': term not in ['intercept', 'ic', 'rc_past']
            })
        extra = [
            i for i,
            n in enumerate(['intercept', *features]) if n not in ['intercept', 'ic', 'rc_past']
        ]
        joint = wald(beta, cov, extra)
        rows.append({
            'model': model,
            'specification': spec,
            'phase': phase,
            'fold': fold,
            'lag': lag,
            'term': 'JOINT_ADDED',
            'p_two_sided': joint['pvalue'],
            'wald_statistic': joint['statistic'],
            'wald_df': joint['df'],
            'added_term': True
        })
    return rows
# Test a residual auxiliary equation with calendar-aware robust covariance.

def auxiliary_test(y, frame, features, calendar):
    """Test a residual auxiliary equation with calendar-aware robust covariance."""
    if len(frame) < 40:
        return np.nan
    fit = fit_least_squares(frame[features], y)
    e = np.asarray(y) - predict(fit, frame, features)
    cov = hac_covariance(design(frame, features), e, frame.date, calendar, lag=30)
    return wald(fit['coefficients'], cov, range(1, len(features) + 1))['pvalue']
# Inspect variance, dependence, stationarity, collinearity and influential observations.

def diagnose(fit, train, features, calendar):
    """Inspect variance, dependence, stationarity, collinearity and influential observations."""
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tsa.stattools import adfuller, kpss
    X = design(train, features)
    e = train.rc_future.to_numpy() - predict(fit, train, features)
    h = np.einsum('ij,jk,ik->i', X, np.linalg.inv(X.T @ X), X)
    cook = e ** 2 / (np.sum(e ** 2) / (len(e) - X.shape[1])) / X.shape[1] * h / np.maximum(1 - h, 1e-10) ** 2
    d = train[['date']].copy()
    d['residual'] = e
    contiguous = longest_run(d, calendar)
    result = {
        'n': len(train),
        'last_label_available': train.label_available_at.max(),
        'condition_number': fit['condition_number'],
        'vif': {n: variance_inflation_factor(X, i + 1) for i, n in enumerate(features)},
        'variance_auxiliary_HAC_p': auxiliary_test(e ** 2, train, ['vol20', 'abs_return20', 'index_iv'], calendar),
        'variance_predictors_HAC_p': auxiliary_test(e ** 2, train, features, calendar),
        'classical_BP_p_not_serial_robust': het_breuschpagan(e, X)[1],
        'consecutive_run_n': len(contiguous),
        'consecutive_start': str(contiguous.date.min()),
        'consecutive_end': str(contiguous.date.max()),
        'cook_above_4_over_n': int((cook > 4 / len(train)).sum()),
        'stationarity': {},
        'warnings': []
    }
    if len(contiguous) > 80:
        result['ljung_box_residual_p'] = acorr_ljungbox(contiguous.residual, lags=[5, 10, 20], return_df=True).lb_pvalue.to_dict()
        result['acf1'] = contiguous.residual.autocorr(1)
        run = train.loc[train.date.isin(contiguous.date)]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            for f in dict.fromkeys([*features, 'rc_future']):
                adf = adfuller(run[f], autolag='AIC')
                kp = kpss(run[f], nlags='auto')
                result['stationarity'][f] = {'adf_p': adf[1], 'kpss_p_table_bound': kp[1]}
            result['warnings'] = sorted(set((str(v.message) for v in caught)))
    # HAC RESET-style check; powers of fitted values are a specification diagnostic.
    aux = train.copy()
    aux['fitted'] = predict(fit, train, features)
    aux['fitted_squared'] = aux.fitted ** 2
    try:
        f = fit_least_squares(aux[[*features, 'fitted_squared']], aux.rc_future)
        cov = hac_covariance(
            design(aux, [*features, 'fitted_squared']),
            aux.rc_future - predict(f, aux, [*features, 'fitted_squared']),
            aux.date,
            calendar
        )
        result['squared_fit_specification_HAC_p'] = wald(f['coefficients'], cov, [len(features) + 1])['pvalue']
    except ValueError:
        result['squared_fit_specification_HAC_p'] = None
    d['fitted'] = predict(fit, train, features)
    d['cooks_distance'] = cook
    keep = cook <= 4 / len(train)
    if keep.sum() > 252:
        alternative = fit_least_squares(train.loc[keep, features], train.loc[keep, 'rc_future'])
        result['influence_coefficient_change'] = dict(zip(
            ['intercept', *features],
            alternative['coefficients'] - fit['coefficients']
        ))
    # Independent statsmodels solve, a numerical check only (not independent research review).
    independent = sm.OLS(train.rc_future, X).fit()
    result['independent_coefficient_max_error'] = float(np.max(abs(independent.params - fit['coefficients'])))
    return (result, d)
# Fit all four A/B equations chronologically without choosing a winner.

def run_models(frame, calendar, cfg, root):
    """Fit all four A/B equations chronologically without choosing a winner."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    forecasts = []
    coeff = []
    beta = []
    failures = []
    fit_cache = {}
    training_rows = []
    for phase, folds in [
        ('development', cfg['development_years']),
        ('final', [int(cfg['evaluation_start'][:4])])
    ]:
        for year in folds:
            cutoff = pd.Timestamp(f'{year - 1}-12-31') if phase == 'development' else pd.Timestamp(cfg['training_end'])
            first = pd.Timestamp(f'{year}-01-01') if phase == 'development' else pd.Timestamp(cfg['evaluation_start'])
            last = pd.Timestamp(f'{year}-12-31') if phase == 'development' else pd.Timestamp(cfg['evaluation_end'])
            for model in ['A', 'B']:
                for spec, features in cfg['specifications'].items():
                    try:
                        fit, train, pred = forecast_block(frame, cutoff, first, last, model, features, cfg, development=phase == 'development')
                    except ValueError as exc:
                        failures.append({
                            'phase': phase,
                            'fold': year,
                            'model': model,
                            'specification': spec,
                            'reason': str(exc)
                        })
                        continue
                    assert train.label_available_at.max() < first
                    audit = train[['date', 'label_available_at']].copy()
                    audit['phase'] = phase
                    audit['fold'] = year
                    audit['model'] = model
                    audit['specification'] = spec
                    training_rows.append(audit)
                    pred['phase'] = phase
                    pred['fold'] = year
                    pred['model'] = model
                    pred['specification'] = spec
                    forecasts.append(pred)
                    coeff.append({
                        'phase': phase,
                        'fold': year,
                        'model': model,
                        'specification': spec,
                        'n_train': len(train),
                        'first_training_signal': train.date.min(),
                        'last_training_signal': train.date.max(),
                        'last_label_available': train.label_available_at.max(),
                        'condition_number': fit['condition_number'],
                        **dict(zip(['intercept', *features], fit['coefficients']))
                    })
                    beta.extend(coefficient_tests(fit, train, features, calendar, model, spec, phase, year))
                    if phase == 'final':
                        fit_cache[model, spec] = (fit, train, features)
                        dump(
                            {'features': features, 'coefficients': fit['coefficients']},
                            root / f'{model}_{spec}_fit.json'
                        )
    predictions = pd.concat(forecasts, ignore_index=True)
    predictions['signal_decimal'] = predictions.ic - predictions.prediction
    predictions['signal_percentage_points'] = 100 * predictions.signal_decimal
    predictions.to_parquet(root / 'all_forecasts.parquet', index=False)
    pd.concat(training_rows, ignore_index=True).to_parquet(root / 'training_rows.parquet', index=False)
    pd.DataFrame(coeff).to_csv(root / 'coefficients.csv', index=False)
    bt = pd.DataFrame(beta)
    bt['p_holm_added_family'] = np.nan
    for _, ix in bt.loc[bt.added_term].groupby(['phase', 'fold', 'model', 'lag']).groups.items():
        bt.loc[ix, 'p_holm_added_family'] = holm(bt.loc[ix, 'p_two_sided'])
    bt.to_csv(root / 'coefficient_tests.csv', index=False)
    scores(predictions).to_csv(root / 'forecast_scores.csv', index=False)
    compare_losses(predictions, calendar, cfg).to_csv(root / 'paired_loss_tests.csv', index=False)
    dump(failures, root / 'failures.json')
    predictions.loc[predictions.phase == 'final'].to_csv(root / 'signals.csv', index=False)
    diagnostics = {}
    nonoverlap_fits = []
    nonoverlap_scores = []
    for (model, spec), (fit, train, features) in fit_cache.items():
        diag, resid = diagnose(fit, train, features, calendar)
        diagnostics[f'{model}/{spec}'] = diag
        resid.to_parquet(root / f'{model}_{spec}_training_residuals.parquet', index=False)
        final = predictions.loc[(predictions.phase == 'final') & (predictions.model == model) & (predictions.specification == spec)]
        for offset in [0, 5, 10]:
            d = nonoverlap(final, offset)
            e = d.prediction - d.actual
            nonoverlap_scores.append({
                'model': model,
                'specification': spec,
                'offset': offset,
                'n': len(d),
                'rmse': np.sqrt(np.mean(e ** 2)),
                'mae': np.mean(abs(e)),
                'adjacent_nonoverlap_error_correlation': e.autocorr(1)
            })
        if spec in cfg['nonoverlap_fit']['specifications']:
            for offset in [0, 5, 10]:
                subset = nonoverlap(train, offset)
                if len(subset) < cfg['nonoverlap_fit']['minimum_training_rows']:
                    continue
                alternative = fit_least_squares(subset[features], subset.rc_future)
                test = frame.loc[frame.date.between(cfg['evaluation_start'], cfg['evaluation_end']) & frame.complete_features]
                error = predict(alternative, test, features) - test.rc_future.to_numpy()
                nonoverlap_fits.append({
                    'model': model,
                    'specification': spec,
                    'offset': offset,
                    'n_train': len(subset),
                    'n_test': len(test),
                    'rmse': np.sqrt(np.mean(error ** 2)),
                    'mae': np.mean(abs(error)),
                    **dict(zip(['intercept', *features], alternative['coefficients']))
                })
    dump(diagnostics, root / 'diagnostics.json')
    pd.DataFrame(nonoverlap_scores).to_csv(root / 'nonoverlap_scores.csv', index=False)
    pd.DataFrame(nonoverlap_fits).to_csv(root / 'nonoverlap_fit_sensitivity.csv', index=False)
    return predictions
