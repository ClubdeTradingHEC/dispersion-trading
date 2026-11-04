"""Prepare the canonical DJIA panel from local, checksum-verified source inputs."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .correlation_features import entry_features
from .inputs import clean_returns, sha256
from .measurement import available_pair_rc
from .store import dump
from .statistics import training_mask
from .store import DiskBundle
# Bind prepared features to their settings, financial inputs and implementation.

def fingerprint(cfg):
    """Bind prepared features to their settings, financial inputs and implementation."""
    import hashlib
    constituents = Path(cfg['measurements_root']) / 'constituents.parquet'
    parts = sorted(constituents.rglob('*.parquet')) if constituents.is_dir() else [constituents]
    member_hash = hashlib.sha256(''.join(sha256(p) for p in parts).encode()).hexdigest()
    return {
        'constituents': member_hash,
        'preparation_code': {name: sha256(Path(__file__).with_name(name)) for name in ['dataset.py', 'correlation_features.py', 'inputs.py', 'measurement.py', 'statistics.py', 'store.py']},
        'configuration': hashlib.sha256(json.dumps({key: cfg[key] for key in [
            'training_start', 'evaluation_end', 'slow_history_sessions', 'slow_half_life_sessions',
            'downside_sessions', 'minimum_negative_sessions_per_stock', 'common_features'
        ]}, sort_keys=True).encode()).hexdigest(),
        'measurement': sha256(Path(cfg['measurements_root']) / 'financial_panel.parquet'),
        'raw_manifest': sha256(Path(cfg['raw_root']) / 'manifest.json'),
        'crashes': sha256(cfg['crash_dates_file']),
    }
# Validate the supported experiment without selecting models from outcomes.

def read_config(path='configs/study.json'):
    """Validate the supported experiment without selecting models from outcomes."""
    cfg = json.loads(Path(path).read_text(encoding='utf-8'))
    expected = {
        'ic_only': ['ic'],
        'baseline': ['ic', 'rc_past'],
        'expanded': ['ic', 'rc_past', 'vol20', 'return20', 'index_iv'],
        'requested': ['ic', 'rc_past', 'slow_rc', 'downside_rc']
    }
    if cfg['specifications'] != expected:
        raise ValueError('EXPECTED_FOUR_APPROVED_EQUATIONS')
    if not pd.Timestamp(cfg['training_start']) < pd.Timestamp(cfg['training_end']) < pd.Timestamp(cfg['evaluation_start']) <= pd.Timestamp(cfg['evaluation_end']):
        raise ValueError('INVALID_CHRONOLOGICAL_SPLIT')
    if not 2 <= cfg['downside_sessions'] <= cfg['slow_history_sessions']:
        raise ValueError('INVALID_FEATURE_HISTORY')
    if cfg['minimum_training_rows'] <= max(map(len, expected.values())) + 1:
        raise ValueError('INSUFFICIENT_CONFIGURED_TRAINING')
    return cfg
# Load daily returns and the existing entry basket; never replace a member.

def raw_inputs(cfg):
    """Load daily returns and the existing entry basket; never replace a member."""
    bundle = DiskBundle(cfg['raw_root']).validate()
    calendar = pd.DatetimeIndex(bundle.calendar.date)
    stocks = clean_returns(bundle.read_table('returns'), calendar)
    if stocks.duplicated(['date', 'permno']).any():
        raise ValueError('DUPLICATE_RETURN_GRAIN')
    wide = stocks.pivot(index='date', columns='permno', values='return').reindex(calendar)
    constituents = pd.read_parquet(Path(cfg['measurements_root']) / 'constituents.parquet')
    constituents = constituents.loc[(constituents.basket == 'full') & (constituents.horizon == 30)].copy()
    if constituents.duplicated(['date', 'permno']).any():
        raise ValueError('DUPLICATE_ENTRY_MEMBER')
    constituents['a'] = constituents.weight * constituents.iv
    members = {date: group.sort_values('permno') for date, group in constituents.groupby('date')}
    return (bundle, calendar, stocks, wide, members)
# Build measurements plus entry-only predictors, preserving rejected dates.

def prepare(cfg):
    """Build measurements plus entry-only predictors, preserving rejected dates."""
    root = Path(cfg['dataset_root'])
    root.mkdir(parents=True, exist_ok=True)
    bundle, calendar, stocks, wide, members = raw_inputs(cfg)
    # Reconstruct market features using completed sessions through the entry close.
    ir = bundle.read_table('index_returns').sort_values('date')
    if ir.date.duplicated().any():
        raise ValueError('DUPLICATE_INDEX_RETURN_DATE')
    market = pd.Series(pd.to_numeric(ir['return']).to_numpy(), index=pd.to_datetime(ir.date)).reindex(calendar)
    features = pd.DataFrame(index=calendar)
    features['vol20'] = market.rolling(20, min_periods=20).std() * np.sqrt(252)
    features['return20'] = (1 + market).rolling(20, min_periods=20).apply(np.prod, raw=True) - 1
    features['abs_return20'] = features.return20.abs()
    price = (1 + market).cumprod()
    features['drawdown252'] = price / price.rolling(252, min_periods=252).max() - 1
    features['crash_day'] = market <= -0.03
    features['after_crash20'] = features.crash_day.shift(1).rolling(20, min_periods=20).max().eq(1)
    # Label validity is separate from feature availability and the Model B mask.
    source = Path(cfg['measurements_root']) / 'financial_panel.parquet'
    frame = pd.read_parquet(source)
    frame = frame.loc[(frame.basket == 'full') & (frame.horizon == 30) & frame.ic_status.eq('PASS') & frame.label_status.eq('PASS')].copy()
    frame = frame.loc[frame.date.between(cfg['training_start'], cfg['evaluation_end'])].sort_values('date')
    if frame.date.duplicated().any():
        raise ValueError('DUPLICATE_ENTRY_DATE')
    frame = frame.set_index('date').join(features).reset_index()
    if not (frame.label_available_at > frame.date).all():
        raise ValueError('INVALID_LABEL_CLOCK')
    flags = json.loads(Path(cfg['crash_dates_file']).read_text())['dates']
    frame = frame.join(training_mask(frame.date, flags), on='date')
    # Histories use every entry member and never zero-fill missing returns.
    rows, recent_errors = ([], [])
    for row in frame.itertuples():
        status = {'date': row.date, 'feature_status': 'PASS', 'feature_reason': ''}
        try:
            group = members.get(row.date)
            if group is None:
                raise ValueError('NO_ENTRY_BASKET')
            if len(group) != row.n_selected:
                raise ValueError('ENTRY_BASKET_COUNT_MISMATCH')
            a, ids = (group.a.to_numpy(float), group.permno.tolist())
            status.update(entry_features(wide, calendar, row.date, ids, a, cfg))
            if np.isfinite(row.rc_past):
                dates = calendar[(calendar > row.date - pd.Timedelta(days=30)) & (calendar <= row.date)]
                recent = available_pair_rc(wide.reindex(index=dates, columns=ids).to_numpy(float), a)['rc']
                error = abs(recent - row.rc_past)
                recent_errors.append(error)
                if error > 1e-10:
                    raise RuntimeError('RECENT_RC_DEFINITION_MISMATCH')
        except ValueError as exc:
            status.update(feature_status='UNAVAILABLE', feature_reason=str(exc))
        rows.append(status)
    frame = frame.merge(pd.DataFrame(rows), on='date', validate='one_to_one')
    base = ['ic', 'rc_past', 'vol20', 'return20', 'index_iv', 'rc_future']
    frame['base_features_available'] = np.isfinite(frame[base]).all(axis=1)
    frame['complete_features'] = frame.base_features_available & frame.feature_status.eq('PASS') & np.isfinite(frame[cfg['common_features']]).all(axis=1)
    frame['log_vol20'] = np.log(frame.vol20.where(frame.vol20 > 0))
    frame['gap'] = frame.ic - frame.rc_future
    # Publish a complete dataset as a unit; the source bundle remains untouched.
    from .store import _publish
    import tempfile
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=root) as temporary:
        staging = Path(temporary)
        frame.to_parquet(staging / 'dataset.parquet', index=False)
        audit = {
            'rows': len(frame),
            'eligible': int(frame.complete_features.sum()),
            'reasons': frame.loc[~frame.feature_status.eq('PASS'), 'feature_reason'].value_counts().to_dict(),
            'recent_RC_max_error': max(recent_errors, default=None),
            'new_WRDS_queries': 0,
            'source_panel_sha256': sha256(source),
            'raw_manifest_sha256': sha256(Path(cfg['raw_root']) / 'manifest.json'),
            'assumptions': 'Same-close observability and vintage timing are not certified; early baskets can be partial'
        }
        audit['fingerprint'] = fingerprint(cfg)
        audit['prepared_panel_sha256'] = sha256(staging / 'dataset.parquet')
        dump(audit, staging / 'dataset_manifest.json')
        _publish(staging, root)
    return audit
# Reject stale prepared inputs when configuration or source fingerprints change.

def inputs(cfg):
    """Reject stale prepared inputs when configuration or source fingerprints change."""
    root = Path(cfg['dataset_root'])
    audit = json.loads((root / 'dataset_manifest.json').read_text())
    if audit.get('fingerprint') != fingerprint(cfg):
        raise ValueError('STALE_PREPARED_DATA: run study prepare with the current inputs/config')
    if audit.get('prepared_panel_sha256') != sha256(root / 'dataset.parquet'):
        raise ValueError('CHANGED_PREPARED_DATA: regenerate the dataset')
    frame = pd.read_parquet(root / 'dataset.parquet')
    calendar = pd.DatetimeIndex(DiskBundle(cfg['raw_root']).calendar.date)
    return (frame, calendar)
