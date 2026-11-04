from pathlib import Path
import json, time
import importlib.metadata, hashlib
import numpy as np
import pandas as pd
from .inputs import ReturnStore, members_at, weights_at, map_secid, sha256, require_available, sessions
from .measurement import implied_correlation, available_pair_rc, pair_rc_bounds, mic_comparators, miv, original_weight_subset_diagnostic
from .pricing import package
from .errors import DataError
# Construct declared basket candidates without using future measurements.

def basket_rules(config, n):
    """Construct declared basket candidates without using future measurements."""
    return [('full', n)] + [(f'fraction_{f:g}', f) for f in config.basket_fractions if f < 1] + [(f'top_{k}', k) for k in sorted(set(config.basket_counts)) if 2 <= k < n] + [(f'weight_{f:g}', f) for f in config.basket_weight_thresholds]
# Measure package IV, IC, MIV and realized outcomes with explicit quality reasons.

def compute(bundle, config, dates=None, asof=None, *, provisional=False):
    """Measure package IV, IC, MIV and realized outcomes with explicit quality reasons."""
    bundle.validate()
    config.validate()
    if not bundle.metadata.get('synthetic', False):
        if not provisional:
            config.require_rate_certification()
        if bundle.metadata.get('rate_unit', config.rate_unit) != config.rate_unit:
            raise DataError('RAW_RATE_UNIT_CONFLICT')
    store = ReturnStore(bundle)
    start = pd.Timestamp(config.entry_start)
    end = pd.Timestamp(config.entry_end)
    grid = config.entry_grid(store.calendar)
    if dates is not None:
        grid = grid.intersection(pd.DatetimeIndex(pd.to_datetime(dates)))
    records = []
    exclusions = []
    constituents = []
    packages = []
    timer = time.perf_counter()
    surface = {d: v for d, v in bundle.surface.groupby('date')}
    forward = {d: v for d, v in bundle.forwards.groupby('date')}
    curve = {d: v for d, v in bundle.curve.groupby('date')}
    cache = {}
    rhos = {}

    def reject(date, spec, h, rule, stage, e, permno=None):
        """Record an explicit exclusion reason rather than silently dropping an observation."""
        exclusions.append({
            'date': date,
            'index': spec.name,
            'horizon': h,
            'basket': rule,
            'stage': stage,
            'permno': permno,
            'code': e.code,
            'detail': None if e.detail is None else str(e.detail)
        })
    for spec in config.specs():
        if spec.secid is None:
            raise DataError('UNCONFIGURED_INDEX_SECID', spec.name)
        for date in grid:
            try:
                ids = members_at(bundle, spec.name, date)
                n_original = len(ids)
                fullw, capmass = weights_at(bundle, ids, date, spec.weighting, allow_partial=True)
                usable = np.isfinite(fullw)
                for p in ids[~usable]:
                    reject(date, spec, None, 'all', 'stock_weight', DataError('MISSING_INVALID_WEIGHT_INPUT'), int(p))
                ids, fullw, capmass = ids[usable], fullw[usable], capmass[usable]
            except DataError as e:
                reject(date, spec, None, 'all', 'universe', e)
                continue
            order = np.lexsort((ids, -fullw))
            ids = ids[order]
            fullw = fullw[order]
            capmass = capmass[order]
            for h in config.horizons:
                end_label = date + pd.Timedelta(days=h)
                required_sessions = sessions(date + pd.Timedelta(days=1), end_label)
                beyond_cutoff = config.observation_end is not None and len(required_sessions) and (required_sessions[-1] > pd.Timestamp(config.observation_end))

                def get_iv(secid):
                    """Reuse the authoritative package calculation for a declared security/date/tenor."""
                    key = (secid, date, h)
                    if key not in cache:
                        try:
                            s = surface.get(date, bundle.surface.iloc[:0])
                            f = forward.get(date, bundle.forwards.iloc[:0])
                            c = curve.get(date, bundle.curve.iloc[:0])
                            require_available(
                                s.loc[(s.secid == secid) & (s.days == h)],
                                date,
                                'OPTION_NOT_AVAILABLE_AT_ENTRY'
                            )
                            require_available(
                                f.loc[(f.secid == secid) & (f.days == h)],
                                date,
                                'FORWARD_NOT_AVAILABLE_AT_ENTRY'
                            )
                            require_available(c, date, 'RATE_NOT_AVAILABLE_AT_ENTRY')
                            result = package(s, f, c, secid, date, h, config)
                            cache[key] = result
                            packages.append({'date': date, 'secid': secid, 'horizon': h, **result})
                        except DataError as e:
                            cache[key] = e
                    if isinstance(cache[key], DataError):
                        raise cache[key]
                    return cache[key]['iv']
                try:
                    index_iv = get_iv(spec.secid)
                except DataError as e:
                    reject(date, spec, h, 'all', 'index_iv', e)
                    continue
                stock_iv = np.full(len(ids), np.nan)
                stock_code = {}
                for j, p in enumerate(ids):
                    try:
                        stock_iv[j] = get_iv(map_secid(bundle.links, int(p), date))
                    except DataError as e:
                        stock_code[int(p)] = e
                rules = basket_rules(config, len(ids))
                if np.isfinite(stock_iv).sum() >= 2:
                    rules.append(('reference_option_feasible', None))
                for rule, threshold in rules:
                    basket_timer = time.perf_counter()
                    if threshold is None:
                        chosen = np.flatnonzero(np.isfinite(stock_iv))
                    else:
                        k = threshold if isinstance(threshold, int) else min(
                            len(ids),
                            max(
                                2,
                                int(np.ceil(len(ids) * threshold)) if rule.startswith('fraction_') else int(np.searchsorted(np.cumsum(fullw), threshold) + 1)
                            )
                        )
                        chosen = np.arange(k)
                    k = len(chosen)
                    ii = ids[chosen]
                    ww = fullw[chosen] / fullw[chosen].sum()
                    iv = stock_iv[chosen]
                    rec = {
                        'date': date,
                        'index': spec.name,
                        'horizon': h,
                        'basket': rule,
                        'measurement_policy': 'available_inputs_v1',
                        'n_original': n_original,
                        'n_weight_available': len(ids),
                        'n_missing_weight': n_original - len(ids),
                        'original_cap_coverage_known': bool(np.isfinite(capmass).all()),
                        'n_selected': k,
                        'n_option_valid': int(np.isfinite(iv).sum()),
                        'original_cap_coverage': float(capmass[chosen].sum()),
                        'original_option_cap_coverage': float(capmass[np.isfinite(stock_iv)].sum()),
                        'index_iv': index_iv,
                        'label_end': end_label,
                        'return_convention': spec.return_convention,
                        'interpretation': 'entry_option_feasible_full_index_tracking_proxy' if threshold is None else 'strict_full_membership_proxy' if k == n_original else 'prospective_full_index_tracking_proxy',
                        'ic_status': 'NOT_RUN',
                        'miv_status': 'NOT_RUN',
                        'label_status': 'NOT_RUN',
                        'mic_label_status': 'NOT_RUN',
                        'rate_convention_status': 'USER_SELECTED_KEVIN_RULE' if config.rate_unit == 'kevin' else 'PROVISIONAL' if provisional else 'CERTIFIED'
                    }
                    for p in ii:
                        if int(p) in stock_code:
                            reject(date, spec, h, rule, 'stock_iv', stock_code[int(p)], int(p))
                    if not np.isfinite(iv).all():
                        rec['ic_status'] = 'INCOMPLETE_OPTIONS'
                        rec['incremental_compute_seconds'] = time.perf_counter() - basket_timer
                        records.append(rec)
                        continue
                    a = ww * iv
                    try:
                        rec.update(implied_correlation(index_iv, ww, iv))
                        rec['mic'] = float(index_iv / a.sum())
                        rec['ic_status'] = 'OUT_OF_BOUNDS' if rec['ic_out_of_bounds'] else 'PASS'
                        rec['ic_original_weight_diagnostic'] = original_weight_subset_diagnostic(index_iv, fullw[chosen], iv)
                        if rec['ic_out_of_bounds']:
                            reject(date, spec, h, rule, 'ic', DataError('OUT_OF_BOUNDS_IC', rec['ic']))
                    except DataError as e:
                        reject(date, spec, h, rule, 'ic', e)
                        rec['ic_status'] = e.code
                    key = (spec.name, date if store.availability else date.to_period('M'), tuple(ii))
                    if key not in rhos:
                        try:
                            rhos[key] = store.historical_rho(date, ii, spec.name)
                        except DataError as e:
                            rhos[key] = e
                    try:
                        if isinstance(rhos[key], DataError):
                            raise rhos[key]
                        value, contrib = miv(ww, iv, rhos[key])
                        rec.update(
                            miv=value,
                            spread=index_iv - value,
                            miv_status='PASS',
                            miv_normalized=value / a.sum()
                        )
                    except DataError as e:
                        reject(date, spec, h, rule, 'miv', e)
                        rec['miv_status'] = e.code
                        contrib = np.full(k, np.nan)
                    for j, p in enumerate(ii):
                        constituents.append({
                            'date': date,
                            'index': spec.name,
                            'horizon': h,
                            'basket': rule,
                            'permno': int(p),
                            'weight': float(ww[j]),
                            'original_weight': float(fullw[chosen[j]]),
                            'original_cap_mass': float(capmass[chosen[j]]),
                            'iv': float(iv[j]),
                            'miv_contribution': float(contrib[j])
                        })
                    try:
                        x, _, ix = store.grid(
                            date - pd.Timedelta(days=h),
                            date,
                            ii,
                            None,
                            asof=date,
                            min_sessions=config.min_sessions,
                            require_complete=False
                        )
                        past = available_pair_rc(x, a, config.min_sessions)
                        rec['rc_past'] = past.pop('rc')
                        rec.update({'past_' + key: value for key, value in past.items()})
                    except DataError as e:
                        reject(date, spec, h, rule, 'past_rc', e)
                    try:
                        x, y, _ = store.grid(
                            date - pd.Timedelta(days=h),
                            date,
                            ii,
                            spec.name,
                            asof=date,
                            min_sessions=config.min_sessions
                        )
                        rec['mic_rc_past'] = mic_comparators(x, y, ww, iv)['mic_rc_future']
                    except DataError as e:
                        reject(date, spec, h, rule, 'past_mic', e)
                    try:
                        if asof is not None and end_label > pd.Timestamp(asof):
                            raise DataError('LABEL_NOT_MATURED')
                        if beyond_cutoff:
                            raise DataError('LABEL_BEYOND_OBSERVATION_CUTOFF')
                        x, _, ix = store.grid(date, end_label, ii, None, min_sessions=config.min_sessions, require_complete=False)
                        available = store.label_available(ix, ii, None, config.information_lag_sessions)
                        if asof is not None and available > pd.Timestamp(asof):
                            raise DataError('LABEL_NOT_AVAILABLE')
                        future = available_pair_rc(x, a, config.min_sessions)
                        rc = future.pop('rc')
                        rec.update({'future_' + key: value for key, value in future.items()})
                        # Preserve conservative bounds for the original full-grid
                        # target, separately from pairwise observed-session RC.
                        rec.update(pair_rc_bounds(x, a))
                        rec.update(
                            rc_future=rc,
                            rc_weight_only=available_pair_rc(x, ww, config.min_sessions)['rc'],
                            rc_equal_pair=available_pair_rc(x, np.ones(k), config.min_sessions)['rc'],
                            label_available_at=available,
                            label_sessions=len(ix),
                            label_first_session=ix[0],
                            label_last_session=ix[-1],
                            label_status='PASS'
                        )
                        rec['gap'] = rec.get('ic', np.nan) - rc
                    except DataError as e:
                        reject(date, spec, h, rule, 'future_rc', e)
                        rec['label_status'] = e.code
                        if e.code in (
                            'MISSING_FUTURE_RETURNS',
                            'RETURN_DURATION_DISCONTINUITY',
                            'DELISTING_DISCONTINUITY',
                            'CORPORATE_ACTION_DISCONTINUITY'
                        ):
                            ix = store.calendar[(store.calendar > date) & (store.calendar <= end_label)]
                            try:
                                partial = store.wide.reindex(index=ix, columns=ii).to_numpy(float)
                                covered_ids = ii[np.isfinite(partial).all(axis=0)]
                                available = store.label_available(ix, covered_ids, None, config.information_lag_sessions)
                                if asof is not None and available > pd.Timestamp(asof):
                                    raise DataError('BOUNDS_NOT_AVAILABLE_ASOF')
                                rec.update(pair_rc_bounds(partial, a))
                                rec['rc_bounds_available_at'] = available
                            except DataError as bounds_error:
                                reject(date, spec, h, rule, 'future_rc_bounds', bounds_error)
                    try:
                        if asof is not None and end_label > pd.Timestamp(asof):
                            raise DataError('LABEL_NOT_MATURED')
                        if beyond_cutoff:
                            raise DataError('LABEL_BEYOND_OBSERVATION_CUTOFF')
                        x, y, ix = store.grid(date, end_label, ii, spec.name, min_sessions=config.min_sessions)
                        available = store.label_available(ix, ii, spec.name, config.information_lag_sessions)
                        if asof is not None and available > pd.Timestamp(asof):
                            raise DataError('LABEL_NOT_AVAILABLE')
                        rec.update(mic_comparators(x, y, ww, iv))
                        rec['mic_gap'] = rec.get('mic', np.nan) - rec['mic_rc_future']
                        rec['mic_label_available_at'] = available
                        rec['mic_label_status'] = 'PASS'
                    except DataError as e:
                        reject(date, spec, h, rule, 'future_mic', e)
                        rec['mic_label_status'] = e.code
                    rec['incremental_compute_seconds'] = time.perf_counter() - basket_timer
                    records.append(rec)
    panel = pd.DataFrame(records)
    if panel.empty:
        panel = pd.DataFrame(columns=[
            'date',
            'index',
            'horizon',
            'basket',
            'ic_status',
            'miv_status',
            'label_status'
        ])
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'scipy', 'pyarrow', 'exchange-calendars', 'wrds')}
    source_root = Path(__file__).resolve().parents[1]
    code_hashes = {f.relative_to(source_root).as_posix(): sha256(f) for f in source_root.rglob('*.py')}
    config_hash = hashlib.sha256(json.dumps(config.__dict__, sort_keys=True, default=str).encode()).hexdigest()
    exclusion_frame = pd.DataFrame(exclusions)
    # Universe failures have no horizon/identifier; keep shard schemas stable.
    for column in ('horizon', 'permno'):
        if column in exclusion_frame:
            exclusion_frame[column] = pd.array(exclusion_frame[column], dtype='Int64')
    return {
        'measurements': panel,
        'exclusions': exclusion_frame,
        'constituents': pd.DataFrame(constituents),
        'packages': pd.DataFrame(packages),
        'metadata': {'elapsed_seconds': time.perf_counter() - timer, 'runtime_versions': versions, 'code_sha256': code_hashes, 'config_sha256': config_hash, 'raw_metadata': bundle.metadata, 'config': config.__dict__, 'signal_grid_count': len(grid), 'live_wrds_integration': 'NOT_RUN', 'rate_convention_status': 'USER_SELECTED_KEVIN_RULE' if config.rate_unit == 'kevin' else 'PROVISIONAL' if provisional else 'CERTIFIED', 'availability_assumption': {'entry_features': 'same-date observations; historical publication/decision time NOT VERIFIED', 'future_labels': f'latest observation/explicit availability + {config.information_lag_sessions} exchange session(s)'}, 'licensed': not bundle.metadata.get('synthetic', False)}
    }
# Persist named financial tables and fingerprint the completed output set.

def write_outputs(result, root):
    """Persist named financial tables and fingerprint the completed output set."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for k, v in result.items():
        if isinstance(v, pd.DataFrame):
            v.to_parquet(root / (k + '.parquet'), index=False)
        else:
            (root / (k + '.json')).write_text(json.dumps(v, indent=2, default=str))
    (root / 'output_manifest.json').write_text(json.dumps(
        {f.name: sha256(f) for f in root.iterdir() if f.is_file() and f.name != 'output_manifest.json'},
        indent=2
    ))
