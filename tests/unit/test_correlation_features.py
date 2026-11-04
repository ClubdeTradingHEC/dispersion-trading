"""Hand-checkable numerical matrices, not generated market histories."""
import numpy as np
import pandas as pd
import pytest

from src.research.correlation_features import exponential_correlation,downside_comovement,entry_features


X=np.array([[-.02,.01,-.01],[.01,-.03,-.02],[-.01,-.02,.04],[.03,.02,.01]])
A=np.array([.5,.3,.2])


def test_exponential_feature_matches_independent_weighted_covariance_pairs():
    weights=2.**(-np.arange(3,-1,-1)/2);weights/=weights.sum()
    covariance=np.cov(X,rowvar=False,aweights=weights,bias=True)
    expected=sum(A[i]*A[j]*covariance[i,j]/np.sqrt(covariance[i,i]*covariance[j,j]) for i in range(3) for j in range(i+1,3))/sum(A[i]*A[j] for i in range(3) for j in range(i+1,3))
    assert exponential_correlation(X,A,2)==pytest.approx(expected,abs=1e-14)


def test_downside_is_uncentered_negative_comovement_not_pearson():
    negative=np.minimum(X,0)
    expected=sum(A[i]*A[j]*sum(negative[:,i]*negative[:,j])/np.sqrt(sum(negative[:,i]**2)*sum(negative[:,j]**2)) for i in range(3) for j in range(i+1,3))/sum(A[i]*A[j] for i in range(3) for j in range(i+1,3))
    assert downside_comovement(X,A,1)==pytest.approx(expected,abs=1e-14)
    # Multiplying stock return units by positive constants preserves dependence.
    assert downside_comovement(X*np.array([2,3,5]),A,1)==pytest.approx(expected)


def test_missing_returns_zero_variance_and_sparse_negative_samples_fail():
    missing=X.copy();missing[0,0]=np.nan
    with pytest.raises(ValueError,match='HISTORY'):exponential_correlation(missing,A,2)
    with pytest.raises(ValueError,match='ZERO_VARIANCE'):exponential_correlation(np.ones((4,3)),A,2)
    with pytest.raises(ValueError,match='NEGATIVE'):downside_comovement(X,A,3)
    with pytest.raises(ValueError,match='WEIGHTS'):downside_comovement(X,[1,0,2],1)


def test_entry_prefix_ignores_all_later_return_values():
    dates=pd.bdate_range('2024-01-02',periods=7)
    # Extra rows are deliberately extreme numerical values to detect look-ahead.
    data=np.vstack([X[0],X,[[100,200,300],[400,500,600]]])
    frame=pd.DataFrame(data,index=dates,columns=[1,2,3])
    cfg={'slow_history_sessions':4,'slow_half_life_sessions':2,'downside_sessions':4,'minimum_negative_sessions_per_stock':1}
    first=entry_features(frame,dates,dates[4],[1,2,3],A,cfg)
    frame.loc[dates[5]:]=999.
    second=entry_features(frame,dates,dates[4],[1,2,3],A,cfg)
    assert first==second
    assert first['feature_last_session']==dates[4]


def test_frozen_basket_and_corresponding_weights_are_permutation_invariant():
    order=[2,0,1]
    assert exponential_correlation(X[:,order],A[order],2)==pytest.approx(exponential_correlation(X,A,2))
    assert downside_comovement(X[:,order],A[order],1)==pytest.approx(downside_comovement(X,A,1))
