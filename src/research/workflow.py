"""One explicit local research workflow; importing it never queries WRDS or fits."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
import pandas as pd
from .dataset import read_config, prepare, inputs, raw_inputs
from .inputs import sha256
from .measurement import available_pair_rc
from .store import dump
from .modeling import design, predict, train_for, run_models
from .modeling import fit_least_squares
# Read-only source validation before expensive local work; no database login.

def readiness(cfg):
    """Read-only source validation before expensive local work; no database login."""
    from .store import DiskBundle
    bundle = DiskBundle(cfg['raw_root']).validate()
    measurement = Path(cfg['measurements_root'])
    for name in ['financial_panel.parquet', 'constituents.parquet']:
        if not (measurement / name).exists():
            raise FileNotFoundError('MISSING_MEASUREMENT: ' + name)
    return {
        'status': 'PASS',
        'raw_tables': len(bundle.manifest['tables']),
        'configured_evaluation_end': cfg['evaluation_end'], 'source_entry_end': bundle.metadata.get('effective_entry_end'),
        'new_WRDS_queries': 0,
        'scope': 'Checks local input integrity, not vendor vintage or full-index certification'
    }
# Verify real arithmetic, entry timing, saved models and pre-cleanup parity.

def verify(cfg):
    """Verify real arithmetic, entry timing, saved models and pre-cleanup parity."""
    import statsmodels.api as sm
    frame, calendar = inputs(cfg)
    _, _, _, wide, members = raw_inputs(cfg)
    arithmetic = []
    from .correlation_features import entry_features
    # Explicit matrices provide an independent check of the fast basket identity.
    for year, group in frame.loc[frame.complete_features].groupby(frame.date.dt.year):
        row = group.iloc[len(group) // 2]
        entry = members[row.date]
        a, ids = (entry.a.to_numpy(float), entry.permno.tolist())
        dates = calendar[calendar <= row.date][-cfg['slow_history_sessions']:]
        x = wide.reindex(index=dates, columns=ids).to_numpy(float)
        p = 2.0 ** (-np.arange(len(x) - 1, -1, -1) / cfg['slow_half_life_sessions'])
        covariance = np.cov(x, rowvar=False, aweights=p, bias=True)
        slow = covariance / np.sqrt(np.outer(covariance.diagonal(), covariance.diagonal()))
        negative = np.minimum(x[-cfg['downside_sessions']:], 0)
        products = negative.T @ negative
        downside = products / np.sqrt(np.outer(products.diagonal(), products.diagonal()))
        pairs = np.triu_indices(len(a), 1)
        weights = np.outer(a, a)[pairs]
        explicit = lambda matrix: float(np.average(matrix[pairs], weights=weights))
        errors = [abs(explicit(slow) - row.slow_rc), abs(explicit(downside) - row.downside_rc)]
        future = calendar[(calendar > row.date) & (calendar <= row.label_end)]
        returns = wide.reindex(index=future, columns=ids).to_numpy(float)
        matrix = pd.DataFrame(returns).corr(min_periods=10).to_numpy()[pairs]
        known = np.isfinite(matrix)
        direct = float(np.average(matrix[known], weights=weights[known]))
        estimated = available_pair_rc(returns, a)['rc']
        errors.extend([abs(estimated - direct), abs(estimated - row.rc_future)])
        changed = wide.copy()
        changed.loc[changed.index > row.date] = 999.0
        again = entry_features(changed, calendar, row.date, ids, a, cfg)
        if max(errors) > 1e-10 or again['slow_rc'] != row.slow_rc or again['downside_rc'] != row.downside_rc:
            raise ValueError('REAL_ARITHMETIC_OR_FEATURE_LOOKAHEAD')
        arithmetic.append({'year': int(year), 'maximum_error': max(errors)})
    # Every saved equation must reconstruct forecasts on exactly the same test dates.
    root = Path(cfg['output_root'])
    bundle = json.loads((Path(cfg['dataset_root']) / 'models.json').read_text())
    saved_forecasts = root / 'models/all_forecasts.parquet'
    predictions = pd.read_parquet(saved_forecasts) if saved_forecasts.exists() else None
    checks = []
    for model in ['A', 'B']:
        for spec, features in cfg['specifications'].items():
            train = train_for(frame, cfg['training_end'], model, cfg)
            fit = fit_least_squares(train[features], train.rc_future)
            reference = sm.OLS(train.rc_future, design(train, features)).fit()
            alternate = frame.copy()
            alternate.loc[alternate.date > pd.Timestamp(cfg['training_end']), 'rc_future'] = 999.0
            t2 = train_for(alternate, cfg['training_end'], model, cfg)
            second = fit_least_squares(t2[features], t2.rc_future)
            if not np.array_equal(fit['coefficients'], second['coefficients']):
                raise ValueError('FUTURE_TARGET_LEAKAGE')
            saved = bundle['fits'][f'{model}/{spec}']
            test = frame.loc[frame.complete_features & frame.date.between(cfg['evaluation_start'], cfg['evaluation_end'])]
            expected_prediction = predict(fit, test, features)
            delta = float(np.max(abs(design(test, features) @ np.asarray(saved['coefficients']) - expected_prediction)))
            if predictions is not None:
                d = predictions.loc[(predictions.phase == 'final') & (predictions.model == model) & (predictions.specification == spec)]
                if list(d.date) != list(test.date) or not np.allclose(d.prediction, expected_prediction, atol=1e-10, rtol=0):
                    raise ValueError('SAVED_FORECASTS_DIFFER_FROM_RETAINED_MODELS')
            if np.max(abs(fit['coefficients'] - np.asarray(saved['coefficients']))) > 1e-10:
                raise ValueError('SAVED_COEFFICIENTS_DIFFER_FROM_CURRENT_FIT')
            if delta > 1e-10 or np.max(abs(reference.params - fit['coefficients'])) > 1e-10:
                raise ValueError('SAVED_MODEL_RECONSTRUCTION')
            checks.append({
                'model': model,
                'specification': spec,
                'n_train': len(train),
                'saved_prediction_error': delta
            })
    if predictions is not None:
        for phase, d in predictions.groupby('phase'):
            wanted = set(d.date)
            if not all((set(g.date) == wanted for _, g in d.groupby(['model', 'specification']))):
                raise ValueError('UNMATCHED_COMPARISON_DATES')
    # Old five-variable fits used a broader eligible history; reproduce that sample
    # separately so a fair common-sample refit cannot be mistaken for numerical drift.
    baseline = Path(cfg['dataset_root'])
    parity = []
    if (baseline / 'reference_fits.json').exists():
        old = json.loads((baseline / 'reference_fits.json').read_text())
        for key, record in old.items():
            model, spec = key.split('/')
            f = frame.copy()
            if spec == 'expanded':
                f['complete_features'] = f.base_features_available
            train = train_for(f, cfg['training_end'], model, cfg)
            fit = fit_least_squares(train[record['features']], train.rc_future)
            error = float(np.max(abs(fit['coefficients'] - record['coefficients'])))
            # A changed, explicitly authorized measurement target is not a
            # cleanup parity comparison. Retain the original reference and
            # disclose its coefficient difference instead of overwriting it.
            changed_policy = 'measurement_policy' in frame and frame.measurement_policy.eq('available_inputs_v1').all()
            if error > 1e-10 and not changed_policy:
                raise ValueError('PRE_CLEANUP_PARITY_FAILED: ' + key)
            parity.append({
                'model': model,
                'specification': spec,
                'coefficient_error': error,
                'status': 'CHANGED_MEASUREMENT_POLICY' if changed_policy else 'PASS'
            })
    result = {
        'status': 'PASS',
        'annual_explicit_arithmetic': arithmetic,
        'saved_fit_checks': checks,
        'pre_cleanup_native_sample_parity': parity,
        'independent_scientific_review': 'NOT_RUN'
    }
    dump(result, root / 'verification.json')
    return result
# Bind saved fits to the fitting implementation as well as the input panel.
def model_code():
    """Fingerprint the workflow, fitting arithmetic and authoritative solver."""
    directory = Path(__file__).parent
    return {name: sha256(directory / name) for name in ['workflow.py', 'modeling.py']}


# Require models fitted on this exact panel/config before scoring or reporting.

def check_models(cfg):
    """Require models fitted on this exact panel/config before scoring or reporting."""
    manifest = json.loads((Path(cfg['dataset_root']) / 'models.json').read_text())['manifest']
    if manifest['prepared_panel_sha256'] != sha256(Path(cfg['dataset_root']) / 'dataset.parquet') or manifest['config'] != cfg or manifest.get('model_code') != model_code():
        raise ValueError('STALE_FITTED_MODELS: run study fit on the current prepared data')
# Dispatch one declared phase and persist provenance without credentials.

def run(phase, config='configs/study.json'):
    """Dispatch one declared phase and persist provenance without credentials."""
    cfg = read_config(config)
    root = Path(cfg['output_root'])
    root.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc)
    record = {
        'started_utc': start.isoformat(),
        'phase': phase,
        'config': cfg,
        'command': ' '.join(sys.argv),
        'python': sys.version.split()[0],
        'versions': {n: importlib.metadata.version(n) for n in ['numpy', 'pandas', 'scipy', 'statsmodels', 'pyarrow']},
        'source_sha256': {str(p): sha256(p) for p in Path('src/research').glob('*.py')},
        'new_WRDS_queries': 0
    }
    try:
        if phase == 'check':
            result = readiness(cfg)
        elif phase == 'prepare':
            result = prepare(cfg)
        elif phase == 'fit':
            frame, calendar = inputs(cfg)
            from .store import _publish
            # Publish the entire completed model set, leaving prior models intact on failure.
            with tempfile.TemporaryDirectory(prefix='.fit-', dir=root) as folder:
                staging = Path(folder)
                p = run_models(frame, calendar, cfg, staging / 'models')
                if json.loads((staging / 'models/failures.json').read_text()):
                    raise ValueError('INCOMPLETE_MODEL_SET')
                dump(
                    {
                        'prepared_panel_sha256': sha256(Path(cfg['dataset_root']) / 'dataset.parquet'),
                        'config': cfg,
                        'training_information_end': cfg['training_end'], 'model_code': model_code()
                    },
                    staging / 'models/manifest.json'
                )
                _publish(staging, root)
            fits = {
                f'{model}/{spec}': json.loads((root / f'models/{model}_{spec}_fit.json').read_text())
                for model in ['A', 'B'] for spec in cfg['specifications']
            }
            dump({'manifest': json.loads((root / 'models/manifest.json').read_text()), 'fits': fits},
                 Path(cfg['dataset_root']) / 'models.json')
            result = {'status': 'PASS', 'forecast_rows': len(p)}
        elif phase == 'explore':
            from .exploration import explore
            explore(root, cfg)
            result = {'status': 'PASS'}
        elif phase == 'report':
            check_models(cfg)
            from .study_report import report
            result = report(cfg)
        elif phase == 'verify':
            check_models(cfg)
            result = verify(cfg)
        else:
            raise ValueError('UNKNOWN_STUDY_PHASE')
        record.update(status='PASS', result=result)
        return result
    except Exception as exc:
        record.update(status='FAIL', error_type=type(exc).__name__)
        raise
    finally:
        record['elapsed_seconds'] = (datetime.now(timezone.utc) - start).total_seconds()
        dump(record, root / 'runs' / (start.strftime('%Y%m%dT%H%M%S%f') + '_' + phase + '.json'))
