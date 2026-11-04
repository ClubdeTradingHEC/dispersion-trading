"""Inspect retained forecasts and actual gaps; reporting never selects a model."""
from pathlib import Path
import os
import numpy as np
import pandas as pd
from .config import Config
from .dataset import inputs
from .diagnostics import annual_stationarity, residual_checks
from .inference import mean_test
from .store import dump
from .modeling import design, predict, train_for, hac_covariance, wald, scores
from .modeling import fit_least_squares
from .statistics import holm
# Keep the full financial sample distinct from the regression history filter.

def historical_gaps(cfg, calendar):
    """Keep the full financial sample distinct from the regression history filter."""
    panel = pd.read_parquet(Path(cfg['measurements_root']) / 'financial_panel.parquet')
    panel = panel.loc[(panel.basket == 'full') & panel.ic_status.eq('PASS') & panel.label_status.eq('PASS')]
    params = Config.read('configs/measurement.json')
    rows = []
    for years in [15, 10, 7, 5]:
        end = pd.Timestamp(cfg['evaluation_end'])
        grid = calendar[(calendar >= end - pd.DateOffset(years=years)) & (calendar <= end)]
        d = panel.loc[panel.date.isin(grid)]
        values = d.set_index('date').gap.reindex(grid).to_numpy(float)
        rows.append({
            'years': years,
            'partial_mapping_share': float((d.mapped_member_count < 30).mean()),
            **mean_test(values, 30, params)
        })
    return pd.DataFrame(rows)
# Reproduce the declared public-series approximation, not Faria's option engine.

def literature(root, cfg):
    """Reproduce the declared public-series approximation, not Faria's option engine."""
    source = Path(cfg['dataset_root']) / 'sources/public_ic_rc.parquet'
    if not source.exists():
        return {'status': 'SOURCE_UNAVAILABLE'}
    raw = pd.read_parquet(source).sort_values('date').reset_index(drop=True)
    if raw.date.duplicated().any() or not np.isfinite(raw[['SP500ic30', 'SP500rc30']]).all().all():
        raise ValueError('INVALID_PUBLIC_REFERENCE_SERIES')
    d = raw.loc[raw.date.between('1996-01-01', '2012-12-31')]
    rows = [{
        'name': 'Driessen_public_same_date',
        'n': len(d),
        'mean_gap': float((d.SP500ic30 - d.SP500rc30).mean())
    }]
    for lead in [20, 21, 22]:
        future = raw.SP500rc30.shift(-lead)
        ix = raw.date.between('2002-01-01', '2012-12-31') & future.notna()
        rows.append({
            'name': f'Faria_style_public_lead_{lead}',
            'n': int(ix.sum()),
            'mean_gap': float((raw.loc[ix, 'SP500ic30'] - future[ix]).mean())
        })
    result = {'status': 'APPROXIMATE_PRECOMPUTED_SERIES_NOT_EXACT_REPLICATION', 'results': rows}
    dump(result, root / 'analysis/literature_comparison.json')
    return result
# Write common-date scores, robust diagnostics, equations and readable figures.

def report(cfg):
    """Write common-date scores, robust diagnostics, equations and readable figures."""
    root = Path(cfg['output_root'])
    frame, calendar = inputs(cfg)
    models = root / 'models'
    p = pd.read_parquet(models / 'all_forecasts.parquet')
    generic = p.rename(columns={'specification': 'equation'}).merge(frame[['date', 'log_vol20']], on='date', validate='many_to_one')
    generic['method'] = 'OLS'
    residual, nonoverlap = residual_checks(generic, calendar)
    residual.to_csv(models / 'calibration_and_dependence.csv', index=False)
    nonoverlap.to_csv(models / 'nonoverlap_error_checks.csv', index=False)
    fields = [*cfg['common_features'], 'rc_future']
    annual_stationarity(frame, calendar, cfg, fields).to_csv(models / 'annual_stationarity.csv', index=False)
    # Fixed historical break tests are diagnostics, never an outcome-tuned refit.
    stability = []
    for model in ['A', 'B']:
        for spec, features in cfg['specifications'].items():
            train = train_for(frame, cfg['training_end'], model, cfg)
            for split in ['2015-01-01', '2019-01-01']:
                d = train.copy()
                d['post'] = (d.date >= pd.Timestamp(split)).astype(float)
                extra = ['post']
                for f in features:
                    d[f + '_post'] = d[f] * d.post
                    extra.append(f + '_post')
                terms = [*features, *extra]
                fit = fit_least_squares(d[terms], d.rc_future)
                for lag in [30, 60]:
                    cov = hac_covariance(
                        design(d, terms),
                        d.rc_future - predict(fit, d, terms),
                        d.date,
                        calendar,
                        lag=lag
                    )
                    test = wald(fit['coefficients'], cov, range(len(features) + 1, len(terms) + 1))
                    stability.append({'model': model, 'specification': spec, 'split': split, 'lag': lag, **test})
    stable = pd.DataFrame(stability)
    stable['p_holm'] = stable.groupby(['model', 'lag']).pvalue.transform(holm)
    stable.to_csv(models / 'stability_tests.csv', index=False)
    # Persistence/mean are transparent forecast benchmarks, not extra fitted equations.
    benchmarks = []
    for name in ['historical_mean', 'persistence']:
        d = p.loc[p.specification.eq('baseline')].copy()
        d['specification'] = name
        d['prediction'] = d.training_mean if name == 'historical_mean' else d.date.map(frame.set_index('date').rc_past)
        benchmarks.append(d)
    scores(pd.concat(benchmarks)).to_csv(models / 'benchmark_scores.csv', index=False)
    gaps = historical_gaps(cfg, calendar)
    (root / 'analysis').mkdir(exist_ok=True)
    gaps.to_csv(root / 'analysis/historical_gaps.csv', index=False)
    public = literature(root, cfg)
    # Render only retained models. All error units below are correlation points.
    score = pd.read_csv(models / 'forecast_scores.csv')
    final = score.loc[(score.phase == 'final') & (score.period == 'all')]
    coefficients = pd.read_csv(models / 'coefficients.csv')
    lines = [
        '# DJIA 30-day research results',
        '',
        'Four retained equations, each fitted as A (all eligible training) and B (fixed crash exclusions).',
        '',
        f"Training information: {cfg['training_start']} through {cfg['training_end']}. Final comparison: {cfg['evaluation_start']} through {cfg['evaluation_end']}. This period was inspected in earlier rounds; it is not fresh confirmation.",
        '',
        f'Prepared rows: {len(frame):,}; common eligible rows: {int(frame.complete_features.sum()):,}. Baselines and expanded equations use identical training-feature eligibility within each A/B design. Missing data are not zero-filled; early partial baskets remain labelled.',
        '',
        '| Equation | A RMSE | B RMSE | A MAE | B MAE |',
        '|---|---:|---:|---:|---:|'
    ]
    for spec in cfg['specifications']:
        d = final.loc[final.specification.eq(spec)].set_index('model')
        values = [100 * d.loc[m, metric] for metric in ['rmse', 'mae'] for m in ['A', 'B']]
        lines.append('| ' + spec + ' | ' + ' | '.join((f'{v:.3f}' for v in values)) + ' |')
    lines += [
        '',
        'Errors are correlation percentage points. Lower is better. Coefficient significance, paired-loss HAC/bootstrap intervals and yearly/non-overlap scores can be regenerated in `data/research/models/`. All four equations remain saved; there is no automatic winner selection.',
        '',
        '## Fitted equations',
        ''
    ]
    for row in coefficients.loc[coefficients.phase.eq('final')].itertuples():
        terms = ' + '.join((f'({getattr(row, f):.6f})*{f}' for f in cfg['specifications'][row.specification]))
        lines += [f'- {row.model}/{row.specification}: `RC_hat = {row.intercept:.6f} + {terms}`; training rows {row.n_train}.']
    lines += [
        '',
        'Signals are `IC - predicted future RC`, saved as decimals and correlation percentage points. They are not investment returns.',
        '',
        '## Historical actual gaps',
        '',
        '| Years | Mean gap (points) | HAC 95% interval (points) |',
        '|---|---:|---|'
    ]
    for row in gaps.itertuples():
        lines.append(f'| {row.years} | {100 * row.mean:.3f} | [{100 * row.ci_low:.3f}, {100 * row.ci_high:.3f}] |')
    lines += [
        '',
        'Nested windows are dependent. Positive average gaps are not proof of mispricing or tradable profit. The public Faria-style approximation remains about 4.63 points; it uses shifted precomputed series rather than Faria\u2019s original option data. Its calculation does not validate the raw-return calculator; explicit real-pair checks do.',
        '',
        '## Actual-gap exploration and limitations',
        '',
        'Actual IC minus subsequent RC quintiles/deciles and dated episodes can be regenerated in `data/research/analysis/`. No predicted thresholds enter these groups. Full-history exploration is descriptive and never selects model inputs. Larger positive gaps accompany lower future market volatility on average; event explanations are hypotheses, not causal identification.',
        '',
        'Overlapping outcomes create daily error dependence. HAC (15/30/60), block bootstrap and disjoint-window sensitivities accommodate it without pretending errors become independent. Calibration, variance, stationarity, collinearity, influence and coefficient stability diagnostics remain visible. B estimates a selected crash-free training sample. Source publication/vintage timing and early full-index equivalence remain uncertified. No independent scientific signoff or trading P&L is claimed.',
        '',
        'The previous five-variable model used broader history eligibility. Its exact original sample is checked in the retained verification receipt; this report uses a common sample for fair comparisons. Prior important aggregates are summarized in `docs/RESULTS.md`.',
        '',
        'Reusable dataset, models and final verification are retained in `important_data/`. Detailed phase outputs under `data/research/` are disposable and can be regenerated.'
    ]
    summary = '\n'.join(lines) + '\n'
    (root / 'RESULTS.md').write_text(summary, encoding='utf-8')
    (Path(cfg['dataset_root']) / 'RESULTS.md').write_text(summary, encoding='utf-8')
    # Keep figures readable and tied to the same saved forecast table.
    os.environ.setdefault('MPLCONFIGDIR', str(root / '.matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figures = root / 'figures'
    figures.mkdir(exist_ok=True)
    table = final.pivot(index='specification', columns='model', values='rmse').reindex(cfg['specifications'])
    ax = (100 * table).plot.bar(figsize=(9, 4), rot=20)
    ax.set_ylabel('RMSE (correlation points)')
    ax.set_title('Four retained equations on identical comparison dates')
    ax.figure.tight_layout()
    ax.figure.savefig(figures / 'model_errors.png', dpi=150)
    plt.close(ax.figure)
    return {'status': 'PASS', 'equations': 4, 'designs': 2, 'literature_status': public['status']}
