"""Descriptive actual IC–future-RC groups and episodes, independent of forecasts."""
from pathlib import Path
import numpy as np
import pandas as pd
from .store import dump
from .dataset import inputs
# Actual outcome sorting, independent of regression predictions/thresholds.

def explore(root, cfg):
    """Actual outcome sorting, independent of regression predictions/thresholds."""
    from .store import DiskBundle
    from .inputs import clean_returns
    root = Path(root)
    out = root / 'analysis'
    out.mkdir(exist_ok=True)
    panel, calendar = inputs(cfg)
    panel = panel.sort_values('date')
    ir = DiskBundle(cfg['raw_root']).read_table('index_returns').set_index('date')['return']
    # The saved constituent table is a partitioned directory, not a single file.
    src = Path(cfg['measurements_root'])
    constituents = pd.read_parquet(
        src / 'constituents.parquet',
        columns=['date', 'horizon', 'basket', 'permno']
    )
    constituents = constituents.loc[(constituents.basket == 'full') & (constituents.horizon == 30)]
    memberships = constituents.groupby('date').permno.apply(lambda s: sorted(set(s)))
    stocks = DiskBundle(cfg['raw_root']).read_table('returns')
    if stocks.duplicated(['date', 'permno']).any():
        raise ValueError('DUPLICATE_RETURN_GRAIN')
    stocks = clean_returns(stocks, calendar)
    return_quality_counts = stocks.loc[stocks._quality_code.ne(''), '_quality_code'].value_counts().to_dict()
    pivot = stocks.pivot(index='date', columns='permno', values='return').reindex(calendar)
    future = []
    for row in panel.itertuples():
        dates = calendar[(calendar > row.date) & (calendar <= row.label_end)]
        m = ir.reindex(dates)
        usable = len(dates) >= 10 and m.notna().all()
        members = memberships.get(row.date, [])
        before = pivot.loc[pivot.index <= row.date, members].tail(20)
        after = pivot.reindex(dates)[members]
        # Balanced entry-member panels only; never zero-fill or survivor-reweight.
        past_ok = len(before) == 20 and len(members) > 1 and before.notna().all().all()
        future_ok = len(after) >= 10 and len(members) > 1 and after.notna().all().all()
        future.append({
            'date': row.date,
            'future_index_return': np.prod(1 + m) - 1 if usable else np.nan,
            'future_index_volatility': m.std() * np.sqrt(252) if usable else np.nan,
            'past_stock_dispersion': before.std(axis=1, ddof=1).mean() if past_ok else np.nan,
            'future_stock_dispersion': after.std(axis=1, ddof=1).mean() if future_ok else np.nan,
            'dispersion_members': len(members),
            'future_index_complete': usable
        })
    panel = panel.merge(pd.DataFrame(future), on='date', validate='one_to_one')
    panel['market_direction'] = np.select(
        [panel.return20 > 0.02, panel.return20 < -0.02],
        ['rising', 'falling'],
        default='sideways'
    )
    all_groups = []
    episodes = []
    matches = []
    associations = []
    scopes = {
        'development': panel.loc[panel.label_available_at <= pd.Timestamp(cfg['training_end'])],
        'full_2011_2025': panel,
        'complete_mapping_period': panel.loc[panel.date >= pd.Timestamp('2020-08-31')]
    }
    fields = [
        'ic',
        'rc_future',
        'rc_past',
        'vol20',
        'return20',
        'index_iv',
        'drawdown252',
        'after_crash20',
        'past_stock_dispersion',
        'future_stock_dispersion',
        'future_index_return',
        'future_index_volatility'
    ]
    for scope, original in scopes.items():
        d = original.copy()
        for n in [5, 10]:
            labels = pd.qcut(d.gap, n, labels=False, duplicates='drop') + 1
            for group, part in d.groupby(labels):
                all_groups.append({
                    'scope': scope,
                    'groups': n,
                    'group': group,
                    'n': len(part),
                    'mean_gap': part.gap.mean(),
                    'first': part.date.min(),
                    'last': part.date.max(),
                    'partial_mapping_share': float((part.mapped_member_count < 30).mean()),
                    **{f'mean_{f}': part[f].mean() for f in fields},
                    **{f'n_{f}': int(part[f].notna().sum()) for f in fields},
                    **{f'{v}_share': part.market_direction.eq(v).mean() for v in ['rising', 'falling', 'sideways']}
                })
        d['decile'] = pd.qcut(d.gap, 10, labels=False, duplicates='drop') + 1
        scale = d[['vol20', 'return20', 'index_iv']].std()
        for tail, condition in [('positive', d.decile == 10), ('negative', d.decile == 1)]:
            z = d.loc[condition].sort_values('date').copy()
            z['episode'] = (z.date.diff() > pd.Timedelta(days=30)).cumsum()
            for episode, part in z.groupby('episode'):
                extreme = part.loc[part.gap.idxmax() if tail == 'positive' else part.gap.idxmin()]
                eid = f'{scope}_{tail}_{episode}'
                episodes.append({
                    'scope': scope,
                    'tail': tail,
                    'episode': eid,
                    'first': part.date.min(),
                    'last': part.date.max(),
                    'n_entries': len(part),
                    'representative_date': extreme.date,
                    'representative_gap': extreme.gap,
                    'mean_gap': part.gap.mean(),
                    **{f'mean_{f}': part[f].mean() for f in fields}
                })
                controls = d.loc[d.decile.between(4, 7) & (abs((d.date - extreme.date).dt.days) > 30) & (d.date.dt.year == extreme.date.year)].copy()
                fallback = False
                if controls.empty:
                    controls = d.loc[d.decile.between(4, 7) & (abs((d.date - extreme.date).dt.days) > 30) & (abs(d.date.dt.year - extreme.date.year) <= 1)].copy()
                    fallback = True
                controls = controls.dropna(subset=['vol20', 'return20', 'index_iv'])
                if controls.empty:
                    continue
                dist = ((controls[['vol20', 'return20', 'index_iv']] - extreme[['vol20', 'return20', 'index_iv']].astype(float)) / scale) ** 2
                controls['distance'] = np.sqrt(dist.sum(axis=1))
                control = controls.sort_values('distance').iloc[0]
                matches.append({
                    'scope': scope,
                    'episode': eid,
                    'tail': tail,
                    'extreme_date': extreme.date,
                    'control_date': control.date,
                    'adjacent_year_fallback': fallback,
                    'distance': control.distance,
                    'same_mapped_count': extreme.mapped_member_count == control.mapped_member_count,
                    **{f'extreme_{f}': extreme[f] for f in ['gap', *fields]},
                    **{f'control_{f}': control[f] for f in ['gap', *fields]}
                })
        # Differences in covariates: distributional associations, never causes.
        for field in [
            'vol20',
            'return20',
            'index_iv',
            'drawdown252',
            'past_stock_dispersion',
            'after_crash20'
        ]:
            for tail, condition in [('positive', d.decile == 10), ('negative', d.decile == 1)]:
                ordinary = d.decile.between(4, 7)
                a = d.loc[condition, field].dropna().astype(float)
                b = d.loc[ordinary, field].dropna().astype(float)
                associations.append({
                    'scope': scope,
                    'tail': tail,
                    'feature': field,
                    'n_tail': len(a),
                    'n_ordinary': len(b),
                    'tail_mean': a.mean(),
                    'ordinary_mean': b.mean(),
                    'difference': a.mean() - b.mean(),
                    'interpretation': 'outcome-selected exploratory association; not causal or a forecast test'
                })
    pd.DataFrame(all_groups).to_csv(out / 'actual_gap_groups.csv', index=False)
    pd.DataFrame(episodes).to_csv(out / 'actual_gap_episodes.csv', index=False)
    pd.DataFrame(matches).to_csv(out / 'matched_episode_controls.csv', index=False)
    pd.DataFrame(associations).to_csv(out / 'tail_associations.csv', index=False)
    panel.to_parquet(out / 'actual_gap_exploration_panel.parquet', index=False)
    dump(
        {
            'matching': 'nearest ordinary-gap observation in same calendar year, adjacent year fallback; normalized prior volatility/return/IV distance',
            'limitations': 'outcome selection, reused controls, overlap, missing sectors and official weight mass; no causal claim',
            'predictor_selection_uses_full_exploration': False,
            'no_predicted_thresholds': True,
            'dispersion_return_quality_exclusions': return_quality_counts,
            'scopes': {k: len(v) for k, v in scopes.items()},
            'future_index_unavailable': int(panel.future_index_return.isna().sum())
        },
        out / 'exploration_audit.json'
    )
