"""Local WRDS authentication and a bounded exact-query cache."""
import os
from .query_cache import CachedWRDS

def get_wrds_connection(cache=True, cache_dir=None):
    import wrds
    from src.research.errors import DataError
    username = os.environ.get("WRDS_USERNAME")
    if not username:
        raise DataError("WRDS_USERNAME_UNSET", "Set WRDS_USERNAME locally; WRDS handles credentials.")
    db = wrds.Connection(wrds_username=username)
    return CachedWRDS(db, cache_dir or os.environ.get("DISPERSION_CACHE", "data/cache/queries")) if cache else db
