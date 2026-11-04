"""Bound measurement intermediates without changing entry baskets or estimators."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import tempfile
import time
import pandas as pd
import pyarrow as pa
from .inputs import sha256
from .pipeline import compute, write_outputs
from .errors import DataError
from .store import _publish

# Aggregate small panels; write large constituent/package tables in shards.

def compute_to_disk(
    bundle,
    config,
    root,
    dates=None,
    asof=None,
    batch_sessions=252,
    *,
    provisional=False,
    checkpoint_root=None,
    progress=None
):
    """Aggregate small panels; write large constituent/package tables in shards.

    DiskBundle loads filtered raw windows. Chunking bounds wide return grids,
    pricing caches and the much larger per-basket constituent output.
    """
    if not isinstance(batch_sessions, int) or batch_sessions < 1:
        raise ValueError('batch_sessions must be a positive integer')
    bundle.validate()
    config.validate()
    if not bundle.metadata.get('synthetic', False) and (not provisional):
        config.require_rate_certification()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    grid = config.entry_grid(bundle.calendar.date)
    if dates is not None:
        grid = grid.intersection(pd.DatetimeIndex(pd.to_datetime(dates)))
    small = {'measurements': [], 'exclusions': []}
    counts = {name: 0 for name in (*small, 'constituents', 'packages')}
    chunks = []
    timer = time.perf_counter()
    checkpoint_key = None
    if checkpoint_root is not None:
        relevant = [
            Path(__file__),
            Path(__file__).with_name('pipeline.py'),
            Path(__file__).with_name('inputs.py'),
            Path(__file__).with_name('pricing.py'),
            Path(__file__).with_name('measurement.py'),
            Path(__file__).with_name('config.py')
        ]
        relevant += list((Path(__file__).resolve().parents[1] / 'data').glob('*.py'))
        signature = {
            'config': config.__dict__,
            'asof': asof,
            'provisional': provisional,
            'raw_metadata': bundle.metadata,
            'batch_sessions': batch_sessions,
            'raw_manifest': bundle.manifest,
            'lock_sha256': sha256(Path(__file__).resolve().parents[2] / 'uv.lock'),
            'source_hashes': {str(f): sha256(f) for f in relevant},
            'dates': [str(d) for d in grid]
        }
        checkpoint_key = hashlib.sha256(json.dumps(signature, sort_keys=True, default=str).encode()).hexdigest()
        checkpoint_root = Path(checkpoint_root) / checkpoint_key
        checkpoint_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.measurement-', dir=root) as temp:
        staging = Path(temp)
        for number, start in enumerate(range(0, len(grid), batch_sessions)):
            entries = grid[start:start + batch_sessions]
            child = replace(
                config,
                entry_start=str(entries[0].date()),
                entry_end=str(entries[-1].date())
            )
            checkpoint = checkpoint_root / f'part-{number:05d}' if checkpoint_root is not None else None
            reused = checkpoint is not None and (checkpoint / 'output_manifest.json').exists()
            if reused:
                hashes = json.loads((checkpoint / 'output_manifest.json').read_text())
                required = {name + '.parquet' for name in counts} | {'metadata.json'}
                if not required <= set(hashes) or any((
                    not (checkpoint / name).resolve().is_relative_to(checkpoint.resolve()) or not (checkpoint / name).is_file() or sha256(checkpoint / name) != digest for name,
                    digest in hashes.items()
                )):
                    raise DataError('MEASUREMENT_CHECKPOINT_HASH_MISMATCH')
                result = {name: pd.read_parquet(checkpoint / (name + '.parquet')) for name in counts}
                result['metadata'] = json.loads((checkpoint / 'metadata.json').read_text())
            else:
                result = compute(
                    bundle.window(entries[0], entries[-1], max(config.horizons)),
                    child,
                    dates=entries,
                    asof=asof,
                    provisional=provisional
                )
                if checkpoint is not None:
                    write_outputs(result, checkpoint)
            for name in counts:
                frame = result[name]
                counts[name] += len(frame)
                if name in small:
                    small[name].append(frame)
                elif not frame.empty:
                    target = staging / (name + '.parquet')
                    target.mkdir(exist_ok=True)
                    frame.to_parquet(target / f'part-{number:05d}.parquet', index=False)
            chunks.append({
                'first_entry': child.entry_start,
                'last_entry': child.entry_end,
                'signal_grid_count': len(entries),
                'elapsed_seconds': result['metadata']['elapsed_seconds'],
                'code_sha256': result['metadata']['code_sha256'],
                'runtime_versions': result['metadata']['runtime_versions'],
                'checkpoint_reused': reused
            })
            if progress is not None:
                progress({
                    'batch': number,
                    'first_entry': child.entry_start,
                    'last_entry': child.entry_end,
                    'checkpoint_reused': reused,
                    'compute_seconds': result['metadata']['elapsed_seconds']
                })
            del result
        for name, parts in small.items():
            frame = pa.concat_tables(
                [pa.Table.from_pandas(part, preserve_index=False) for part in parts],
                promote_options='permissive'
            ).to_pandas() if parts else pd.DataFrame()
            if name == 'measurements' and frame.empty:
                frame = pd.DataFrame(columns=[
                    'date',
                    'index',
                    'horizon',
                    'basket',
                    'ic_status',
                    'miv_status',
                    'label_status'
                ])
            frame.to_parquet(staging / (name + '.parquet'), index=False)
        for name in ('constituents', 'packages'):
            if not (staging / (name + '.parquet')).exists():
                pd.DataFrame().to_parquet(staging / (name + '.parquet'), index=False)
        metadata = {
            'elapsed_seconds': time.perf_counter() - timer,
            'batch_sessions': batch_sessions,
            'chunks': chunks,
            'signal_grid_count': len(grid),
            'row_counts': counts,
            'config': config.__dict__,
            'config_sha256': hashlib.sha256(json.dumps(config.__dict__, sort_keys=True, default=str).encode()).hexdigest(),
            'raw_metadata': bundle.metadata,
            'licensed': not bundle.metadata.get('synthetic', False),
            'live_wrds_integration': 'NOT_RUN',
            'rate_convention_status': 'USER_SELECTED_KEVIN_RULE' if config.rate_unit == 'kevin' else 'PROVISIONAL' if provisional else 'CERTIFIED',
            'availability_assumption': {'entry_features': 'same-date observations; historical publication/decision time NOT VERIFIED', 'future_labels': f'latest observation/explicit availability + {config.information_lag_sessions} exchange session(s)'},
            'storage': 'measurements/exclusions: files; nonempty constituents/packages: Parquet dataset directories',
            'checkpoint_key': checkpoint_key
        }
        (staging / 'metadata.json').write_text(json.dumps(metadata, indent=2, default=str))
        manifest = {f.relative_to(staging).as_posix(): sha256(f) for f in staging.rglob('*') if f.is_file()}
        (staging / 'output_manifest.json').write_text(json.dumps(manifest, indent=2))
        _publish(staging, root)
    return metadata
