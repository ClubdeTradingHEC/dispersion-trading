"""Fresh-checkout boundaries and arithmetic export checks; no live data access."""
from pathlib import Path
import importlib.util
import pandas as pd
import pytest
from src.research.cli import main
from src.research.config import Config
from src.research.inputs import sessions
from src.research.reproduction import gaps, membership


# A full membership request must be explicitly budgeted before any connection.
def test_membership_budget_precedes_login(monkeypatch):
    from src.research import wrds_client
    def forbidden():
        raise AssertionError('unexpected WRDS connection')
    monkeypatch.setattr(wrds_client, 'connect', forbidden)
    assert main(['membership','--config','configs/measurement.json']) == 2


# Kevin's discovery API accepts the OptionMetrics ticker, while CSVs use DJIA.
def test_membership_uses_configured_vendor_ticker(monkeypatch,tmp_path):
    from src.data import compustat_membership
    seen=[]
    def resolve(db,index,date,verbose=False):
        seen.append(index)
        data=pd.DataFrame({'permno':[1,2]})
        data.attrs['membership_coverage']={'expected':3,'found':2,'missing':1}
        return data
    monkeypatch.setattr(compustat_membership,'get_compustat_index_constituents',resolve)
    cfg=Config.read('configs/measurement.json')
    cfg.entry_start=cfg.entry_end='2024-07-01'
    target=tmp_path/'membership.csv'
    membership(None,cfg,target)
    assert seen==['DJX']
    assert pd.read_csv(target)['index'].eq('DJIA').all()
    assert pd.read_csv(target.with_suffix('.coverage.csv')).missing.tolist()==[1]


# Check the actual export contract using small declared correlation numbers.
def test_gap_export_schema_forward_alignment_and_duplicates(tmp_path):
    cfg=Config.read('configs/spx.json')
    dates=sessions('2025-01-02','2025-01-31')[:12]
    panel=pd.DataFrame({'date':dates,'index':'SPX','horizon':30,'basket':'reference_option_feasible',
        'ic_status':'PASS','label_status':'PASS','ic':[.30,.32,.31,.29]*3,'rc_future':.25,
        'label_end':dates+pd.Timedelta(days=30),'label_first_session':dates+pd.Timedelta(days=1),
        'label_last_session':dates+pd.Timedelta(days=29),'label_available_at':dates+pd.Timedelta(days=32)})
    panel.to_parquet(tmp_path/'measurements.parquet',index=False)
    cfg.bootstrap_repetitions=19
    result=gaps(tmp_path,cfg,tmp_path/'exports',years=(1,))
    assert result['status']=='PASS'
    read=pd.read_csv(tmp_path/'exports/SPX_IC_RC_1years.csv')
    assert list(read)==['date_of_IC','IC','matched_date_of_RC','RC']
    assert len(read)==12 and read.RC.eq(.25).all()
    pd.concat([panel,panel.iloc[:1]]).to_parquet(tmp_path/'measurements.parquet',index=False)
    with pytest.raises(ValueError,match='DUPLICATE_ENTRY_DATE'):
        gaps(tmp_path,cfg,tmp_path/'bad',years=(1,))


# A source ZIP must not need Git metadata or accidentally copy local outputs.
def test_source_export_selection_excludes_generated_material(tmp_path):
    spec=importlib.util.spec_from_file_location('export_source',Path('scripts/export_source.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for text in ['src/research/a.py','src/research/__pycache__/a.pyc','docs/RESULTS.md',
                 'data/out.json','important_data/market.parquet','.venv/secret.py','README.md']:
        p=tmp_path/text;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
    assert {p.as_posix() for p in module.source_files(tmp_path)}=={'src/research/a.py','docs/RESULTS.md','README.md'}
