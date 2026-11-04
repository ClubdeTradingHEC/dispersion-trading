"""Preparation boundaries and independent arithmetic; no empirical study."""
from dataclasses import replace
import ast
import inspect
import re
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from src.research.config import Config
from src.research.errors import DataError
from src.research.measurement import pair_rc
from src.research.inputs import Bundle, TABLES


def test_rc_centering_scale_and_ddof_cancel():
    x=np.array([[1,2,4],[2,1,3],[4,5,2],[3,4,1]],float)
    a=np.array([.1,.2,.3])
    centered=x-x.mean(axis=0)
    expected=sum(a[i]*a[j]*np.corrcoef(x[:,i],x[:,j])[0,1] for i in range(3) for j in range(i+1,3))/sum(a[i]*a[j] for i in range(3) for j in range(i+1,3))
    for ddof in (0,1):
        z=centered/x.std(axis=0,ddof=ddof)
        identity=(np.var(z@a,ddof=ddof)-a@a)/(a.sum()**2-a@a)
        assert identity==pytest.approx(expected,abs=1e-12)
    assert pair_rc(x*np.array([10,2,.3])+[100,-5,9],a)==pytest.approx(expected,abs=1e-12)
    assert pair_rc(x,a)==pytest.approx(expected,abs=1e-12)


def test_unequal_pair_samples_are_different_estimand():
    x=np.array([[1,1,np.nan],[2,3,1],[3,2,4],[4,np.nan,2]],float)
    # Pairwise deletion and complete-case deletion use different observations.
    pairwise=pd.DataFrame(x).corr().to_numpy()
    complete=np.corrcoef(x[np.isfinite(x).all(axis=1)],rowvar=False)
    assert not np.allclose(pairwise,complete)
    with pytest.raises(DataError,match='INCOMPLETE_PAIR_GRID'): pair_rc(x,[.1,.2,.3])
    with pytest.raises(DataError,match='ZERO_VARIANCE'): pair_rc([[1,1],[1,2],[1,3]],[.1,.2])


def test_config_observation_bounds():
    cfg=Config(entry_start='2024-01-01',entry_end='2025-06-30',observation_end='2025-05-30').validate()
    dates=pd.to_datetime(['2024-05-31','2024-06-03','2025-05-30','2025-06-02'])
    assert cfg.entry_grid(dates).tolist()==list(dates[:3])
    with pytest.raises(ValueError):replace(cfg,observation_end='2023-12-31').validate()


@pytest.mark.parametrize('horizon',[30,60,91])
def test_cached_future_observations_cannot_cross_cutoff(monkeypatch,horizon):
    from src.research import pipeline
    date=pd.Timestamp('2024-01-02')
    tables={name:pd.DataFrame(columns=fields) for name,fields in TABLES.items()}
    tables['membership']=pd.DataFrame({'index':['SPX']*2,'permno':[1,2],'start':[date]*2,'end':[pd.NaT]*2})
    tables['caps']=pd.DataFrame({'permno':[1,2],'date':[date]*2,'dlycap':[1.,1.],'dlyprc':[1.,1.]})
    tables['links']=pd.DataFrame({'permno':[1,2],'secid':[11,12],'score':[1,1],'sdate':[pd.NaT]*2,'edate':[pd.NaT]*2})
    tables['calendar']=pd.DataFrame({'date':[date]})
    class Store:
        calendar=pd.DatetimeIndex([date]);availability={}
        def __init__(self,b): pass
        def historical_rho(self,*args): return np.array([.5,.5])
        def grid(self,start,end,*args,**kwargs):
            assert end<=date, 'future data read despite cutoff'
            raise DataError('INSUFFICIENT_PAIR_OVERLAP')
    monkeypatch.setattr(pipeline,'ReturnStore',Store)
    monkeypatch.setattr(pipeline,'package',lambda s,f,c,secid,*args:{'iv':.15 if secid==108105 else .2})
    cfg=Config(entry_start='2024-01-02',entry_end='2024-01-02',observation_end='2024-01-05',horizons=[horizon],basket_fractions=[],basket_weight_thresholds=[])
    out=pipeline.compute(Bundle(tables,{}),cfg,provisional=True)['measurements']
    assert out.ic.notna().all()
    assert (out.label_status=='LABEL_BEYOND_OBSERVATION_CUTOFF').all()
    assert (out.mic_label_status=='LABEL_BEYOND_OBSERVATION_CUTOFF').all()
    assert 'gap' not in out or out.gap.isna().all()


def test_verification_does_not_dispatch_research():
    from src.research import cli
    tree=ast.parse(inspect.getsource(cli.main))
    branch=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=="args.command == 'verify'")
    # The verify branch's own body must not run research; subsequent elif arms are separate.
    calls=[n.func.id for statement in branch.body for n in ast.walk(statement) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    assert 'research' not in calls


@pytest.mark.parametrize('mapped,labels,code', [([1,None],[1,2],None),([1,1],[1,2],'AMBIGUOUS_HISTORICAL_MAPPING'),([1,1.5],[1,2],'AMBIGUOUS_HISTORICAL_MAPPING'),([1,2],[1],None),([1,2],[1,2],None)])
def test_compustat_unresolved_member_is_not_silently_dropped(monkeypatch,mapped,labels,code):
    from src.data import compustat_membership as cm
    monkeypatch.setattr(cm,'discover_compustat_index',lambda **k:{'gvkeyx':'1'})
    monkeypatch.setattr(cm,'resolve_compustat_tickers_to_permnos',lambda **k:pd.DataFrame({'compustat_ticker':['AAA','BBB'],'ticker':['AAA','BBB'],'permno':mapped}))
    monkeypatch.setattr(cm,'resolve_cusips_to_permnos',lambda **k:pd.DataFrame())
    monkeypatch.setattr(cm,'attach_crsp_tickers',lambda **k:pd.DataFrame({'permno':labels,'ticker':['AAA','BBB'][:len(labels)]}))
    class DB:
        def raw_sql(self,sql):
            if 'names_ix_cst' in sql:
                return pd.DataFrame({'gvkey':['1','2'],'iid':['01','01'],'cusip':['111111111','222222222']})
            return pd.DataFrame({'gvkey':['1','2'],'iid':['01','01'],'tic':['AAA','BBB']})
    if code:
        with pytest.raises(ValueError,match=code): cm.get_compustat_index_constituents(DB(),'DJIA','2024-01-02')
    else:
        expected=[p for p in mapped if p is not None and p in labels]
        from contextlib import nullcontext
        with pytest.warns(RuntimeWarning,match='1 not found') if len(expected)<2 else nullcontext():
            result=cm.get_compustat_index_constituents(DB(),'DJIA','2024-01-02')
        assert result.permno.tolist()==expected
        assert result.attrs['membership_coverage']=={'expected':2,'found':len(expected),'missing':2-len(expected)}


@pytest.mark.parametrize('raw,expected',[(4,.04),(.04,.04),(.2,.2),(1,1),(1.01,.0101)])
def test_user_selected_kevin_rate_rule(raw,expected):
    from src.data.optionmetrics_iv import _normalize_rate
    from src.data.rates import rate_convert
    assert _normalize_rate(raw)==pytest.approx(expected)
    assert rate_convert(raw,Config().rate_unit)==pytest.approx(expected)
    Config().require_rate_certification()


def test_kevin_defaults_and_dynamic_cutoff():
    from src.data.miv_history import compute_miv_history,run_miv_history
    assert inspect.signature(compute_miv_history).parameters['engine'].default=='diagnostic'
    assert inspect.signature(run_miv_history).parameters['engine'].default=='diagnostic'
    assert Config().quarantine_repricing is False
    cfg=Config.read('configs/measurement.json')
    assert cfg.observation_end=='2026-12-31' and cfg.rate_unit=='kevin'
    assert replace(cfg,observation_end=None).validate().observation_end is None


def test_extraction_bounds_do_not_download_future_tail(tmp_path):
    from src.research.wrds_client import extract
    sqls=[]
    class DB:
        def raw_sql(self,sql,date_cols=None):
            sqls.append(sql)
            if 'dsp500list_v2' in sql:return pd.DataFrame({'permno':[1],'start':pd.to_datetime(['2024-01-01']),'end':[pd.NaT]})
            if 'opcrsphist' in sql:return pd.DataFrame({'permno':[1],'secid':[11],'score':[1],'sdate':[pd.NaT],'edate':[pd.NaT]})
            columns=(["permno","date","dlycap","dlyprc","return","dlyretmissflg","dlyretdurflg","dlydelflg"] if 'dsf_v2' in sql else
                     TABLES['surface'] if 'vsurfd' in sql else TABLES['forwards'] if 'stdopd' in sql else TABLES['curve'] if 'zerocd' in sql else ['date','return','close'])
            return pd.DataFrame(columns=columns)
    cfg=Config(entry_start='2024-01-02',entry_end='2024-01-10',observation_end='2024-01-05')
    bundle=extract(DB(),cfg,tmp_path,provisional=True)
    assert bundle.calendar.date.max()<=pd.Timestamp('2024-01-05')
    for sql in sqls:
        for _,upper in re.findall(r"BETWEEN '([0-9-]+)' AND '([0-9-]+)'",sql): assert upper<='2024-01-05'


def test_forecast_blocks_reject_overlapping_training_information():
    from src.research.modeling import forecast_block
    with pytest.raises(ValueError,match='TRAINING_OVERLAPS'):
        forecast_block(pd.DataFrame(), '2024-01-08', '2024-01-08', '2024-02-01','A',['ic'],{})


def test_old_panel_cannot_bypass_observation_cutoff(tmp_path):
    from src.research.reporting import research
    panel=pd.DataFrame({'label_status':['PASS'],'mic_label_status':['PASS'],'label_end':pd.to_datetime(['2025-06-02'])})
    with pytest.raises(DataError,match='PANEL_EXCEEDS_OBSERVATION_CUTOFF'):
        research(panel,[],Config(observation_end='2025-05-30'),tmp_path/'no_research')
    assert not (tmp_path/'no_research').exists()
