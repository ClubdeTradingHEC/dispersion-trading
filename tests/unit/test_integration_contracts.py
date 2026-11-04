"""Packaging, preserved entry points and strict input contracts."""
import importlib
from pathlib import Path
import json
import pandas as pd
import pytest
from src.research.config import Config
from src.research.inputs import map_secid
from src.research.errors import DataError
from src.research.wrds_client import chunks, periods
from src.research.cli import parser
from src.data.index_weights import _normalize_weights
from src.data.correlation import daily_to_monthly

ROOT=Path(__file__).resolve().parents[2]

def test_wrds_sql_to_dataframe_without_network():
    """Isolate SQL/DataFrame compatibility from WRDS network/authentication."""
    import sqlalchemy as sa
    import wrds

    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1 AS connection_ok").scalar() == 1
            db = wrds.Connection(autoconnect=False)
            db.connection = connection
            result = db.raw_sql("SELECT 1 AS connection_ok")
            pd.testing.assert_frame_equal(result, pd.DataFrame({"connection_ok": [1]}))
    finally:
        engine.dispose()

@pytest.mark.parametrize("module", sorted(["scripts.discovery."+f.stem for f in (ROOT/"scripts/discovery").glob("*.py") if f.stem!="__init__"]+["tests."+f.stem for f in (ROOT/"tests").glob("test_*.py")]+["src.run_dispersion"]))
def test_original_entrypoints_import_without_database_login(module):
    importlib.import_module(module)

@pytest.mark.parametrize("name", ["query_batch_ids","query_batch_days"])
@pytest.mark.parametrize("value", [0,-1,True,1.5])
def test_invalid_query_bounds(name,value):
    with pytest.raises(ValueError): Config(**{name:value}).validate()

def test_date_partition_never_crosses_option_year():
    assert list(periods("2023-12-30","2024-01-03",2)) == [("2023-12-30","2023-12-31",2023),("2024-01-01","2024-01-02",2024),("2024-01-03","2024-01-03",2024)]
    assert list(chunks([3,1,2,2],2)) == ["1,2","3"]

def test_security_identity_ambiguity_is_not_option_availability():
    links=pd.DataFrame({"permno":[1,1],"secid":[2,3],"score":[1,1],"sdate":[pd.NaT,pd.NaT],"edate":[pd.NaT,pd.NaT]})
    with pytest.raises(DataError,match="AMBIGUOUS_SECID_LINK"):
        map_secid(links,1,pd.Timestamp("2024-01-02"))

def test_kevin_weights_renormalize_available_inputs():
    result=_normalize_weights(pd.DataFrame({"price":[100,float('nan')]}),"price","missing price")
    assert len(result)==1 and result.weight.iloc[0]==pytest.approx(1.)

def test_kevin_partial_month_is_compounded():
    result=daily_to_monthly(pd.DataFrame({"date":pd.to_datetime(["2024-01-02"]),"return":[0.01]}))
    assert result["return"].iloc[0]==pytest.approx(.01)

def test_delivery_has_no_simulation_command():
    with pytest.raises(SystemExit): parser().parse_args(["synthetic"])

def test_all_original_scripts_and_manual_checks_preserved():
    assert len(list((ROOT/"scripts/discovery").glob("*.py"))) == 14
    assert len(list((ROOT/"tests").glob("test_*.py"))) == 7
