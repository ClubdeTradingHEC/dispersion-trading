"""Hand-checkable regression and timing examples; no fake market histories."""
import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from src.research.modeling import fit_least_squares
from src.research.modeling import hac_covariance,nonoverlap,wald,train_for


def test_shared_solver_matches_independent_statsmodels_and_raw_prediction():
    x=np.array([[1.,2.],[2.,0.],[3.,4.],[4.,1.],[5.,3.],[6.,2.]])
    y=np.array([2.,3.,5.,4.,7.,8.])
    result=fit_least_squares(x,y)
    expected=sm.OLS(y,sm.add_constant(x)).fit()
    assert result['coefficients']==pytest.approx(expected.params)
    exact=fit_least_squares(x[:3],y[:3])
    assert sm.add_constant(x[:3])@exact['coefficients']==pytest.approx(y[:3])


def test_hac_preserves_real_missing_session_distance():
    calendar=pd.bdate_range('2024-01-02',periods=8)
    dates=calendar[[0,1,5,6,7]]
    X=np.column_stack([np.ones(5),[1,3,2,4,6]])
    e=np.array([1.,-.5,2.,-1.,.3])
    score=np.zeros((8,2));score[[0,1,5,6,7]]=X*e[:,None]
    meat=score.T@score
    for lag in [1,2]:
        cross=sum(np.outer(score[t],score[t-lag]) for t in range(lag,8))
        meat+=(1-lag/3)*(cross+cross.T)
    bread=np.linalg.inv(X.T@X)
    expected=bread@meat@bread*5/3
    assert hac_covariance(X,e,dates,calendar,lag=2)==pytest.approx(expected)


def test_nonoverlap_uses_actual_endpoints_and_never_compresses_missing_dates():
    d=pd.DataFrame({'date':pd.to_datetime(['2024-01-02','2024-01-31','2024-02-01','2024-02-02']),
                    'label_end':pd.to_datetime(['2024-02-01','2024-03-01','2024-03-02','2024-03-03'])})
    assert nonoverlap(d).index.tolist()==[0,3]


def test_joint_wald_known_arithmetic():
    result=wald(np.array([7.,2.,3.]),np.diag([1.,4.,9.]),[1,2])
    assert result['statistic']==pytest.approx(2.)
    assert result['pvalue']==pytest.approx(np.exp(-1))


def test_training_outcomes_must_be_available_and_B_mask_does_not_change_A():
    d=pd.DataFrame({'date':pd.to_datetime(['2020-01-02','2020-02-03','2020-03-02']),
                    'label_available_at':pd.to_datetime(['2020-02-04','2020-03-04','2020-04-02']),
                    'complete_features':True,'eligible_B':[True,False,True]})
    cfg={'training_start':'2020-01-01'}
    assert train_for(d,'2020-03-31','A',cfg).index.tolist()==[0,1]
    assert train_for(d,'2020-03-31','B',cfg).index.tolist()==[0]
