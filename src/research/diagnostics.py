"""Stationarity, calibration and residual checks; no parameter tuning."""
import warnings
import numpy as np
import pandas as pd
from .statistics import holm, longest_run
from .modeling import fit_least_squares
from .modeling import design, predict, hac_covariance, wald, nonoverlap, train_for

# Check ADF/KPSS on consecutive yearly runs without closing calendar gaps.

def annual_stationarity(frame, calendar, cfg, fields=None):
    """Check ADF/KPSS on consecutive yearly runs without closing calendar gaps."""
    from statsmodels.tsa.stattools import adfuller, kpss
    rows = []
    for model in ['A', 'B']:
        eligible_frame = train_for(frame, cfg['training_end'], model, cfg)
        for year, d in eligible_frame.groupby(eligible_frame.date.dt.year):
            run = longest_run(d, calendar)
            for field in fields or ['ic', 'rc_past', 'rc_future', 'return20', 'vol20']:
                row = {
                    'model': model,
                    'year': year,
                    'field': field,
                    'year_rows': len(d),
                    'consecutive_n': len(run),
                    'first': run.date.min(),
                    'last': run.date.max()
                }
                if len(run) < 60:
                    rows.append(row | {'status': 'INSUFFICIENT_CONSECUTIVE_RUN'})
                    continue
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    a = adfuller(run[field], autolag='AIC')
                    k = kpss(run[field], nlags='auto')
                rows.append(row | {
                    'status': 'COMPUTED_NOT_CERTIFICATION',
                    'adf_p': a[1],
                    'kpss_p_table_bound': k[1],
                    'warning': '; '.join(sorted(set((str(w.message) for w in caught))))
                })
    return pd.DataFrame(rows)
# Assess calibration, error dependence and non-overlapping outcome windows.

def residual_checks(predictions, calendar):
    """Assess calibration, error dependence and non-overlapping outcome windows."""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    rows = []
    nonoverlap_rows = []
    for (model, equation, method), d in predictions.loc[predictions.phase == 'final'].groupby(['model', 'equation', 'method']):
        d = d.sort_values('date').copy()
        d['error'] = d.prediction - d.actual
        run = longest_run(d, calendar)
        base = {'model': model, 'equation': equation, 'method': method}
        fitted = fit_least_squares(d[['prediction']], d.actual)
        covariance = hac_covariance(
            design(d, ['prediction']),
            d.actual - predict(fitted, d, ['prediction']),
            d.date,
            calendar
        )
        cal = wald(fitted['coefficients'] - np.array([0.0, 1.0]), covariance, [0, 1])
        x = d.copy()
        x['squared_error'] = d.error ** 2
        vf = fit_least_squares(x[['log_vol20']], x.squared_error)
        vc = hac_covariance(
            design(x, ['log_vol20']),
            x.squared_error - predict(vf, x, ['log_vol20']),
            x.date,
            calendar
        )
        row = base | {
            'n': len(d),
            'consecutive_n': len(run),
            'acf1': run.error.autocorr(1),
            'acf30': run.error.autocorr(30),
            'acf60': run.error.autocorr(60),
            'calibration_intercept': fitted['coefficients'][0],
            'calibration_slope': fitted['coefficients'][1],
            'calibration_joint_p': cal['pvalue'],
            'variance_HAC_p': wald(vf['coefficients'], vc, [1])['pvalue']
        }
        if len(run) > 80:
            lb = acorr_ljungbox(run.error, lags=[5, 20, 40, 60], return_df=True)
            row.update({f'ljung_box_{lag}_p': lb.loc[lag, 'lb_pvalue'] for lag in lb.index})
        rows.append(row)
        for offset in [0, 5, 10]:
            part = nonoverlap(d, offset)
            nonoverlap_rows.append(base | {
                'offset': offset,
                'n': len(part),
                'rmse': np.sqrt(np.mean(part.error ** 2)),
                'error_acf1': part.error.autocorr(1)
            })
    out = pd.DataFrame(rows)
    out['calibration_joint_p_holm'] = out.groupby('model').calibration_joint_p.transform(lambda p: holm(p))
    out['variance_p_holm'] = out.groupby('model').variance_HAC_p.transform(lambda p: holm(p))
    return (out, pd.DataFrame(nonoverlap_rows))
