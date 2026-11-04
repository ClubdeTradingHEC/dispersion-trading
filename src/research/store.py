"""Partitioned raw inputs: verify on disk, load only a measurement window."""
from pathlib import Path
import json
import shutil
import tempfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .inputs import Bundle, TABLES, sha256, normalize_table
from .errors import DataError
# Publish owned files/bundles; roll back failures and interruptions.

def _publish(staging, root):
    """Publish owned files/bundles; roll back failures and interruptions.

    The output manifest is installed last. Use one writer and wait before reading.
    Failed recovery retains previous outputs, including complete bundle directories.
    """
    root = root.resolve()
    sources = sorted(staging.iterdir(), key=lambda p: (p.name == 'output_manifest.json', p.name))
    for source in sources:
        if not (root / source.name).resolve().is_relative_to(root):
            raise DataError('UNSAFE_OUTPUT_PATH')
    backup = Path(tempfile.mkdtemp(prefix='.previous-output-', dir=root))
    moved, installed = ([], [])
    recovered = False
    try:
        for source in sources:
            target = root / source.name
            # Register before rename: an interrupt can arrive just after success.
            if target.exists():
                moved.append(source.name)
                target.replace(backup / source.name)
            installed.append(source.name)
            source.replace(target)
        recovered = True
    except BaseException:
        try:
            for name in reversed(installed):
                target = root / name
                if not target.resolve().is_relative_to(root):
                    raise DataError('UNSAFE_OUTPUT_PATH')
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            for name in reversed(moved):
                previous = backup / name
                if previous.exists():
                    previous.replace(root / name)
            recovered = True
        except BaseException as rollback_error:
            raise DataError('OUTPUT_ROLLBACK_FAILED', f'Previous outputs retained in {backup}') from rollback_error
        raise
    finally:
        if recovered:
            if not backup.resolve().is_relative_to(root):
                raise DataError('UNSAFE_OUTPUT_PATH')
            shutil.rmtree(backup)
# Write partitioned licensed inputs with schema/count/hash provenance.

class BundleWriter:
    """Write partitioned licensed inputs with schema/count/hash provenance."""

    def __init__(self, root, metadata):
        """Initialize the declared object and retain its explicit dependencies."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.manifest = {'metadata': metadata, 'tables': {}}

    def add(self, name, frame):
        """Append a normalized input partition and record its checksum and row count."""
        missing = set(TABLES[name]) - set(frame)
        if missing:
            raise DataError('MISSING_RAW_FIELDS', f'{name}: {missing}')
        frame = normalize_table(name, frame.copy())
        parts = self.manifest['tables'].setdefault(name, {'parts': [], 'rows': 0})
        folder = self.root / (name + '.parquet')
        folder.mkdir(exist_ok=True)
        path = folder / f"part-{len(parts['parts']):05d}.parquet"
        frame.to_parquet(path, index=False)
        parts['parts'].append({
            'file': path.relative_to(self.root).as_posix(),
            'rows': len(frame),
            'sha256': sha256(path)
        })
        parts['rows'] += len(frame)

    def finish(self):
        """Complete the input manifest only after all declared shards are written."""
        missing = set(TABLES) - set(self.manifest['tables'])
        if missing:
            raise DataError('MISSING_RAW_TABLE', str(missing))
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest, indent=2, default=str))
        return DiskBundle(self.root)
# Validate local source shards and load only required measurement windows.

class DiskBundle:
    """Validate local source shards and load only required measurement windows."""

    def __init__(self, root):
        """Initialize the declared object and retain its explicit dependencies."""
        self.root = Path(root)
        self.manifest = json.loads((self.root / 'manifest.json').read_text())
        self.metadata = self.manifest['metadata']
        self._verified = False

    def validate(self):
        """Validate input fields and invariants before financial calculations."""
        if self._verified:
            return self
        if set(self.manifest['tables']) != set(TABLES):
            raise DataError('MISSING_RAW_TABLE')
        for name, spec in self.manifest['tables'].items():
            parts = spec.get('parts', [spec])
            total = 0
            for part in parts:
                relative = Path(part['file'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise DataError('UNSAFE_MANIFEST_PATH')
                path = self.root / relative
                if not path.resolve().is_relative_to(self.root.resolve()):
                    raise DataError('UNSAFE_MANIFEST_PATH')
                if sha256(path) != part['sha256']:
                    raise DataError('RAW_CHECKSUM_MISMATCH', name)
                footer = pq.ParquetFile(path)
                if footer.metadata.num_rows != part['rows']:
                    raise DataError('RAW_ROW_COUNT_MISMATCH', name)
                if not set(TABLES[name]) <= set(footer.schema_arrow.names):
                    raise DataError('MISSING_RAW_FIELDS', name)
                total += part['rows']
            if total != spec['rows']:
                raise DataError('RAW_ROW_COUNT_MISMATCH', name)
        self._verified = True
        return self

    def read_table(self, name, first=None, last=None, identifiers=None, id_column=None):
        """Validate and read the filtered partitions for one normalized source table."""
        self.validate()
        parts = self.manifest['tables'][name].get('parts', [self.manifest['tables'][name]])
        frames = []
        for part in parts:
            path = self.root / part['file']
            filters = [('date', '>=', pd.Timestamp(first)), ('date', '<=', pd.Timestamp(last))] if first is not None and 'date' in TABLES[name] else []
            if identifiers is not None:
                filters.append((id_column, 'in', list(identifiers)))
            frames.append(pd.read_parquet(path, filters=filters or None))
        return pd.concat(frames, ignore_index=True)

    @property
    def calendar(self):
        """Load sorted exchange-session metadata from the verified source bundle."""
        return self.read_table('calendar').sort_values('date').reset_index(drop=True)

    def window(self, first, last, horizon):
        """Bound financial inputs while preserving required history and future-label tails."""
        history = (first.to_period('M') - 36).start_time
        tail = last + pd.Timedelta(days=horizon + 14)
        membership = self.read_table('membership')
        active = membership.loc[(membership.start <= last) & (membership.end.isna() | (membership.end >= first))]
        ids = active.permno.unique().tolist()
        links = self.read_table('links')
        links = links.loc[links.permno.isin(ids)].copy()
        tables = {'membership': membership, 'links': links}
        secids = links.secid.unique().tolist() + self.metadata.get('index_secids', [])
        for name in TABLES:
            if name in tables:
                continue
            lo, hi = (first, last) if name in ('surface', 'forwards', 'curve', 'caps') else (history, tail)
            if name in ('returns', 'caps'):
                tables[name] = self.read_table(name, lo, hi, ids, 'permno')
            elif name in ('surface', 'forwards') and 'index_secids' in self.metadata:
                tables[name] = self.read_table(name, lo, hi, secids, 'secid')
            else:
                tables[name] = self.read_table(name, lo, hi)
        return Bundle(tables, self.metadata).validate()


def dump(value, path):
    """Serialize finite, inspectable metadata without nonstandard JSON NaN values."""

    def clean(x):
        """Convert NumPy/scalar metadata into strict, finite JSON-compatible values."""
        if isinstance(x, dict):
            return {str(k): clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple, np.ndarray)):
            return [clean(v) for v in x]
        if isinstance(x, (float, np.floating)):
            return float(x) if np.isfinite(x) else None
        if isinstance(x, (bool, np.bool_)):
            return bool(x)
        if isinstance(x, (int, np.integer)):
            return int(x)
        return x
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(clean(value), indent=2, default=str, allow_nan=False) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.metadata-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
