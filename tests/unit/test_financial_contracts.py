"""Known-answer financial checks; no simulated stock market or data generator."""
from math import exp, erf, sqrt
import numpy as np
import pandas as pd
import pytest
from src.data.option_pricing import black_price, invert_combined_iv
from src.data.rates import rate_convert, zero_rate
from src.research.measurement import implied_correlation, pair_rc, miv, mic_comparators
from src.research.errors import DataError

@pytest.mark.parametrize("days", [30, 60, 91])
@pytest.mark.parametrize("rate", [0.00191598, 0.04, -0.01])
def test_atm_closed_form(days, rate):
    t = days / 365
    value = exp(-rate*t)*100*erf(0.28*sqrt(t)/(2*sqrt(2)))
    assert black_price(100, 100, t, rate, 0.28, "C") == pytest.approx(value, abs=1e-12)
    assert black_price(100, 100, t, rate, 0.28, "P") == pytest.approx(value, abs=1e-12)

@pytest.mark.parametrize("days", [30, 60, 91])
@pytest.mark.parametrize("sigma", [0.2, 0.8, 2.0])
def test_package_root_recovers_known_volatility(days, sigma):
    c = black_price(100, 98, days/365, 0.01, sigma, "C")
    p = black_price(100, 103, days/365, 0.01, sigma, "P")
    assert invert_combined_iv(c,p,98,103,100,0.01,days) == pytest.approx(sigma, abs=1e-10)

@pytest.mark.parametrize("raw,expected", [(0.191598,0.00191598),(4.0,0.04),(-0.5,-0.005)])
def test_percentage_rates(raw, expected):
    assert rate_convert(raw, "percent") == pytest.approx(expected)
    assert rate_convert(raw, "decimal") == raw

def test_rate_units_must_be_explicit():
    with pytest.raises(DataError, match="RATE_UNIT_UNDECLARED"):
        rate_convert(0.191598, None)

def test_interpolation_and_no_extrapolation():
    date = pd.Timestamp("2024-01-02")
    curve = pd.DataFrame({"date":[date,date],"days":[10,50],"rate":[0.1,0.3]})
    raw,rate = zero_rate(curve,date,30,"percent")
    assert raw == pytest.approx(0.2)
    assert rate == pytest.approx(0.002)
    with pytest.raises(DataError, match="UNBRACKETED_ZERO_CURVE"):
        zero_rate(curve,date,91,"percent")

def test_duplicate_curve_rejected():
    date=pd.Timestamp("2024-01-02")
    curve=pd.DataFrame({"date":[date,date],"days":[30,30],"rate":[0.1,0.1]})
    with pytest.raises(DataError, match="DUPLICATE_ZERO_CURVE"):
        zero_rate(curve,date,30,"percent")

def test_ic_identity_and_unclipped_diagnostic():
    # Two equally weighted 20% volatility legs at 50% correlation.
    result=implied_correlation(sqrt(0.03),[0.5,0.5],[0.2,0.2])
    assert result["ic"] == pytest.approx(0.5)
    result=implied_correlation(0.3,[0.5,0.5],[0.2,0.2])
    assert result["ic"] > 1 and result["ic_out_of_bounds"]

def test_fast_pair_aggregate_matches_explicit_pairs():
    x=np.array([[1,2,4],[2,1,3],[4,5,2],[3,4,1]],float)
    assert pair_rc(x,[0.1,0.2,0.3]) == pytest.approx(pair_rc(x,[0.1,0.2,0.3],explicit=True),abs=1e-12)

def test_exact_fixed_basket_mic_identity():
    x=np.array([[1,2,4],[2,1,3],[4,5,2],[3,4,1]],float)
    result=mic_comparators(x,x@np.array([0.2,0.3,0.5]),[0.2,0.3,0.5],[0.2,0.3,0.4])
    assert result["mic_identity_residual"] == pytest.approx(0,abs=1e-12)
    assert result["return_tracking_error_annual"] == pytest.approx(0,abs=1e-12)

def test_marshall_contributions():
    total,contrib=miv(np.array([0.4,0.6]),np.array([0.2,0.3]),np.array([0.5,0.8]))
    assert total == pytest.approx(0.184)
    np.testing.assert_allclose(contrib,[0.04,0.144])

@pytest.mark.parametrize("x,code", [([[1,2],[1,3]],"ZERO_VARIANCE_RETURNS"),([[1,float('nan')],[2,3]],"INCOMPLETE_PAIR_GRID")])
def test_pair_grid_failure(x,code):
    with pytest.raises(DataError,match=code): pair_rc(x,[0.1,0.2])
