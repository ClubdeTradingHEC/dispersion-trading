"""Team event calculations, kept separate from forward package-IV-weighted RC."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from src.research.measurement import pair_rc
from src.research.inputs import sessions


# Validate long-format exports without inventing returns or silently dropping duplicates.
def returns_panel(raw):
    raw = raw.copy()
    required = {'date', 'permno', 'weight', 'daily_return'}
    if required - set(raw):
        raise ValueError('Returns require date, permno, weight, daily_return')
    raw['date'] = pd.to_datetime(raw['date'])
    if raw.empty:
        raise ValueError('Empty returns panel')
    if raw.date.dt.tz is not None or not raw.date.equals(raw.date.dt.normalize()):
        raise ValueError('Use timezone-free session dates, not intraday timestamps')
    if 'index' in raw:
        raw['index'] = raw['index'].astype('string').str.strip().str.upper()
        if raw['index'].isna().any() or raw['index'].nunique() != 1:
            raise ValueError('Use exactly one index per returns panel')
    identifiers = pd.to_numeric(raw.permno, errors='raise')
    if not np.isfinite(identifiers).all() or (identifiers <= 0).any() or (identifiers % 1 != 0).any():
        raise ValueError('PERMNO must be a positive integer')
    raw['permno'] = identifiers.astype('int64')
    if raw[['date', 'permno']].isna().any().any() or raw.duplicated(['date', 'permno']).any():
        raise ValueError('Missing or duplicate date/PERMNO')
    for name in ['weight', 'daily_return']:
        raw[name] = pd.to_numeric(raw[name], errors='raise')
        if np.isinf(raw[name]).any():
            raise ValueError('Infinite return/weight')
    if raw.weight.dropna().lt(0).any():
        raise ValueError('Negative weight')
    if (raw.groupby('date').weight.sum() > 1 + 1e-8).any():
        raise ValueError('Daily weights exceed one; use decimal constituent weights')
    grid = sessions(raw.date.min(), raw.date.max())
    if not raw.date.isin(grid).all():
        raise ValueError('Returns contain non-exchange sessions')
    return raw.sort_values(['date', 'permno'])


# Preserve the team's trailing 30 observed sessions and endpoint cap-weighted pairs.
def basket_correlation(raw, window=30):
    if window < 2:
        raise ValueError('window must be at least two sessions')
    raw = returns_panel(raw)
    ret = raw.pivot(index='date', columns='permno', values='daily_return').sort_index()
    # A whole missing day must remain missing, not shorten a 30-session window.
    ret = ret.reindex(sessions(ret.index.min(), ret.index.max()))
    weights = raw.pivot(index='date', columns='permno', values='weight').reindex_like(ret)
    rows = []
    for i in range(window - 1, len(ret)):
        day = ret.index[i]
        x = ret.iloc[i-window+1:i+1]
        members = weights.loc[day].dropna()
        members = members[members > 0]
        complete = x[members.index].notna().all()
        varying = x[members.index].std() > 1e-15
        names = members.index[complete & varying]
        row = {'date': day, 'n_stocks': len(names), 'n_excluded': len(members)-len(names),
               'rc_basket': np.nan, 'rc_equal_weight': np.nan,
               'available_entry_weight': float(members.loc[names].sum()),
               'status': 'INSUFFICIENT_STOCKS'}
        if len(names) >= 2:
            w = members.loc[names].to_numpy(float)
            w /= w.sum()
            row.update(rc_basket=pair_rc(x[names].to_numpy(), w),
                       rc_equal_weight=pair_rc(x[names].to_numpy(), np.ones(len(names))), status='PASS')
        rows.append(row)
    if not rows:
        raise ValueError('Not enough observed sessions for the trailing window')
    return pd.DataFrame(rows)


# Keep the team's contemporaneous weighted-return proxy, but expose missing coverage.
def market_proxy(raw):
    raw = returns_panel(raw)
    rows = []
    for day, group in raw.groupby('date', sort=True):
        valid = group.daily_return.notna() & group.weight.notna() & group.weight.gt(0)
        weight_mass = group.loc[valid, 'weight'].sum()
        missing = int((group.weight.gt(0) & group.daily_return.isna()).sum())
        value = (group.loc[valid, 'weight'] * group.loc[valid, 'daily_return']).sum()
        # A partial same-day sum is not silently represented as the full market return.
        value = float(value) if missing == 0 and np.isclose(weight_mass, 1) else np.nan
        breadth = (np.sign(group.loc[valid, 'daily_return']) == np.sign(value)).mean() if np.isfinite(value) else np.nan
        rows.append({'date': day, 'index_return': value, 'breadth': breadth,
                     'return_weight_coverage': weight_mass, 'missing_returns': missing})
    result = pd.DataFrame(rows).set_index('date')
    return result.reindex(sessions(result.index.min(), result.index.max()))


# The future volatility window excludes entry and requires every next session.
def vix_overlay(correlation, raw, vix, horizon=21):
    if horizon < 2:
        raise ValueError('horizon must be at least two sessions')
    correlation = correlation_series(correlation)
    market = market_proxy(raw)
    idx = market.index_return
    forward = idx.iloc[::-1].rolling(horizon, min_periods=horizon).std().iloc[::-1].shift(-1)
    vix = vix.copy()
    vix.index = pd.to_datetime(vix.index)
    vix = pd.to_numeric(vix.replace('.', np.nan), errors='raise').sort_index()
    if vix.index.has_duplicates or vix.index.hasnans or vix.index.tz is not None:
        raise ValueError('Invalid or duplicate VIX dates')
    if np.isinf(vix).any() or vix.dropna().le(0).any():
        raise ValueError('VIX must be positive annualized percentage points')
    # Union first, so an earlier observation outside the correlation grid is retained.
    aligned = vix.reindex(vix.index.union(correlation.index)).sort_index().ffill().reindex(correlation.index)
    result = pd.DataFrame({'rc_basket': correlation, 'vix': aligned,
                          'fwd_realized_vol': forward.reindex(correlation.index)*np.sqrt(252)*100})
    observations = pd.Series(vix.dropna().index, index=vix.dropna().index)
    observation_dates = observations.reindex(observations.index.union(correlation.index)).sort_index().ffill().reindex(correlation.index)
    result['vix_observation_date'] = pd.to_datetime(observation_dates)
    result['vix_age_calendar_days'] = (pd.Series(result.index,index=result.index)-result.vix_observation_date).dt.days
    result['realized_above_vix'] = (result.fwd_realized_vol > result.vix).astype(float)
    result.loc[result[['vix','fwd_realized_vol']].isna().any(axis=1), 'realized_above_vix'] = np.nan
    return result


# Correlation files must represent one daily trailing basket, not IC values or duplicates.
def correlation_series(values):
    values = values.copy()
    values.index = pd.DatetimeIndex(values.index)
    if values.empty or values.index.has_duplicates or values.index.hasnans or values.index.tz is not None:
        raise ValueError('Invalid or duplicate correlation dates')
    if not values.index.equals(values.index.normalize()):
        raise ValueError('Use session dates for correlation')
    values = pd.to_numeric(values, errors='raise').sort_index()
    if np.isinf(values).any() or values.dropna().abs().gt(1 + 1e-8).any():
        raise ValueError('Realized correlation must be a decimal between -1 and 1')
    if not values.index.isin(sessions(values.index.min(), values.index.max())).all():
        raise ValueError('Correlation contains non-exchange sessions')
    return values


# Preserve event-day changes and broad-move grouping; legacy p-values are descriptive.
def event_study(correlation, events, raw, big_move=.015, breadth=.80):
    correlation = correlation_series(correlation)
    correlation = correlation.reindex(sessions(correlation.index.min(), correlation.index.max()))
    days = correlation.index
    changes = pd.DataFrame({f'd{k}': correlation.shift(-(k-1))-correlation.shift(1) for k in (1,2,3)})
    events = events.copy()
    events['trading_date'] = pd.to_datetime(events['trading_date'])
    events = events[events.event_type.isin(['FOMC','CPI','NFP']) & events.trading_date.isin(days)]
    events = events.drop_duplicates(['trading_date','event_type'])
    positions = {d:i for i,d in enumerate(days)}
    event_positions = {positions[d] for d in events.trading_date}
    normal_mask = [not any(j in event_positions for j in range(i-1,i+3)) for i in range(len(days))]
    normal = changes.loc[normal_mask].dropna()
    market = market_proxy(raw).reindex(days)
    broad = (market.index_return.abs() >= big_move) & (market.breadth >= breadth)
    is_event = days.isin(events.trading_date)

    def summarize(name, sample):
        sample = sample.dropna()
        row = {'group': name, 'n': len(sample), 'median_change_3_sessions': sample.d3.median(),
               'fraction_positive_3_sessions': (sample.d3 > 0).mean() if len(sample) else np.nan,
               'mean_abs_change_3_sessions': sample.d3.abs().mean(),
               'inference': 'DESCRIPTIVE_OVERLAPPING_WINDOWS_NOT_INDEPENDENT'}
        for k in (1,2,3):
            x,y = sample[f'd{k}'],normal[f'd{k}']
            row[f'mean_change_{k}_sessions'] = x.mean()
            row[f'naive_welch_p_{k}_sessions'] = stats.ttest_ind(x,y,equal_var=False).pvalue if name!='Normal days' and min(len(x),len(y))>=2 else np.nan
        row['naive_mann_whitney_abs_p_3_sessions'] = stats.mannwhitneyu(sample.d3.abs(),normal.d3.abs()).pvalue if name!='Normal days' and len(sample) and len(normal) else np.nan
        return row

    by_type = [summarize('Normal days',normal)]
    for typ in ['FOMC','CPI','NFP']:
        by_type.append(summarize(typ,changes.reindex(events.loc[events.event_type.eq(typ),'trading_date'])))
    groups = {'Broad move with event':broad & is_event,'Broad move without event':broad & ~is_event,
              'Event without broad move':~broad & is_event & market.index_return.notna()}
    broad_table = [summarize('Normal days',normal)] + [summarize(n,changes.loc[m]) for n,m in groups.items()]
    market['broad_move'] = broad
    detail = events[['trading_date','event_type']].merge(changes.rename_axis('trading_date'),on='trading_date',how='left')
    detail = detail.merge(market.rename_axis('trading_date'),on='trading_date',how='left')
    return pd.DataFrame(by_type),pd.DataFrame(broad_table),detail


# Tables live only in the requested runtime directory, never beside source scripts.
def save_tables(output, tables):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    for name, table in tables.items():
        table.to_csv(output/f'{name}.csv',index=False)
    with pd.ExcelWriter(output/'tables.xlsx',engine='openpyxl') as writer:
        for name,table in tables.items():
            table.to_excel(writer,sheet_name=name[:31],index=False)
            writer.sheets[name[:31]].freeze_panes='A2'
