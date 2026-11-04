"""Per-index/horizon calibration. No predetermined optimum and no future screening."""
import numpy as np
import pandas as pd
from .inference import bootstrap_means, regime
# Evaluate declared basket adequacy against the reference with held-out constraints.

def assess(panel, calendar, config):
    """Evaluate declared basket adequacy against the reference with held-out constraints."""
    scores = []
    decisions = []
    grid = pd.DatetimeIndex(calendar)
    cut = pd.Timestamp(config.calibration_end)
    metrics = list(config.basket_tolerances)
    for (index, h), group in panel.groupby(['index', 'horizon']):
        full = group.loc[group.basket == config.basket_reference].set_index('date')
        chosen = None
        calibration = []
        for basket, d in group.groupby('basket'):
            d = d.set_index('date')
            for phase, mask in (('calibration', grid <= cut), ('evaluation', grid > cut)):
                phase_grid = grid[mask & (grid >= pd.Timestamp(config.entry_start)) & (grid <= pd.Timestamp(config.entry_end))]
                ix = d.index.intersection(full.index).intersection(phase_grid)
                if not len(ix):
                    continue
                reduced = bool(basket not in ('full', 'reference_option_feasible', config.basket_reference) and (d.loc[ix, 'n_selected'] < full.loc[ix, 'n_selected']).all())
                arrays = []
                metrics_valid = []
                # A rule locked at the calibration cutoff cannot use forward
                # labels that were still unavailable then. Keep purged signals
                # as missing calendar slots, rather than shortening distances.
                pending = pd.Series(False, index=phase_grid)
                if phase == 'calibration' and any((m in metrics for m in ('rc_future', 'gap', 'mic_rc_future', 'mic_gap'))):
                    for frame in (d, full):
                        columns = {'label_available_at'}
                        if any((m in metrics for m in ('mic_rc_future', 'mic_gap'))):
                            columns.add('mic_label_available_at' if 'mic_label_available_at' in frame else 'label_available_at')
                        for column in columns:
                            available = pd.to_datetime(frame.reindex(phase_grid).get(column, pd.Series(pd.NaT, index=phase_grid)))
                            pending |= available.isna() | (available > cut)
                for metric in metrics:
                    if metric not in d or metric not in full:
                        continue
                    diff = (d.loc[ix, metric] - full.loc[ix, metric]).reindex(phase_grid)
                    invalid = (d.reindex(phase_grid).ic_status != 'PASS') | (full.reindex(phase_grid).ic_status != 'PASS') | pending
                    diff[invalid] = np.nan
                    arrays.append(diff.to_numpy(float))
                    metrics_valid.append(metric)
                if not arrays:
                    continue
                values = np.column_stack(arrays)
                complete = np.isfinite(values).all(1)
                # Common complete metric dates; joint blocks preserve cross-metric dependence.
                values[~complete] = np.nan
                n = int(complete.sum())
                coverage = n / max(1, len(phase_grid))
                joint = np.column_stack([values, abs(values), values ** 2])
                boot_all = bootstrap_means(joint, 2 * h, config.bootstrap_repetitions, config.seed)
                boot = boot_all[:, :len(arrays)]
                means = np.nanmean(values, axis=0) if n else np.full(len(arrays), np.nan)
                # Bonferroni simultaneous mean-equivalence intervals across objectives.
                alpha = 0.1 / max(1, len(metrics))
                passed = n >= config.basket_min_dates and coverage >= config.basket_min_coverage and (len(metrics_valid) == len(metrics))
                for j, metric in enumerate(metrics_valid):
                    v = values[:, j]
                    good = np.isfinite(v)
                    tol = config.basket_tolerances[metric]
                    b = boot[:, j]
                    b = b[np.isfinite(b)]
                    ci = 2 * means[j] - np.quantile(b, [1 - alpha / 2, alpha / 2]) if len(b) else [np.nan, np.nan]
                    rmse = float(np.sqrt(np.nanmean(v * v))) if n else np.nan
                    rmse_boot = np.sqrt(np.maximum(0, boot_all[:, 2 * len(arrays) + j]))
                    rmse_boot = rmse_boot[np.isfinite(rmse_boot)]
                    rmse_upper = float(np.quantile(rmse_boot, 1 - alpha)) if len(rmse_boot) else np.nan
                    success = bool(n >= config.basket_min_dates and coverage >= config.basket_min_coverage and (ci[0] > -tol) and (ci[1] < tol) and (rmse_upper <= tol))
                    passed &= success
                    a = d.reindex(phase_grid).loc[good, metric]
                    ref = full.reindex(phase_grid).loc[good, metric]
                    common = a.notna() & ref.notna()
                    scores.append({
                        'index': index,
                        'horizon': h,
                        'basket': basket,
                        'is_reduced_candidate': reduced,
                        'phase': phase,
                        'metric': metric,
                        'n_common': n,
                        'calendar_coverage': coverage,
                        'labels_unavailable_at_calibration_cutoff': int(pending.sum()),
                        'mean_selected_count': float(d.loc[ix, 'n_selected'].mean()),
                        'min_selected_count': int(d.loc[ix, 'n_selected'].min()),
                        'max_selected_count': int(d.loc[ix, 'n_selected'].max()),
                        'cap_coverage_mean': float(d.loc[ix, 'original_cap_coverage'].mean()),
                        'mean_incremental_seconds': float(d.loc[ix, 'incremental_compute_seconds'].mean()) if 'incremental_compute_seconds' in d else np.nan,
                        'bias': float(means[j]),
                        'mae': float(np.nanmean(abs(v))) if n else np.nan,
                        'rmse': rmse,
                        'rmse_upper_simultaneous': rmse_upper,
                        'tracking_correlation': float(a[common].corr(ref[common])) if common.sum() > 2 and a[common].std() > 0 and (ref[common].std() > 0) else np.nan,
                        'signal_agreement': float(np.mean(np.sign(a[common]) == np.sign(ref[common]))) if common.sum() else np.nan,
                        'ci_low': float(ci[0]),
                        'ci_high': float(ci[1]),
                        'tolerance': tol,
                        'passes': success
                    })
                    for name in ('GFC', 'COVID', 'other'):
                        select = np.array([regime(t) == name for t in phase_grid]) & good
                        if select.sum():
                            scores.append({
                                'index': index,
                                'horizon': h,
                                'basket': basket,
                                'phase': phase,
                                'metric': metric,
                                'regime': name,
                                'n_common': int(select.sum()),
                                'bias': float(v[select].mean()),
                                'mae': float(abs(v[select]).mean()),
                                'rmse': float(np.sqrt(np.mean(v[select] ** 2))),
                                'tolerance': tol,
                                'passes': bool(np.sqrt(np.mean(v[select] ** 2)) <= tol)
                            })
                if phase == 'calibration' and reduced:
                    calibration.append((float(d.loc[ix, 'n_selected'].mean()), basket, bool(passed)))
        candidates = sorted((t for t in calibration if t[2]))
        if candidates:
            chosen = candidates[0][1]
        evalrows = [r for r in scores if r['index'] == index and r['horizon'] == h and (r['basket'] == chosen) and (r['phase'] == 'evaluation') and ('regime' not in r)]
        evaluation_pass = bool(len(evalrows) == len(metrics) and all((r['passes'] for r in evalrows)))
        decisions.append({
            'index': index,
            'horizon': h,
            'calibration_end': config.calibration_end,
            'selected_rule': chosen,
            'evaluation_pass': evaluation_pass,
            'tolerances_confirmed': config.basket_tolerances_confirmed,
            'status': 'ACCEPTED' if chosen and evaluation_pass and config.basket_tolerances_confirmed else 'PROVISIONAL' if chosen and evaluation_pass else 'NO_ACCEPTED_RULE',
            'default_basket': 'full',
            'reference': config.basket_reference,
            'future_availability_screening': False,
            'calibration_uses_only_available_labels': True
        })
    return (pd.DataFrame(scores), decisions)
