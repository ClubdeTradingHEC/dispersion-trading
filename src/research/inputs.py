from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import numpy as np
import pandas as pd
import exchange_calendars as xcals
from .errors import DataError
TABLES = {
    'membership': ['index', 'permno', 'start', 'end'],
    'caps': ['permno', 'date', 'dlycap', 'dlyprc'],
    'links': ['permno', 'secid', 'sdate', 'edate', 'score'],
    'surface': ['secid', 'date', 'days', 'cp_flag', 'delta', 'impl_volatility', 'impl_strike', 'impl_premium'],
    'forwards': ['secid', 'date', 'days', 'forward_price'],
    'curve': ['date', 'days', 'rate'],
    'returns': ['permno', 'date', 'return'],
    'index_returns': ['index', 'date', 'return'],
    'calendar': ['date']
}
DATE_FIELDS = {'date', 'start', 'end', 'sdate', 'edate', 'available_at', 'label_available_at'}
# Reuse the exchange calendar without repeatedly rebuilding session metadata.

@lru_cache(maxsize=8)
def _calendar(first_year, last_year):
    """Reuse the exchange calendar without repeatedly rebuilding session metadata."""
    return xcals.get_calendar('XNYS', start=f'{first_year}-01-01', end=f'{last_year}-12-31')
# Return exchange sessions for the declared endpoints.

def sessions(start, end):
    """Return exchange sessions for the declared endpoints."""
    cal = _calendar(
        min(1990, pd.Timestamp(start).year // 10 * 10),
        max(2035, (pd.Timestamp(end).year // 10 + 1) * 10)
    )
    return cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end)).tz_localize(None)
# Fingerprint local files without logging their contents.

def sha256(path):
    """Fingerprint local files without logging their contents."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()
# Validate one raw shard before writing or using permanent identifiers.

def normalize_table(name, frame):
    """Validate one raw shard before writing or using permanent identifiers."""
    missing = set(TABLES[name]) - set(frame)
    if missing:
        raise DataError('MISSING_RAW_FIELDS', f'{name}: {missing}')
    for column in {'permno', 'secid'} & set(frame):
        values = pd.to_numeric(frame[column], errors='coerce')
        if values.isna().any() or not np.isfinite(values).all() or (values <= 0).any() or (values % 1 != 0).any():
            raise DataError('INVALID_PERMANENT_IDENTIFIER', f'{name}.{column}')
        frame[column] = values.astype('int64')
    for column in DATE_FIELDS & set(frame):
        values = pd.to_datetime(frame[column], errors='raise')
        frame[column] = values if column.endswith('available_at') else values.dt.normalize()
    if 'date' in frame and frame.date.isna().any():
        raise DataError('INVALID_RAW_DATE', name)
    if name == 'membership' and frame.start.isna().any():
        raise DataError('INVALID_MEMBERSHIP_START')
    return frame
# Hold normalized financial tables and provenance with explicit validation.

@dataclass
class Bundle:
    """Hold normalized financial tables and provenance with explicit validation."""
    tables: dict[str, pd.DataFrame]
    metadata: dict = field(default_factory=dict)

    def __getattr__(self, name):
        """Expose normalized named tables through the bundle interface."""
        if name in TABLES:
            return self.tables[name]
        raise AttributeError(name)

    def validate(self):
        """Validate input fields and invariants before financial calculations."""
        for name in TABLES:
            if name not in self.tables:
                raise DataError('MISSING_RAW_TABLE', name)
            normalize_table(name, self.tables[name])
        for name, keys in (
            ('returns', ['date', 'permno']),
            ('index_returns', ['date', 'index']),
            ('calendar', ['date'])
        ):
            if self.tables[name].duplicated(keys).any():
                raise DataError('DUPLICATE_RETURN_OR_CALENDAR', name)
        if self.calendar.date.isna().any():
            raise DataError('INVALID_CALENDAR')
        self.tables['calendar'] = self.calendar.sort_values('date').reset_index(drop=True)
        return self


# An explicit timestamp must be present and no later than the decision.

def require_available(frame, asof, code):
    """An explicit timestamp must be present and no later than the decision."""
    if 'available_at' in frame:
        if frame.available_at.isna().any():
            raise DataError('MISSING_AVAILABILITY_DATE')
        if (frame.available_at > asof).any():
            raise DataError(code)
# Resolve the historical entry membership using effective intervals.

def members_at(bundle, index, date):
    """Resolve the historical entry membership using effective intervals."""
    m = bundle.membership
    m = m.loc[(m['index'] == index) & (m.start <= date) & (m.end.isna() | (m.end >= date))]
    if m.empty:
        raise DataError('MISSING_MEMBERSHIP', index)
    if m.permno.duplicated().any():
        raise DataError('OVERLAPPING_MEMBERSHIP')
    require_available(m, date, 'MEMBERSHIP_NOT_AVAILABLE_AT_ENTRY')
    return m.permno.to_numpy(int)
# Construct entry weights under the approved index weighting convention.

def weights_at(bundle, permnos, date, weighting, *, allow_partial=False):
    """Construct entry weights under the approved index weighting convention."""
    c = bundle.caps.loc[(bundle.caps.date == date) & bundle.caps.permno.isin(permnos)].copy()
    if c.permno.duplicated().any():
        raise DataError('DUPLICATE_CRSP_RECORD')
    c = c.set_index('permno').reindex(permnos)
    cap = c.dlycap.to_numpy(float)
    value = cap if weighting == 'market_cap' else abs(c.dlyprc.to_numpy(float)) if weighting == 'price' else np.ones(len(c))
    usable = np.isfinite(value) & (value > 0) & c.date.notna().to_numpy()
    if not allow_partial and (not np.isfinite(cap).all() or (cap <= 0).any()):
        raise DataError('MISSING_INVALID_MARKET_CAP')
    if not usable.any() or (not allow_partial and not usable.all()):
        raise DataError('INVALID_WEIGHT_INPUT')
    require_available(c.loc[usable], date, 'WEIGHTS_NOT_AVAILABLE_AT_ENTRY')
    # Kevin normalizes the stocks with available weighting inputs. Keep missing
    # identifiers aligned as NaN so the caller can report each omitted stock.
    weights = np.where(usable, value, np.nan)
    weights /= np.nansum(weights)
    # A missing cap makes whole-membership cap coverage unknowable; do not call
    # a renormalized observed-cap total 100% of the official index.
    capmass = cap / cap.sum() if np.isfinite(cap).all() and (cap > 0).all() else np.full(len(cap), np.nan)
    return weights, capmass
# Resolve the effective security link and reject ambiguous identifiers.

def map_secid(links, permno, date):
    """Resolve the effective security link and reject ambiguous identifiers."""
    l = links.loc[(links.permno == permno) & (links.sdate.isna() | (links.sdate <= date)) & (links.edate.isna() | (links.edate >= date))]
    if l.empty:
        raise DataError('MISSING_SECID_LINK')
    require_available(l, date, 'LINK_NOT_AVAILABLE_AT_ENTRY')
    if not np.isfinite(l.score.to_numpy(float)).all() or (l.score < 0).any():
        raise DataError('INVALID_LINK_SCORE')
    best = l.loc[l.score == l.score.min(), 'secid'].dropna().unique()
    if len(best) != 1:
        raise DataError('AMBIGUOUS_SECID_LINK', str(best))
    return int(best[0])
# Apply the shared finite/missing/duration/corporate-action return rules.

def clean_returns(frame, calendar):
    """Apply the shared finite/missing/duration/corporate-action return rules."""
    r = frame.copy()
    r['date'] = pd.to_datetime(r['date']).dt.normalize()
    r['return'] = pd.to_numeric(r['return'], errors='coerce')
    r['_quality_code'] = ''
    valid = np.isfinite(r['return']) & (r['return'] >= -1)
    r.loc[~valid, '_quality_code'] = 'INVALID_OR_MISSING_RETURN'
    if 'dlyretmissflg' in r:
        flag_ok = r.dlyretmissflg.astype(str).isin(['NA', '', '0', 'nan', 'None'])
        r.loc[~flag_ok, '_quality_code'] = 'RETURN_MISSING_FLAG'
        valid &= flag_ok
    # Preserve vendor duration flags as metadata, not a blanket return filter.
    # In particular DD denotes a delisting return, not an unusable observation.
    # Kevin uses the reported daily return; missing/nonfinite values stay missing.
    if 'corporate_action_unresolved' in r:
        corp = r.corporate_action_unresolved.fillna(False).astype(bool)
        r.loc[corp, '_quality_code'] = 'CORPORATE_ACTION_DISCONTINUITY'
        valid &= ~corp
    r.loc[~valid, 'return'] = np.nan
    return r
# One aligned wide grid; fixed constituent columns, never future replacements.

class ReturnStore:
    """One aligned wide grid; fixed constituent columns, never future replacements."""

    def __init__(self, bundle):
        """Initialize the declared object and retain its explicit dependencies."""
        self.calendar = pd.DatetimeIndex(bundle.calendar.date)
        r = clean_returns(bundle.returns, self.calendar)
        self.bad = r.loc[r['_quality_code'].ne('')].copy()
        self.delisted = r.loc[r.get('dlydelflg', pd.Series('N', index=r.index)).astype(str).eq('Y')]
        self.wide = r.pivot(index='date', columns='permno', values='return').reindex(self.calendar)
        self.index = bundle.index_returns.pivot(index='date', columns='index', values='return').reindex(self.calendar)
        self.index = self.index.apply(pd.to_numeric, errors='coerce').where(lambda d: np.isfinite(d) & (d >= -1))
        self.availability = {}
        if 'available_at' in r:
            self.availability['stocks'] = r.pivot(index='date', columns='permno', values='available_at').reindex(self.calendar)
        if 'available_at' in bundle.index_returns:
            self.availability['index'] = bundle.index_returns.pivot(index='date', columns='index', values='available_at').reindex(self.calendar)
        group = self.calendar.to_period('M')
        expected_counts = pd.Series(group).value_counts().sort_index()

        def monthly(frame):
            """Construct the declared monthly return history from the available source series."""
            product = (1 + frame).groupby(group).prod(min_count=1) - 1
            complete = frame.notna().groupby(group).sum().eq(expected_counts, axis=0)
            return product.where(complete)
        self.monthly = monthly(self.wide)
        self.index_monthly = monthly(self.index)

    def grid(self, start, end, ids, index=None, asof=None, min_sessions=10, require_complete=True):
        """Build a balanced return grid without silently filling missing returns."""
        ix = self.calendar[(self.calendar > start) & (self.calendar <= end)]
        expected = sessions(start + pd.Timedelta(days=1), end)
        if not ix.equals(expected):
            raise DataError('INCOMPLETE_EXCHANGE_CALENDAR')
        if len(ix) < min_sessions:
            raise DataError('INSUFFICIENT_PAIR_OVERLAP', len(ix))
        x = self.wide.reindex(index=ix, columns=ids)
        y = self.index.reindex(index=ix, columns=[index]) if index is not None else None
        if require_complete and x.isna().any().any():
            bad = self.bad.loc[self.bad.date.isin(ix) & self.bad.permno.isin(ids)]
            for code in ('CORPORATE_ACTION_DISCONTINUITY', 'RETURN_DURATION_DISCONTINUITY'):
                if (bad._quality_code == code).any():
                    raise DataError(
                        code,
                        str(bad.loc[bad._quality_code == code, ['permno', 'date']].to_dict('records'))
                    )
            if self.delisted.date.isin(ix).where(self.delisted.permno.isin(ids), False).any():
                raise DataError('DELISTING_DISCONTINUITY')
            missing = [int(p) for p in x.columns[x.isna().any()]]
            raise DataError(
                'MISSING_FUTURE_RETURNS' if asof is None else 'MISSING_PAST_RETURNS',
                str(missing)
            )
        if y is not None and y.isna().any().any():
            raise DataError('MISSING_INDEX_RETURNS')
        if asof is not None:
            sources = [('stocks', ids)] + ([('index', [index])] if index is not None else [])
            for key, cols in sources:
                if key in self.availability:
                    dates = self.availability[key].reindex(index=ix, columns=cols)
                    if dates.isna().any().any():
                        raise DataError('MISSING_AVAILABILITY_DATE')
                    if (dates > asof).any().any():
                        raise DataError('RETURN_NOT_AVAILABLE')
        return (x.to_numpy(float), y.iloc[:, 0].to_numpy(float) if y is not None else None, ix)

    def historical_rho(self, date, ids, index):
        """Measure past stock-index dependence under the declared history convention."""
        end = date.to_period('M')
        months = pd.period_range(end - 36, end - 1, freq='M')
        expected = sessions(months[0].start_time, months[-1].end_time.normalize())
        actual = self.calendar[(self.calendar >= months[0].start_time) & (self.calendar <= months[-1].end_time.normalize())]
        if not actual.equals(expected):
            raise DataError('INCOMPLETE_HISTORICAL_CALENDAR')
        x = self.monthly.reindex(index=months, columns=ids).to_numpy(float)
        y = self.index_monthly.reindex(index=months, columns=[index]).iloc[:, 0].to_numpy(float)
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise DataError('INCOMPLETE_HISTORICAL_MONTHS')
        for key, cols in (('stocks', ids), ('index', [index])):
            if key in self.availability:
                dates = self.availability[key].reindex(index=actual, columns=cols)
                if dates.isna().any().any():
                    raise DataError('MISSING_AVAILABILITY_DATE')
                if (dates > date).any().any():
                    raise DataError('RETURN_NOT_AVAILABLE')
        x = x - x.mean(0)
        y = y - y.mean()
        sx = np.linalg.norm(x, axis=0)
        sy = np.linalg.norm(y)
        if (sx == 0).any() or sy == 0:
            raise DataError('ZERO_VARIANCE_RETURNS')
        return x.T @ y / (sx * sy)

    def label_available(self, ix, ids, index=None, lag=1):
        """Determine when all observations required by an outcome are available."""
        last = ix[-1]
        target = last
        sources = [('stocks', ids)] + ([('index', [index])] if index is not None else [])
        for key, cols in sources:
            if key in self.availability:
                dates = self.availability[key].reindex(index=ix, columns=cols)
                if dates.isna().any().any():
                    raise DataError('MISSING_AVAILABILITY_DATE')
                target = max(target, dates.max().max())
        # Local feed availability is not the same as historical live publication.
        # When vendor timestamps are absent, use a declared session-lag assumption.
        full = sessions(target.normalize(), target.normalize() + pd.Timedelta(days=14 + lag * 3))
        later = full[full > target]
        if len(later) < lag:
            raise DataError('LABEL_AVAILABILITY_UNRESOLVED')
        return later[lag - 1]
