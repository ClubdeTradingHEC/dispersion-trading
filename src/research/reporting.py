from pathlib import Path
import json
import pandas as pd
from .inference import analyze
from .subsets import assess
from .inputs import sha256
from .inference import regime


# Undersampled or constant report groups have no estimable correlation.
def _correlation(part, left, right, rank=False):
    """Report NaN without numerical warnings when a group cannot identify correlation."""
    values = part[[left, right]].dropna()
    if len(values) < 2 or values.nunique().min() < 2:
        return float('nan')
    if rank:
        values = values.rank()
    return values[left].corr(values[right])
# Report financial gaps and basket adequacy independently of OLS fitting.

def research(panel, calendar, config, root):
    """Report financial gaps and basket adequacy independently of OLS fitting."""
    if config.observation_end and (not panel.empty):
        from .inputs import sessions
        from .errors import DataError
        cutoff = pd.Timestamp(config.observation_end)
        valid = panel.get('label_status', pd.Series(index=panel.index, dtype=str)).eq('PASS')
        valid |= panel.get('mic_label_status', pd.Series(index=panel.index, dtype=str)).eq('PASS')
        if valid.any():
            if 'label_end' not in panel:
                raise DataError('LABEL_OBSERVATION_BOUND_REQUIRED')
            for end in pd.to_datetime(panel.loc[valid, 'label_end']).unique():
                if pd.isna(end) or sessions(pd.Timestamp(end) - pd.Timedelta(days=14), pd.Timestamp(end))[-1] > cutoff:
                    raise DataError(
                        'PANEL_EXCEEDS_OBSERVATION_CUTOFF',
                        'Remeasure cached inputs with the current cutoff before research.'
                    )
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    statistics = analyze(panel, calendar, config)
    baskets, decisions = assess(panel, calendar, config)
    tables = {'hypothesis_tests': statistics, 'basket_scores': baskets}
    common = []
    for (index, basket), group in panel.groupby(['index', 'basket']):
        sets = [set(group.loc[
            (group.horizon == h) & (group.ic_status == 'PASS') & (group.label_status == 'PASS'),
            'date'
        ]) for h in config.horizons]
        dates = set.intersection(*sets) if sets else set()
        common.append(group.loc[group.date.isin(dates)])
    common_panel = pd.concat(common, ignore_index=True) if common else panel.iloc[:0]
    tables['common_horizon_tests'] = analyze(common_panel, calendar, config) if not common_panel.empty else pd.DataFrame()
    branch = []
    if {'spread', 'gap', 'mic_gap'} <= set(panel):
        for (index, h, basket), d in panel.groupby(['index', 'horizon', 'basket']):
            d = d.loc[(d.ic_status == 'PASS') & (d.miv_status == 'PASS')].dropna(subset=['spread', 'gap', 'mic_gap']).copy()
            d['regime'] = d.date.map(regime)
            for name, part in [('full', d), *list(d.groupby('regime'))]:
                branch.append({
                    'index': index,
                    'horizon': h,
                    'basket': basket,
                    'sample': name,
                    'n_common': len(part),
                    'spread_gap_pearson': _correlation(part, 'spread', 'gap'),
                    'spread_gap_spearman': _correlation(part, 'spread', 'gap', rank=True),
                    'spread_mic_gap_pearson': _correlation(part, 'spread', 'mic_gap'),
                    'spread_gap_sign_agreement': float((part.spread.map(lambda x: x > 0) == part.gap.map(lambda x: x > 0)).mean()) if len(part) else None,
                    'interpretation': 'Different units; common-date association, not economic equivalence'
                })
    tables['branch_comparison'] = pd.DataFrame(branch)
    for name, df in tables.items():
        df.to_parquet(root / (name + '.parquet'), index=False)
    (root / 'basket_decisions.json').write_text(json.dumps(decisions, indent=2, default=str))
    counts = panel.groupby(['index', 'horizon', 'basket']).agg(
        observations=('date', 'size'),
        valid_ic=('ic_status', lambda s: (s == 'PASS').sum()),
        valid_miv=('miv_status', lambda s: (s == 'PASS').sum()),
        mature_labels=('label_status', lambda s: (s == 'PASS').sum())
    ).reset_index()
    counts.to_csv(root / 'coverage_counts.csv', index=False)
    summary = {
        'measurement_rows': len(panel),
        'hypothesis_rows': len(statistics),
        'basket_decisions': decisions,
        'live_wrds_integration': 'NOT_RUN_UNLESS_RECORDED_SEPARATELY',
        'independent_second_verification': 'NOT_RUN',
        'interpretation': 'Package-IV proxies; MIC exploratory; no profitability inference',
        'config': config.__dict__
    }
    (root / 'research_summary.json').write_text(json.dumps(summary, indent=2, default=str))
    content = '# Research output\n\n'
    content += f'{len(panel)} measurement rows. {len(statistics)} inference rows.\n\n'
    content += 'Read coverage_counts.csv first. Missing observations are retained with reason codes. Basket rules remain provisional until declared tolerances are confirmed and held-out tests pass. MIC compares stock–index correlations; IC compares stock–stock pairs.\n\n'
    content += 'Files: hypothesis_tests.parquet; basket_scores.parquet; basket_decisions.json; research_summary.json.\n'
    (root / 'REPORT.md').write_text(content)
    (root / 'report_manifest.json').write_text(json.dumps(
        {f.name: sha256(f) for f in root.iterdir() if f.is_file() and f.name != 'report_manifest.json'},
        indent=2
    ))
    return summary
