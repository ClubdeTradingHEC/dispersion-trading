"""Small statistical fixtures, without a market simulator or external dataset."""
import numpy as np
import pandas as pd
import pytest
from src.research.config import Config
from src.research.inference import hac_mean, mean_test
from src.research.measurement import implied_correlation
from src.research.errors import DataError
from src.research.inputs import clean_returns


def test_hac_preserves_missing_session_distances():
    values = np.array([0.1, np.nan, 0.3, 0.2, -0.1, 0.2])
    good = np.isfinite(values)
    scores = np.where(good, values - values[good].mean(), 0)
    n = good.sum()
    omega = scores @ scores
    for lag in (1, 2):
        omega += 2 * (1 - lag / 3) * (scores[lag:] @ scores[:-lag])
    expected = np.sqrt(max(0, omega * n / (n - 1))) / n
    assert hac_mean(values, 2)["se_hac"] == pytest.approx(expected)
    assert hac_mean(values, 2)["grid_n"] == 6


def test_equivalence_uses_a_margin():
    cfg = Config(bootstrap_repetitions=99)
    assert mean_test(np.full(100, 0.001), 30, cfg, 0.02)["equivalent_bias_90pct"]
    assert not mean_test(np.full(100, 0.04), 30, cfg, 0.02)["equivalent_bias_90pct"]


def test_training_excludes_unavailable_labels():
    from src.research.modeling import train_for
    dates = pd.to_datetime(['2024-01-02','2024-01-03','2024-01-04','2024-01-05'])
    panel = pd.DataFrame({'date': dates, 'label_available_at': pd.to_datetime(['2024-01-03','2024-01-10','2024-01-05','2024-01-08']), 'complete_features': True, 'eligible_B': True})
    admitted = train_for(panel, '2024-01-05', 'A', {'training_start':'2024-01-01'})
    assert admitted.date.tolist() == list(dates[[0,2]])
    assert (admitted.label_available_at <= pd.Timestamp('2024-01-05')).all()


@pytest.mark.parametrize("index_iv", [0, -1, float("nan"), float("inf")])
def test_invalid_index_iv_rejected(index_iv):
    with pytest.raises(DataError, match="INVALID_IC_INPUT"):
        implied_correlation(index_iv, [0.5, 0.5], [0.2, 0.2])


def test_vendor_duration_flags_do_not_discard_valid_returns():
    dates = pd.to_datetime(["2024-01-05", "2024-01-08"])
    frame = pd.DataFrame({"date": dates, "return": [0.01, 0.02],
        "dlyretmissflg": ["NA", "NA"], "dlyretdurflg": ["D1", "D3"]})
    assert clean_returns(frame, dates)["return"].notna().all()
    for flag in ('D1', 'DD', 'DU'):
        frame.loc[1, "dlyretdurflg"] = flag
        assert clean_returns(frame, dates).loc[1, "return"] == .02
    frame.loc[1, 'return'] = np.nan
    assert pd.isna(clean_returns(frame, dates).loc[1, 'return'])


@pytest.mark.parametrize("confirmed,source", [(False, "dictionary"), (True, ""), (True, " ")])
def test_uncertified_rates_cannot_enter_real_data_path(confirmed, source):
    with pytest.raises(DataError, match="RATE_CONVENTION_UNCERTIFIED"):
        Config(rate_unit="percent", rate_convention_confirmed=confirmed, rate_confirmation_source=source).require_rate_certification()
