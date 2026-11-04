"""Exact-query disk cache; a query is the unit of reuse, never a security row."""

from collections import OrderedDict
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
import pandas as pd
from src.research.inputs import sha256
from src.research.errors import DataError


class CachedWRDS:
    """Single-writer local cache. Use separate directories for concurrent writers.

    A dated historical query remains reproducible until explicitly refreshed.
    Database corrections do not automatically invalidate previously saved data.
    """

    def __init__(self, db, root, memory_bytes=64 * 1024**2):
        self.db, self.root = db, Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory_bytes, self._bytes = memory_bytes, 0
        self._memory = OrderedDict()

    def __getattr__(self, name):
        return getattr(self.db, name)

    def raw_sql(self, sql, date_cols=None, **kwargs):
        # Non-JSON query options bypass caching rather than produce a wrong key.
        try:
            # Indexed v2 cache entries lost their index on disk. Keep ordinary
            # v2 queries reusable; give indexed results a corrected namespace.
            signature = json.dumps({"version": 3 if kwargs.get("index_col") is not None else 2, "sql": sql,
                "date_cols": list(date_cols or []), "kwargs": kwargs}, sort_keys=True)
        except TypeError:
            return self.db.raw_sql(sql, date_cols=date_cols, **kwargs)
        key = hashlib.sha256(signature.encode()).hexdigest()
        if key in self._memory:
            self._memory.move_to_end(key)
            return self._memory[key].copy(deep=True)
        path, receipt = self.root / (key + ".parquet"), self.root / (key + ".json")
        if path.exists() and receipt.exists():
            info = json.loads(receipt.read_text())
            if info.get("query_sha256") != key:
                raise DataError("QUERY_CACHE_KEY_MISMATCH", key)
            if sha256(path) != info["sha256"]:
                raise DataError("QUERY_CACHE_CORRUPT", key)
            frame = pd.read_parquet(path)
            if len(frame) != info["rows"]:
                raise DataError("QUERY_CACHE_ROW_COUNT", key)
        else:
            frame = self.db.raw_sql(sql, date_cols=list(date_cols or []), **kwargs)
            with tempfile.NamedTemporaryFile(dir=self.root, suffix=".part", delete=False) as f:
                temporary = Path(f.name)
            try:
                frame.to_parquet(temporary)
                os.replace(temporary, path)
                info = {"rows": len(frame), "sha256": sha256(path),
                    "query_sha256": key, "extracted_at": datetime.now(timezone.utc).isoformat()}
                temporary.write_text(json.dumps(info, indent=2))
                os.replace(temporary, receipt)
            finally:
                temporary.unlink(missing_ok=True)
        size = int(frame.memory_usage(deep=True).sum())
        if size <= self.memory_bytes:
            while self._memory and self._bytes + size > self.memory_bytes:
                _, previous = self._memory.popitem(last=False)
                self._bytes -= int(previous.memory_usage(deep=True).sum())
            self._memory[key] = frame.copy(deep=True)
            self._bytes += size
        return frame

    def close(self):
        self._memory.clear()
        self._bytes = 0
        return self.db.close()

