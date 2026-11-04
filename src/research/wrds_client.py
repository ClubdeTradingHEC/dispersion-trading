"""Scoped, resumable extraction using Kevin's subscribed table names.

Raw cache is local-only. Each query is content-addressed and hash-checked.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import pandas as pd
from .inputs import sessions, normalize_table
from .errors import DataError
TABLES = [
    'crsp.dsp500list_v2',
    'crsp.dsf_v2',
    'wrdsapps_link_crsp_optionm.opcrsphist',
    'optionm.zerocd',
    'optionm.secprd'
]
# Open WRDS only when explicitly requested, using existing local authentication.

def connect():
    """Open WRDS only when explicitly requested, using existing local authentication."""
    from src.data.wrds_connection import get_wrds_connection
    return get_wrds_connection(cache=False)
# Cache scoped database results without changing their financial interpretation.

class QueryCache:
    """Cache scoped database results without changing their financial interpretation."""

    def __init__(self, db, root):
        """Initialize the declared object and retain its explicit dependencies."""
        from src.data.query_cache import CachedWRDS
        self.db = CachedWRDS(db, root, memory_bytes=0)

    def get(self, sql, date_cols=()):
        """Read a valid cached query result or execute the explicitly requested query."""
        # Keep query text inspectable beside local-only cache receipts. This does
        # not alter the query, its cache key or Kevin's database implementation.
        catalog = self.db.root / 'sql'
        catalog.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(sql.encode('utf-8')).hexdigest()
        (catalog / (key + '.sql')).write_text(sql, encoding='utf-8')
        return self.db.raw_sql(sql, date_cols=list(date_cols))
# Run the explicit bounded access checks for configured sources.

def verify_access(db, config):
    """Run the explicit bounded access checks for configured sources."""
    report = []
    year = pd.Timestamp(config.entry_end).year
    for table in TABLES + [f'optionm.vsurfd{year}', f'optionm.stdopd{year}']:
        try:
            result = db.raw_sql(f'SELECT * FROM {table} LIMIT 0')
            report.append({'table': table, 'status': 'PASS', 'fields': list(result.columns)})
        except Exception as e:
            report.append({'table': table, 'status': 'FAIL', 'error_type': type(e).__name__})
    for spec in config.specs():
        if spec.secid is not None:
            row = db.raw_sql(f'SELECT MIN(date) AS first_date, MAX(date) AS last_date FROM optionm.secprd WHERE secid={int(spec.secid)}')
            report.append({
                'index': spec.name,
                'index_return_range': row.astype(str).to_dict('records'),
                'joint_coverage': 'NOT_ESTABLISHED_BY_TABLE_MAX'
            })
    return report
# Partition identifiers into bounded query batches.

def chunks(ids, n=200):
    """Partition identifiers into bounded query batches."""
    ids = sorted(set((int(i) for i in ids)))
    for j in range(0, len(ids), n):
        yield ','.join((str(i) for i in ids[j:j + n]))
# Partition requested dates into bounded calendar-year ranges.

def yearly(a, b):
    """Partition requested dates into bounded calendar-year ranges."""
    a = pd.Timestamp(a)
    b = pd.Timestamp(b)
    for y in range(a.year, b.year + 1):
        yield (
            max(a, pd.Timestamp(y, 1, 1)).date().isoformat(),
            min(b, pd.Timestamp(y, 12, 31)).date().isoformat(),
            y
        )
# Bound each query in calendar time and never cross a yearly option table.

def periods(a, b, days):
    """Bound each query in calendar time and never cross a yearly option table."""
    for first, last, year in yearly(a, b):
        cursor, final = (pd.Timestamp(first), pd.Timestamp(last))
        while cursor <= final:
            stop = min(cursor + pd.Timedelta(days=days - 1), final)
            yield (str(cursor.date()), str(stop.date()), year)
            cursor = stop + pd.Timedelta(days=1)
# Stream each bounded SQL result to a validated, partitioned raw bundle.

def extract(db, config, root, progress=print, *, provisional=False, bundle_name='bundle'):
    """Stream each bounded SQL result to a validated, partitioned raw bundle.

    Cache and normalized output need disk capacity; neither is an in-memory history.
    """
    import tempfile
    from .store import BundleWriter, _publish
    config.validate()
    if bundle_name not in ('bundle', 'raw'):
        raise ValueError('bundle_name must be bundle or raw')
    if not provisional:
        config.require_rate_certification()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    from src.data.query_cache import CachedWRDS
    cache = QueryCache(db.db if isinstance(db, CachedWRDS) else db, root / 'query_cache')
    start, end = (pd.Timestamp(config.entry_start), pd.Timestamp(config.entry_end))
    if config.observation_end:
        end = min(end, pd.Timestamp(config.observation_end))
    warmup = (start.to_period('M') - 36).start_time - pd.Timedelta(days=max(config.horizons) + 14)
    tail = end + pd.Timedelta(days=max(config.horizons) + 14)
    if config.observation_end:
        tail = min(tail, pd.Timestamp(config.observation_end))
    metadata = {
        'synthetic': False,
        'source': 'WRDS OptionMetrics/CRSP',
        'extracted_at': datetime.now(timezone.utc).isoformat(),
        'entry_start': config.entry_start,
        'entry_end': config.entry_end,
        'effective_entry_end': str(end.date()),
        'observation_end': config.observation_end,
        'history_start': str(warmup.date()),
        'label_tail': str(tail.date()),
        'index_secids': [s.secid for s in config.specs()],
        'rate_unit': config.rate_unit,
        'rate_confirmation_source': config.rate_confirmation_source,
        'rate_convention_status': 'USER_SELECTED_KEVIN_RULE' if config.rate_unit == 'kevin' else 'PROVISIONAL' if provisional else 'CONFIRMED',
        'return_convention': [s.return_convention for s in config.specs()],
        'historical_publication_timestamps': 'NOT_PROVIDED_BY_SELECTED_TABLES',
        'query_batch_ids': config.query_batch_ids,
        'query_batch_days': config.query_batch_days
    }
    memberships, allids = ([], [])
    for spec in config.specs():
        if spec.secid is None:
            raise DataError('UNCONFIGURED_INDEX_SECID', spec.name)
        if spec.name == 'SPX':
            frame = cache.get(
                f"SELECT permno, mbrstartdt AS start, mbrenddt AS end FROM crsp.dsp500list_v2 WHERE mbrstartdt <= '{end.date()}' AND (mbrenddt >= '{start.date()}' OR mbrenddt IS NULL)",
                ['start', 'end']
            )
            frame['index'] = spec.name
        else:
            if not spec.membership_csv:
                raise DataError('HISTORICAL_MEMBERSHIP_FILE_REQUIRED', spec.name)
            frame = pd.read_csv(spec.membership_csv, keep_default_na=False)
            if not {'permno', 'start', 'end', 'index'} <= set(frame):
                raise DataError('INVALID_MEMBERSHIP_CSV')
            frame = frame.loc[frame['index'] == spec.name].copy()
            frame['start'] = pd.to_datetime(frame.start)
            frame['end'] = pd.to_datetime(frame.end.replace('', None))
        if frame.empty:
            raise DataError('MISSING_MEMBERSHIP', spec.name)
        normalize_table('membership', frame)
        memberships.append(frame)
        allids.extend(frame.permno.astype(int))
    membership = pd.concat(memberships, ignore_index=True).drop_duplicates()
    linkparts = [cache.get(
        f"SELECT permno, secid, score, sdate, edate FROM wrdsapps_link_crsp_optionm.opcrsphist WHERE permno IN ({ids}) AND (sdate <= '{end.date()}' OR sdate IS NULL) AND (edate >= '{start.date()}' OR edate IS NULL)",
        ['sdate', 'edate']
    ) for ids in chunks(allids, config.query_batch_ids)]
    links = normalize_table('links', pd.concat(linkparts, ignore_index=True))
    if links.empty:
        raise DataError('MISSING_SECID_LINK')
    secids = list(links.secid.dropna().astype(int)) + [s.secid for s in config.specs()]
    retcols = {s.return_column for s in config.specs()}
    if len(retcols) != 1:
        raise DataError('MIXED_RETURN_CONVENTIONS')
    retcol = next(iter(retcols))
    with tempfile.TemporaryDirectory(prefix='.extract-', dir=root) as temporary:
        stage = Path(temporary) / bundle_name
        writer = BundleWriter(stage, metadata)
        writer.add('membership', membership)
        writer.add('links', links)
        for a, b, year in periods(warmup, tail, config.query_batch_days):
            progress(f'CRSP {a} to {b}: batches <= {config.query_batch_ids} identifiers')
            for ids in chunks(allids, config.query_batch_ids):
                frame = cache.get(
                    f"SELECT permno, dlycaldt AS date, dlycap, dlyprc, {retcol} AS return, dlyretmissflg, dlyretdurflg, dlydelflg FROM crsp.dsf_v2 WHERE permno IN ({ids}) AND dlycaldt BETWEEN '{a}' AND '{b}'",
                    ['date']
                )
                writer.add(
                    'caps',
                    frame.loc[frame.date.between(start, end), ['permno', 'date', 'dlycap', 'dlyprc']]
                )
                writer.add('returns', frame.drop(columns=['dlycap', 'dlyprc']))
        tenors = ','.join((str(h) for h in config.horizons))
        for a, b, year in periods(start, end, config.query_batch_days):
            progress(f'OptionMetrics {a} to {b}: tenors {tenors}')
            for ids in chunks(secids, config.query_batch_ids):
                writer.add(
                    'surface',
                    cache.get(
                        f"SELECT secid, date, days, cp_flag, delta, impl_volatility, impl_strike, impl_premium, dispersion FROM optionm.vsurfd{year} WHERE secid IN ({ids}) AND date BETWEEN '{a}' AND '{b}' AND days IN ({tenors}) AND ((cp_flag='C' AND delta=50) OR (cp_flag='P' AND delta=-50))",
                        ['date']
                    )
                )
                writer.add(
                    'forwards',
                    cache.get(
                        f"SELECT DISTINCT secid, date, days, forward_price FROM optionm.stdopd{year} WHERE secid IN ({ids}) AND date BETWEEN '{a}' AND '{b}' AND days IN ({tenors})",
                        ['date']
                    )
                )
            writer.add(
                'curve',
                cache.get(
                    f"SELECT date, days, rate FROM optionm.zerocd WHERE date BETWEEN '{a}' AND '{b}'",
                    ['date']
                )
            )
        for spec in config.specs():
            for a, b, year in periods(warmup, tail, config.query_batch_days):
                frame = cache.get(
                    f"SELECT date, return, close FROM optionm.secprd WHERE secid={int(spec.secid)} AND date BETWEEN '{a}' AND '{b}'",
                    ['date']
                )
                frame['index'] = spec.name
                writer.add('index_returns', frame)
        writer.add('calendar', pd.DataFrame({'date': sessions(warmup, tail)}))
        writer.finish().validate()
        # Publish only after shard/schema/checksum validation succeeds.
        _publish(Path(temporary), root)
    from .store import DiskBundle
    result = DiskBundle(root / bundle_name).validate()
    return result
