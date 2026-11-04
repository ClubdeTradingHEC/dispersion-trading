"""Small timing/algebra fixtures, not generated market datasets."""
import numpy as np
import pandas as pd
import pytest

from src.research.config import Config
from src.research.statistics import training_mask,longest_run,holm


def test_crash_mask_includes_entry_and_thirtieth_day_but_not_day_31():
    dates=pd.to_datetime(['2020-02-14','2020-02-15','2020-03-16','2020-03-17'])
    result=training_mask(dates,['2020-03-16'],30)
    assert result.eligible_B.tolist()==[True,False,False,True]
    assert result.excluded_crash_dates.iloc[0]==''
    assert result.excluded_crash_dates.iloc[1]=='2020-03-16'


def test_training_exclusion_preserves_test_dates_and_frozen_future_independence():
    from src.research.modeling import forecast_block
    dates = pd.bdate_range('2024-01-02', periods=9)
    ic = np.array([.1,.2,.4,.3,.7,.5,.6,.8,.9])
    past = np.array([.3,.4,.1,.6,.5,.8,.2,.7,.4])
    frame = pd.DataFrame({'date':dates,'ic':ic,'rc_past':past,'rc_future':.2+.3*ic+.4*past,
        'label_end':dates+pd.Timedelta(days=1),'label_available_at':dates+pd.offsets.BDay(1),
        'complete_features':True,'eligible_B':[False,*([True]*8)]})
    cfg = {'training_start':'2024-01-02','training_end':'2024-01-09','minimum_training_rows':3}
    kwargs = dict(cutoff='2024-01-09',first='2024-01-10',last='2024-01-12',features=['ic','rc_past'],cfg=cfg)
    fitA, trainA, predA = forecast_block(frame,model='A',**kwargs)
    fitB, trainB, predB = forecast_block(frame,model='B',**kwargs)
    assert len(trainA) == len(trainB)+1
    assert predA.date.tolist() == predB.date.tolist() == list(dates[-3:])
    assert np.allclose(predB.prediction,.2+.3*ic[-3:]+.4*past[-3:])
    assert trainB.label_available_at.max() <= pd.Timestamp(cfg['training_end'])
    changed = frame.copy()
    changed.loc[changed.date > pd.Timestamp(cfg['training_end']),'rc_future'] = 999.
    altered, _, pred2 = forecast_block(changed,model='B',**kwargs)
    assert np.array_equal(fitB['coefficients'],altered['coefficients'])
    pd.testing.assert_frame_equal(predB[['date','prediction']],pred2[['date','prediction']])


def test_time_series_diagnostics_do_not_close_missing_calendar_gaps():
    calendar=pd.bdate_range('2024-01-02',periods=8)
    frame=pd.DataFrame({'date':calendar[[0,1,4,5,6]],'x':[1,2,3,4,5]})
    result=longest_run(frame,calendar)
    assert result.date.tolist()==list(calendar[4:7])


def test_multiple_comparison_adjustment_preserves_missing_and_original_order():
    adjusted=holm([.01,.04,.03,np.nan])
    assert adjusted[:3]==pytest.approx([.03,.06,.06])
    assert np.isnan(adjusted[3])


def test_batch_numeric_promotion_and_verified_checkpoint_reuse(monkeypatch,tmp_path):
    from src.research import batching
    class MetadataOnly:
        metadata={'synthetic':True}
        manifest={'fixture':'metadata counters only, not financial observations'}
        calendar=pd.DataFrame({'date':pd.to_datetime(['2024-01-02','2024-01-03'])})
        def validate(self):return self
        def window(self,*args):return self
    calls=[]
    def calculate(bundle,cfg,**kwargs):
        calls.append(cfg.entry_start)
        counters=[21] if len(calls)==1 else [20.,np.nan]
        return {'measurements':pd.DataFrame({'label_sessions':counters}),
                'exclusions':pd.DataFrame(),'constituents':pd.DataFrame(),'packages':pd.DataFrame(),
                'metadata':{'elapsed_seconds':0.,'code_sha256':{},'runtime_versions':{}}}
    monkeypatch.setattr(batching,'compute',calculate)
    cfg=Config(entry_start='2024-01-02',entry_end='2024-01-03',horizons=[30])
    output=tmp_path/'published';cache=tmp_path/'checkpoints'
    batching.compute_to_disk(MetadataOnly(),cfg,output,batch_sessions=1,checkpoint_root=cache)
    frame=pd.read_parquet(output/'measurements.parquet')
    assert frame.label_sessions.iloc[:2].tolist()==[21.,20.]
    assert pd.isna(frame.label_sessions.iloc[2])
    result=batching.compute_to_disk(MetadataOnly(),cfg,output,batch_sessions=1,checkpoint_root=cache)
    assert len(calls)==2
    assert all(c['checkpoint_reused'] for c in result['chunks'])
