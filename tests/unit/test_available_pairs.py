"""Hand-checkable missing-input arithmetic; no generated market dataset."""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from src.research.errors import DataError
from src.research.inputs import weights_at
from src.research.measurement import available_pair_rc, pair_rc


# Compare to an independent pairwise Pearson matrix, retaining incomplete stocks.
def test_available_observations_match_pandas_pairs():
    x = np.array([[1, 4, np.nan], [2, 1, 3], [4, 2, 1], [3, 3, 2]], float)
    a = np.array([.1, .2, .3])
    result = available_pair_rc(x, a, min_sessions=3)
    upper = np.triu_indices(3, 1)
    weights = np.outer(a, a)[upper]
    expected = weights @ pd.DataFrame(x).corr(min_periods=3).to_numpy()[upper] / weights.sum()
    assert result['rc'] == pytest.approx(expected, abs=1e-12)
    assert result['pair_weight_coverage'] == pytest.approx(1)
    assert result['n_pairs_used'] == 3
    assert result['minimum_pair_observations'] == 3
    assert result['n_missing_return_observations'] == 1
    assert result['rc_method'] == 'available_pair_proxy'


# An unavailable stock does not discard the other pair or invent its returns.
def test_missing_stock_reports_original_pair_mass():
    x = np.array([[1, 3, np.nan], [2, 1, np.nan], [3, 2, np.nan]])
    result = available_pair_rc(x, [.1, .2, .3], min_sessions=3)
    assert result['rc'] == pytest.approx(-.5)
    assert result['n_pairs_used'] == 1
    assert result['pair_weight_coverage'] == pytest.approx(2/11)
    assert result['rc_available_pair_lower_bound'] == pytest.approx(-10/11)
    assert result['rc_available_pair_upper_bound'] == pytest.approx(8/11)
    assert np.isnan(x[:, 2]).all()


# The complete-panel fast identity remains exact and avoids pairwise loops.
def test_complete_fast_path_and_no_usable_pairs():
    x = np.array([[1, 3, 2], [2, 1, 4], [3, 2, 1]], float)
    result = available_pair_rc(x, [.1, .2, .3], min_sessions=3)
    assert result['rc'] == pytest.approx(pair_rc(x, [.1, .2, .3], explicit=True), abs=1e-12)
    assert result['rc_method'] == 'complete_fast'
    with pytest.raises(DataError, match='INSUFFICIENT_PAIR_OVERLAP'):
        available_pair_rc([[1, np.nan], [2, np.nan], [3, np.nan]], [.1, .2], min_sessions=3)


# Match Kevin's weighting-input omission while keeping the missing count visible.
def test_missing_cap_omits_stock_not_date_and_price_does_not_require_cap():
    date = pd.Timestamp('2024-01-02')
    bundle = SimpleNamespace(caps=pd.DataFrame({'permno': [1, 2, 3], 'date': date,
        'dlycap': [10, np.nan, 30], 'dlyprc': [1, 2, 3]}))
    w, cap = weights_at(bundle, [1, 2, 3], date, 'market_cap', allow_partial=True)
    np.testing.assert_allclose(w, [.25, np.nan, .75], equal_nan=True)
    assert np.isnan(cap).all()  # Missing original cap mass cannot be certified.
    w, _ = weights_at(bundle, [1, 2, 3], date, 'price', allow_partial=True)
    np.testing.assert_allclose(w, [1/6, 2/6, 3/6])
