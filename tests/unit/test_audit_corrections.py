"""Independent small numerical fixtures for demonstrated audit failures."""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from src.data.rates import zero_rate
from src.research.config import Config
from src.research.errors import DataError
from src.research.inputs import (
    Bundle, TABLES, ReturnStore, normalize_table, require_available, map_secid,
)
from src.research.measurement import pair_rc, pair_rc_bounds, mic_comparators
from src.research.subsets import assess


def test_sentinel_node_cannot_interpolate_to_plausible_rate():
    date = pd.Timestamp("2024-01-02")
    curve = pd.DataFrame({"date": [date, date], "days": [10, 50], "rate": [-99.99, 2.0]})
    with pytest.raises(DataError, match="INVALID_ZERO_CURVE"):
        zero_rate(curve, date, 49, "percent")


def return_fixture(available=False):
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    stocks = pd.DataFrame({
        "date": dates.repeat(2), "permno": [1, 2] * 3,
        "return": [.01, .03, .02, .01, .03, .02],
    })
    index = pd.DataFrame({"date": dates, "index": "SPX", "return": [.01, np.nan, .02]})
    if available:
        stocks["available_at"] = pd.NaT
    return ReturnStore(SimpleNamespace(returns=stocks, index_returns=index,
        calendar=pd.DataFrame({"date": dates})))


def test_stock_only_grid_survives_missing_index():
    store = return_fixture()
    x, y, ix = store.grid(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-04"),
        [1, 2], min_sessions=3)
    assert y is None and len(ix) == 3
    assert pair_rc(x, [.1, .1]) == pytest.approx(-.5, abs=1e-12)
    with pytest.raises(DataError, match="MISSING_INDEX_RETURNS"):
        store.grid(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-04"),
            [1, 2], "SPX", min_sessions=3)


def test_explicit_missing_return_availability_fails():
    store = return_fixture(available=True)
    with pytest.raises(DataError, match="MISSING_AVAILABILITY_DATE"):
        store.grid(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-04"),
            [1, 2], asof=pd.Timestamp("2024-01-05"), min_sessions=3)


def test_availability_time_is_preserved_and_checked():
    stamp = pd.Timestamp("2024-01-02 16:15")
    frame = pd.DataFrame({"date": [stamp], "available_at": [stamp]})
    normalize_table("calendar", frame)
    assert frame.date.iloc[0] == stamp.normalize()
    assert frame.available_at.iloc[0] == stamp
    with pytest.raises(DataError, match="LATE"):
        require_available(frame, pd.Timestamp("2024-01-02 16:00"), "LATE")
    frame.loc[0, "available_at"] = pd.NaT
    with pytest.raises(DataError, match="MISSING_AVAILABILITY_DATE"):
        require_available(frame, stamp, "LATE")


def test_link_availability_checked():
    links = pd.DataFrame({"permno": [1], "secid": [2], "score": [1],
        "sdate": [pd.NaT], "edate": [pd.NaT], "available_at": [pd.NaT]})
    with pytest.raises(DataError, match="MISSING_AVAILABILITY_DATE"):
        map_secid(links, 1, pd.Timestamp("2024-01-02"))


def test_constant_reconstructed_basket_preserves_official_comparator():
    x = np.array([[.01, -.01], [.02, -.02], [.03, -.03]])
    result = mic_comparators(x, [.01, .03, .02], [.5, .5], [.2, .2])
    assert pair_rc(x, [.1, .1]) == pytest.approx(-1)
    assert result["mic_rc_future"] == pytest.approx(0, abs=1e-12)
    assert result["mic_basket_status"] == "ZERO_VARIANCE_BASKET"
    assert np.isnan(result["mic_identity_residual"])


def test_missing_pair_bounds_preserve_original_mass():
    x = np.array([[.01,.03,np.nan], [.02,.01,.01], [.03,.02,.02]])
    bounds = pair_rc_bounds(x, [.1,.2,.3])
    # Pair masses .02/.11, .03/.11, .06/.11; known correlation -1/2.
    assert bounds["missing_pair_mass"] == pytest.approx(9/11)
    assert bounds["rc_covered_pair_contribution"] == pytest.approx(-1/11)
    assert bounds["rc_future_lower_bound"] == pytest.approx(-10/11)
    assert bounds["rc_future_upper_bound"] == pytest.approx(8/11)
    assert bounds["rc_bounds_status"] == "PARTIAL_BOUNDS"


def test_bounds_remain_conservative_for_small_covered_weights():
    x = np.array([[.01,.01,np.nan], [.02,.02,.02], [.03,.03,.03]])
    bounds = pair_rc_bounds(x, [1e-8,1e-8,9.8e-7])
    assert bounds["rc_future_upper_bound"] == pytest.approx(1)


def test_indexed_cache_disk_roundtrip_and_receipt_key(tmp_path):
    from src.data.query_cache import CachedWRDS
    import json
    class DB:
        calls = 0
        def raw_sql(self, sql, **kwargs):
            self.calls += 1
            return pd.DataFrame({"value":[10,20]},index=pd.Index([7,8],name="key"))
    db = DB()
    CachedWRDS(db,tmp_path,memory_bytes=0).raw_sql("SELECT key,value",index_col="key")
    read = CachedWRDS(db,tmp_path,memory_bytes=0).raw_sql("SELECT key,value",index_col="key")
    assert list(read.index) == [7,8] and read.index.name == "key"
    assert db.calls == 1
    path = next(tmp_path.glob("*.json"))
    metadata = json.loads(path.read_text())
    metadata["query_sha256"] = "wrong_query"
    path.write_text(json.dumps(metadata))
    with pytest.raises(DataError,match="QUERY_CACHE_KEY_MISMATCH"):
        CachedWRDS(db,tmp_path,memory_bytes=0).raw_sql("SELECT key,value",index_col="key")


@pytest.mark.parametrize("candidate,count", [("top_2", 2), ("weight_0.95", 3)])
def test_reference_and_unreduced_rule_cannot_qualify(candidate, count):
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04",
        "2024-01-09", "2024-01-10", "2024-01-11"])
    rows = []
    for basket, n, error in [("full", 3, 0), (candidate, count, .3 if count == 2 else 0)]:
        for date in dates:
            rows.append(dict(date=date, index="SPX", horizon=30, basket=basket,
                n_selected=n, original_cap_coverage=n/3, ic_status="PASS", ic=.4+error))
    cfg = Config(entry_start="2024-01-02", entry_end="2024-01-11", calibration_end="2024-01-08",
        basket_tolerances={"ic": .02}, basket_min_dates=3, bootstrap_repetitions=99,
        basket_tolerances_confirmed=True)
    scores, decisions = assess(pd.DataFrame(rows), dates, cfg)
    assert decisions[0]["status"] == "NO_ACCEPTED_RULE"
    assert decisions[0]["selected_rule"] is None
    assert not scores.loc[scores.basket == "full", "is_reduced_candidate"].any()


def test_partial_model_scores_keep_declared_common_date_scope():
    from src.research.modeling import compare_losses
    dates=pd.bdate_range('2024-01-02', periods=4)
    rows=[]
    for spec, values in {'baseline':[.2,.4,.6,.8], 'ic_only':[.1,.4,.8,np.nan]}.items():
        for date,actual,value in zip(dates,[.2,.4,.6,.8],values):
            rows.append({'date':date,'phase':'final','model':'A','specification':spec,'actual':actual,'prediction':value})
    cfg={'bootstrap_block_sessions':2,'bootstrap_repetitions':99,'seed':7}
    score=compare_losses(pd.DataFrame(rows), dates, cfg)
    row=score.loc[(score.specification=='ic_only')&(score.benchmark=='baseline')].iloc[0]
    assert row.n == 3
    assert row.mean_mse_difference == pytest.approx(1/60)


def test_active_OLS_rejects_nonfinite_predictors_and_targets():
    from src.research.modeling import fit_least_squares
    with pytest.raises(ValueError,match='NONFINITE'):
        fit_least_squares(np.array([[.1],[np.inf],[.3]]), np.array([.2,.4,.5]))
    with pytest.raises(ValueError,match='NONFINITE'):
        fit_least_squares(np.array([[.1],[.2],[.3]]), np.array([.2,np.inf,.5]))


@pytest.mark.parametrize("late_bounds", [False, True])
def test_pipeline_branch_isolation_and_bounds_availability(monkeypatch, late_bounds):
    from src.research import pipeline
    date = pd.Timestamp("2024-01-02")
    tables = {name: pd.DataFrame(columns=fields) for name, fields in TABLES.items()}
    tables["membership"] = pd.DataFrame({"index": ["SPX", "SPX"], "permno": [1, 2],
        "start": [date, date], "end": [pd.NaT, pd.NaT]})
    tables["caps"] = pd.DataFrame({"permno": [1, 2], "date": [date, date], "dlycap": [1., 1.], "dlyprc": [1., 1.]})
    tables["links"] = pd.DataFrame({"permno": [1, 2], "secid": [11, 12], "score": [1, 1],
        "sdate": [pd.NaT, pd.NaT], "edate": [pd.NaT, pd.NaT]})
    tables["calendar"] = pd.DataFrame({"date": [date]})
    class Store:
        availability = {}
        calendar = pd.DatetimeIndex([date, pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04"), pd.Timestamp("2024-01-05")])
        wide = pd.DataFrame([[.01,.03],[.02,.01],[.03,.02]],index=calendar[1:],columns=[1,2])
        def __init__(self, bundle): pass
        def historical_rho(self, *args): raise DataError("INCOMPLETE_HISTORICAL_MONTHS")
        def grid(self, start, end, ids, index=None, **kwargs):
            if late_bounds and end > date: raise DataError("MISSING_FUTURE_RETURNS")
            if index is not None: raise DataError("MISSING_INDEX_RETURNS")
            return np.array([[.01, .03], [.02, .01], [.03, .02]]), None, pd.date_range("2024-01-03", periods=3)
        def label_available(self, *args): return pd.Timestamp("2024-02-05" if late_bounds else "2024-02-02")
    monkeypatch.setattr(pipeline, "ReturnStore", Store)
    monkeypatch.setattr(pipeline, "package", lambda s, f, c, secid, *args: {"iv": .15 if secid == 108105 else .2})
    cfg = Config(rate_unit="percent", entry_start="2024-01-02", entry_end="2024-01-02", horizons=[30], min_sessions=3,
        basket_fractions=[], basket_weight_thresholds=[])
    bundle = Bundle(tables, {"source": "small numerical fixture"})
    with pytest.raises(DataError, match="RATE_CONVENTION_UNCERTIFIED"):
        pipeline.compute(bundle, cfg)
    result = pipeline.compute(bundle, cfg, asof="2024-02-02" if late_bounds else None, provisional=True)
    full = result["measurements"].query("basket == 'full'").iloc[0]
    if late_bounds:
        assert full.label_status == "MISSING_FUTURE_RETURNS"
        assert "rc_future_lower_bound" not in result["measurements"]
        assert "BOUNDS_NOT_AVAILABLE_ASOF" in set(result["exclusions"].code)
        return
    assert full.label_status == "PASS"
    assert full.mic_label_status == "MISSING_INDEX_RETURNS"
    assert full.rc_past == pytest.approx(-.5)
    assert full.gap == pytest.approx(.625)
    assert result["metadata"]["rate_convention_status"] == "PROVISIONAL"


def test_batching_mixed_missing_exclusion_ids(monkeypatch, tmp_path):
    from src.research import pipeline
    from src.research.batching import compute_to_disk
    dates = pd.to_datetime(["2024-01-02","2024-01-03"])
    tables = {name:pd.DataFrame(columns=fields) for name,fields in TABLES.items()}
    tables["calendar"] = pd.DataFrame({"date":dates})
    tables["membership"] = pd.DataFrame({"index":["SPX","SPX"],"permno":[1,2],"start":[dates[0],dates[0]],"end":[pd.NaT,pd.NaT]})
    tables["caps"] = pd.DataFrame({"permno":[1,2],"date":[dates[0],dates[0]],"dlycap":[1.,1.],"dlyprc":[1.,1.]})
    tables["links"] = pd.DataFrame({"permno":[1,2],"secid":[11,12],"score":[1,1],"sdate":[pd.NaT,pd.NaT],"edate":[pd.NaT,pd.NaT]})
    class Store:
        availability = {}
        def __init__(self,bundle): self.calendar = pd.DatetimeIndex(bundle.calendar.date)
    def get_package(s,f,c,secid,*args):
        if secid == 11: raise DataError("MISSING_OPTION_LEG")
        return {"iv":.2}
    monkeypatch.setattr(pipeline,"ReturnStore",Store)
    monkeypatch.setattr(pipeline,"package",get_package)
    cfg = Config(entry_start="2024-01-02",entry_end="2024-01-03",horizons=[30],
        basket_fractions=[],basket_weight_thresholds=[])
    from src.research.store import BundleWriter
    writer = BundleWriter(tmp_path/'raw', {})
    for name, table in tables.items(): writer.add(name,table)
    compute_to_disk(writer.finish(),cfg,tmp_path,batch_sessions=1,provisional=True)
    exclusions = pd.read_parquet(tmp_path / "exclusions.parquet")
    assert str(exclusions.horizon.dtype) == "Int64"
    assert str(exclusions.permno.dtype) == "Int64"
    assert exclusions.permno.isna().any() and exclusions.permno.notna().any()


@pytest.mark.parametrize("failure,backup_move,after_rename", [
    (OSError,False,False), (KeyboardInterrupt,False,False),
    (KeyboardInterrupt,False,True), (KeyboardInterrupt,True,True),
])
def test_failed_publication_restores_previous_generation(monkeypatch, tmp_path, failure, backup_move, after_rename):
    from pathlib import Path
    from src.research.batching import _publish
    root, stage = tmp_path / "output", tmp_path / "staging"
    root.mkdir()
    stage.mkdir()
    files = ("measurements.parquet","metadata.json","output_manifest.json")
    for name in files:
        (root / name).write_bytes(b"previous complete generation")
        (stage / name).write_bytes(b"new generation")
    (root / "unrelated.txt").write_bytes(b"keep")
    original = Path.replace
    def fail_metadata(path, target):
        inject = path.name == "metadata.json" and (
            path.parent == root if backup_move else path.parent == stage)
        if inject:
            if after_rename:
                original(path,target)
            raise failure("injected publication failure")
        return original(path,target)
    monkeypatch.setattr(Path,"replace",fail_metadata)
    with pytest.raises(failure,match="injected publication failure"):
        _publish(stage,root)
    assert all((root / name).read_bytes()==b"previous complete generation" for name in files)
    assert (root / "unrelated.txt").read_bytes()==b"keep"


@pytest.mark.parametrize("after_rename", [False, True])
def test_bundle_publication_interrupt_preserves_previous_directory(monkeypatch, tmp_path, after_rename):
    from pathlib import Path
    from src.research.store import _publish
    root, stage = tmp_path / "output", tmp_path / "staging"
    for folder, content in ((root,b"previous bundle"),(stage,b"new bundle")):
        (folder / "bundle").mkdir(parents=True)
        (folder / "bundle" / "manifest.json").write_bytes(content)
    (root / ".previous-bundle").mkdir()
    (root / ".previous-bundle" / "valuable.txt").write_bytes(b"legacy recovery")
    original = Path.replace
    def interrupt(path,target):
        if path == stage / "bundle":
            if after_rename: original(path,target)
            raise KeyboardInterrupt("injected bundle interruption")
        return original(path,target)
    monkeypatch.setattr(Path,"replace",interrupt)
    with pytest.raises(KeyboardInterrupt): _publish(stage,root)
    assert (root / "bundle" / "manifest.json").read_bytes() == b"previous bundle"
    assert (root / ".previous-bundle" / "valuable.txt").read_bytes() == b"legacy recovery"


def test_streaming_extract_preserves_legacy_recovery_on_interruption(monkeypatch, tmp_path):
    """One identity and empty market tables exercise publication, not prices."""
    from pathlib import Path
    from src.research.wrds_client import extract
    class MetadataOnlyDB:
        def raw_sql(self, sql, date_cols=None):
            if "dsp500list_v2" in sql:
                return pd.DataFrame({"permno":[1],"start":pd.to_datetime(["2024-01-01"]),"end":[pd.NaT]})
            if "opcrsphist" in sql:
                return pd.DataFrame({"permno":[1],"secid":[11],"score":[1],
                    "sdate":pd.to_datetime(["2024-01-01"]),"edate":[pd.NaT]})
            if "dsf_v2" in sql:
                return pd.DataFrame(columns=["permno","date","dlycap","dlyprc","return","dlyretmissflg","dlyretdurflg","dlydelflg"])
            if "vsurfd" in sql: return pd.DataFrame(columns=TABLES["surface"])
            if "stdopd" in sql: return pd.DataFrame(columns=TABLES["forwards"])
            if "zerocd" in sql: return pd.DataFrame(columns=TABLES["curve"])
            if "secprd" in sql: return pd.DataFrame(columns=["date","return","close"])
            raise AssertionError("unexpected test query")
    root = tmp_path / "extract"
    for folder in ("bundle",".previous-bundle"):
        (root / folder).mkdir(parents=True)
        (root / folder / "valuable.txt").write_bytes(b"previous local input")
    original = Path.replace
    def interrupt(path,target):
        if path.name == "bundle" and path.parent.name.startswith(".extract-"):
            raise KeyboardInterrupt("injected extractor publication interruption")
        return original(path,target)
    monkeypatch.setattr(Path,"replace",interrupt)
    cfg = Config(rate_unit="percent",entry_start="2024-01-02",entry_end="2024-01-02")
    with pytest.raises(DataError,match="RATE_CONVENTION_UNCERTIFIED"):
        extract(MetadataOnlyDB(),cfg,root,progress=lambda *args:None)
    with pytest.raises(KeyboardInterrupt):
        extract(MetadataOnlyDB(),cfg,root,progress=lambda *args:None,provisional=True)
    assert (root / "bundle" / "valuable.txt").read_bytes() == b"previous local input"
    assert (root / ".previous-bundle" / "valuable.txt").read_bytes() == b"previous local input"
    assert list((root / "query_cache").glob("*.parquet"))
