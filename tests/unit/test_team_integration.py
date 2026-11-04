"""Hand-checkable financial/timing checks for the newly integrated team workflows."""
import importlib
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.events.analysis import basket_correlation, market_proxy, event_study, vix_overlay
from src.events.macro import align_events
from src.backtest.transaction_costs import (option_execution_cost,stock_hedge_cost,
    futures_hedge_cost,total_execution_cost,FuturesCostConfig)
from src.data.option_quotes import build_straddle_pairs,select_straddle_pair,calculate_straddle_cost


# Tiny declared arithmetic fixtures are not a simulated market or research evidence.
@pytest.fixture
def returns():
    dates=pd.bdate_range('2024-01-02',periods=8)
    x=np.array([[1,2,-1],[-1,0,2],[2,-1,1],[0,1,-2],[1,-2,0],[-2,1,1],[0,-1,2],[2,2,-1]])/100
    return pd.DataFrame([{'date':d,'permno':j+1,'daily_return':x[i,j],'weight':[.5,.3,.2][j]}
                         for i,d in enumerate(dates) for j in range(3)])


def test_trailing_team_rc_matches_explicit_matrix(returns):
    result=basket_correlation(returns,4)
    x=returns.pivot(index='date',columns='permno',values='daily_return')
    w=np.array([.5,.3,.2])
    for row in result.itertuples():
        r=x.loc[:row.date].tail(4).corr().to_numpy()
        expected=sum(w[i]*w[j]*r[i,j] for i in range(3) for j in range(i+1,3))/sum(w[i]*w[j] for i in range(3) for j in range(i+1,3))
        assert row.rc_basket==pytest.approx(expected,abs=1e-14)
        assert row.rc_equal_weight==pytest.approx((r.sum()-3)/6,abs=1e-14)


def test_missing_stock_keeps_trailing_basket_and_reports(returns):
    returns.loc[0,'daily_return']=np.nan
    row=basket_correlation(returns,4).iloc[0]
    assert row.n_stocks==2 and row.n_excluded==1
    assert row.available_entry_weight==pytest.approx(.5)
    assert np.isfinite(row.rc_basket)


def test_duplicate_panel_rejected(returns):
    with pytest.raises(ValueError,match='duplicate'):
        basket_correlation(pd.concat([returns,returns.iloc[:1]]),4)


def test_forward_volatility_excludes_entry_and_unmatured_tail(returns):
    dates=pd.DatetimeIndex(returns.date.unique())
    corr=pd.Series(.4,index=dates)
    vix=pd.Series([20.],index=[dates[0]-pd.Timedelta(days=1)])
    got=vix_overlay(corr,returns,vix,horizon=3)
    idx=market_proxy(returns).index_return
    assert got.fwd_realized_vol.iloc[0]==pytest.approx(idx.iloc[1:4].std()*np.sqrt(252)*100)
    assert got.fwd_realized_vol.tail(3).isna().all()
    assert got.vix.eq(20).all()


def test_missing_return_does_not_turn_into_zero_market_return(returns):
    day=returns.date.iloc[0];returns.loc[0,'daily_return']=np.nan
    assert np.isnan(market_proxy(returns).loc[day,'index_return'])


def test_events_roll_over_holiday_and_after_close():
    events=pd.DataFrame({'date':['2024-07-04','2024-07-05','2024-07-06'],
                         'event_type':['FOMC','SHOCK','SHOCK']})
    assert align_events(events,['2024-07-05']).trading_date.dt.strftime('%Y-%m-%d').tolist()==['2024-07-05','2024-07-08','2024-07-08']


def test_event_change_alignment_and_empty_groups(returns):
    days=pd.DatetimeIndex(returns.date.unique())
    corr=pd.Series(np.arange(len(days))/10,index=days)
    events=pd.DataFrame({'trading_date':[days[3]],'event_type':['FOMC']})
    by_type,broad,detail=event_study(corr,events,returns)
    assert detail.d1.iloc[0]==pytest.approx(.1)
    assert detail.d3.iloc[0]==pytest.approx(.3)
    assert by_type.loc[by_type.group.eq('CPI'),'n'].iloc[0]==0


def test_execution_cost_units_and_sides():
    assert option_execution_cost(-2,10,20,30)==pytest.approx(22.6)
    assert option_execution_cost(2,10,20,30,scenario='stress')==pytest.approx(42.6)
    assert stock_hedge_cost(-100,.02,'stress')==pytest.approx(4)
    assert futures_hedge_cost(-2,FuturesCostConfig())==pytest.approx(12.5)
    assert total_execution_cost(1,2,3)==6
    with pytest.raises(ValueError):
        option_execution_cost(1,1,2,3,scenario='unknown')


def test_quote_pair_compatibility_and_dollar_arithmetic():
    date=pd.Timestamp('2024-07-01')
    rows=[]
    for cp,bid,ask,delta,vega,oid in [('C',4.,5.,.5,12.,1),('P',3.,4.,-.5,8.,2)]:
        rows.append(dict(cp_flag=cp,exdate=date+pd.Timedelta(days=30),strike_price=100000,
            contract_size=100,am_settlement=0,expiry_indicator='M',delta=delta,vega=vega,
            optionid=oid,volume=20,open_interest=200,best_bid=bid,best_offer=ask))
    pairs=build_straddle_pairs(pd.DataFrame(rows),date)
    pair=select_straddle_pair(pairs,'liquidity_aware')
    result=calculate_straddle_cost(pair,date,1,'liquidity_aware')
    assert result['straddle_mid']==8
    assert result['half_spread_usd']==1
    assert result['one_way_cost_per_straddle_usd']==100
    assert result['vega_usd_per_vol_point']==pytest.approx(.2)
    assert result['cost_vol_points']==5 # Checks team's declared convention, not vendor unit certification.
    rows[1]['am_settlement']=1
    with pytest.raises(ValueError,match='compatible'):
        build_straddle_pairs(pd.DataFrame(rows),date)


def test_team_modules_import_without_network(monkeypatch):
    import requests
    from src.data import wrds_connection
    def forbidden(*a,**kw):
        raise AssertionError('Import attempted live access')
    monkeypatch.setattr(wrds_connection,'get_wrds_connection',forbidden)
    monkeypatch.setattr(requests,'get',forbidden)
    for name in ['src.events.analysis','src.events.cli','src.events.macro','src.backtest.transaction_costs',
                 'src.data.export_returns_weights','src.data.export_top30_straddle_costs',
                 'src.data.compare_straddle_costs','src.data.export_delta_hedge_costs']:
        importlib.reload(importlib.import_module(name))


def test_event_cli_paths_and_outputs(returns,tmp_path):
    from src.events.cli import main
    source=tmp_path/'returns.csv';returns.to_csv(source,index=False)
    output=tmp_path/'basket'
    assert main(['basket','--returns',str(source),'--window','4','--output',str(output),'--no-plots'])==0
    assert (output/'basket_correlation.csv').is_file()
    assert (output/'tables.xlsx').is_file()
    assert (output/'run.json').is_file()
