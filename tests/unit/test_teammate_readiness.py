"""Regressions for failures reproduced during the teammate-facing final review."""
from pathlib import Path
import json
import sys
import pandas as pd
import numpy as np
import pytest
from tests.unit.test_team_integration import returns
from src.events.analysis import basket_correlation,vix_overlay
from src.events.cli import main


# Whole-session gaps must not shift a declared future or historical window.
def test_entire_missing_session_remains_in_window(returns):
    raw=returns.loc[returns.date.ne(pd.Timestamp('2024-01-04'))]
    row=basket_correlation(raw,3).set_index('date').loc['2024-01-05']
    assert pd.isna(row.rc_basket) and row.n_stocks==0
    corr=pd.Series(.3,index=pd.to_datetime(['2024-01-02']))
    vix=pd.Series(20.,index=corr.index)
    assert pd.isna(vix_overlay(corr,raw,vix,3).fwd_realized_vol.iloc[0])


def test_mixed_index_panel_is_not_treated_as_one_basket(returns):
    returns['index']=np.where(returns.date.le('2024-01-05'),'SPX','DJIA')
    with pytest.raises(ValueError,match='one index'):
        basket_correlation(returns,3)


@pytest.mark.parametrize('change,message',[
    ('holiday','non-exchange'),('identifier','positive integer'),('weight_unit','weights exceed one')])
def test_invalid_session_identifier_or_weight_units_rejected(returns,change,message):
    if change=='holiday':returns.loc[returns.date.eq('2024-01-02'),'date']=pd.Timestamp('2024-07-04')
    elif change=='identifier':
        returns['permno']=returns.permno.astype(float)
        returns.loc[0,'permno']=1.5
    else:returns['weight']*=100
    with pytest.raises(ValueError,match=message):
        basket_correlation(returns,3)


# Publication failures must preserve every previous table and its provenance receipt.
def test_chart_failure_preserves_previous_complete_outputs(returns,tmp_path,monkeypatch):
    source=tmp_path/'returns.csv';returns.to_csv(source,index=False)
    output=tmp_path/'run'
    assert main(['basket','--returns',str(source),'--window','4','--output',str(output),'--no-plots'])==0
    previous={p.name:p.read_bytes() for p in output.iterdir()}
    def fail(*a,**kw):raise OSError('deliberate chart failure')
    monkeypatch.setattr('src.events.cli.basket_plots',fail)
    assert main(['basket','--returns',str(source),'--window','3','--output',str(output)])==2
    assert {p.name:p.read_bytes() for p in output.iterdir()}==previous


def test_successful_rerun_removes_stale_owned_charts(returns,tmp_path,monkeypatch):
    source=tmp_path/'returns.csv';returns.to_csv(source,index=False)
    output=tmp_path/'run'
    monkeypatch.setattr('src.events.cli.basket_plots',lambda frame,events,folder:(folder/'basket_full.png').write_bytes(b'plot fixture'))
    assert main(['basket','--returns',str(source),'--window','4','--output',str(output)])==0
    assert (output/'basket_full.png').is_file()
    assert main(['basket','--returns',str(source),'--window','3','--output',str(output),'--no-plots'])==0
    assert not (output/'basket_full.png').exists()
    receipt=json.loads((output/'run.json').read_text(encoding='utf-8'))
    assert receipt['arguments']['window']==3 and receipt['inputs']['returns']['sha256']


def test_output_cannot_replace_inputs_or_unrelated_files(returns,tmp_path):
    source=tmp_path/'returns.csv';returns.to_csv(source,index=False)
    before=source.read_bytes()
    assert main(['basket','--returns',str(source),'--window','4','--output',str(tmp_path),'--no-plots'])==2
    assert source.read_bytes()==before
    output=tmp_path/'notes';output.mkdir()
    (output/'README.md').write_text('keep teammate notes')
    assert main(['basket','--returns',str(source),'--window','4','--output',str(output),'--no-plots'])==2
    assert (output/'README.md').read_text()=='keep teammate notes'


# The original filenames and headers are a compatibility contract, not just import paths.
def test_original_script_producer_consumer_chain(returns,tmp_path,monkeypatch):
    from src.events.legacy import launch
    monkeypatch.chdir(tmp_path)
    returns.to_csv('spx_returns_weights_2021_2025.csv',index=False)
    events=pd.DataFrame({'date':pd.to_datetime(['2024-01-05']),
        'trading_date':pd.to_datetime(['2024-01-05']),'event_type':['FOMC'],'description':['Arithmetic fixture']})
    events.to_csv('macro_events.csv',index=False)
    monkeypatch.setattr(sys,'argv',['basket.py','--window','4','--no-plots'])
    assert launch('basket')==0
    old=pd.read_csv('basket_correlation_v2_2021_2025.csv')
    assert list(old)==['date','rc_basket','rc_equal_weight','n_stocks','n_excluded','events','event_description']
    assert Path('basket_correlation_2021_2025.csv').read_bytes()==Path('basket_correlation_v2_2021_2025.csv').read_bytes()
    monkeypatch.setattr(sys,'argv',['study.py'])
    assert launch('study')==0
    assert 'Groupe' in pd.read_csv('event_study_2021_2025.csv')
    assert pd.ExcelFile('event_study_2021_2025.xlsx').sheet_names==['par type','mouvements larges','détail']
    vix=pd.DataFrame({'observation_date':sorted(returns.date.unique()),'VIXCLS':20.})
    vix.to_csv('VIXCLS.csv',index=False)
    monkeypatch.setattr(sys,'argv',['vix.py','--no-plots'])
    assert launch('vix')==0 and Path('vix_overlay_2021_2025.csv').is_file()
    assert list(pd.read_csv('vix_overlay_2021_2025.csv'))==['date','rc_basket','vix','fwd_realized_vol','realized_above_vix']


# The preserved cost script is a report; the new strict wrapper is automation-safe.
@pytest.mark.parametrize('flags,code',[([True],0),([True,False],1),([],1)])
def test_strict_cost_checker_returns_meaningful_exit(monkeypatch,flags,code):
    from src.backtest import cli
    monkeypatch.setattr(cli,'validate_costs',lambda path:(pd.DataFrame({'passes_qa':flags}),None))
    assert cli.main(['validate','--input','unused.csv'])==code


def test_ndx_discovery_never_guesses_nonexistent_columns(monkeypatch):
    from tests import test_ndx_membership_sources as ndx
    class DB:
        closed=False
        def describe_table(self,library,table):
            columns=['gvkeyx','from','thru'] if table=='names_ix_cst' else ['gvkey','company']
            return pd.DataFrame({'name':columns})
        def raw_sql(self,sql):
            if 'WHERE' in sql:
                assert 'comp.names_ix_cst' in sql and '"from"' in sql and 'LIMIT 200' in sql
            return pd.DataFrame()
        def close(self):self.closed=True
    db=DB();monkeypatch.setattr(ndx,'get_wrds_connection',lambda:db)
    results=ndx.main()
    assert db.closed
    assert sum(row['status']=='SKIP_NO_GVKEYX' for row in results)==3
    assert next(r for r in results if r['table']=='names_ix_cst')['status']=='PASS'


def test_fred_network_error_does_not_expose_api_key(monkeypatch,tmp_path):
    import requests
    from src.events.macro import macro_events
    monkeypatch.setenv('FRED_API_KEY','private-test-value')
    def fail(*a,**kw):raise requests.Timeout('url?api_key=private-test-value')
    monkeypatch.setattr(requests,'get',fail)
    config=Path(__file__).resolve().parents[2]/'configs/events.json'
    with pytest.raises(ValueError) as caught:
        macro_events('2024-01-01','2024-01-31',str(config))
    assert 'private-test-value' not in str(caught.value)


def test_original_basket_extra_shocks_preserved_without_macro_input():
    from src.events.macro import legacy_shocks
    config=Path(__file__).resolve().parents[2]/'configs/events.json'
    events=legacy_shocks(None,config)
    assert len(events)==5
    assert {'2024-07-15','2024-07-19','2024-07-22'} <= set(events.trading_date.dt.strftime('%Y-%m-%d'))


def test_offline_verification_finds_checkout_after_noneditable_install(tmp_path,monkeypatch):
    from src.research import cli
    checkout=Path(__file__).resolve().parents[2]
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(cli,'__file__',str(tmp_path/'site-packages/src/research/cli.py'))
    def run(command,**kw):
        assert Path(kw['cwd'])==checkout
        assert Path(command[3])==checkout/'tests/unit'
        output=next(a.split('=',1)[1] for a in command if a.startswith('--junitxml='))
        Path(output).write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"/></testsuites>')
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0,stdout='one test executed',stderr='')
    monkeypatch.setattr(cli.subprocess,'run',run)
    assert cli.offline_tests(tmp_path/'verification')['tests']==1
