"""Hand-checkable execution arithmetic, lossless export and signal boundaries."""
import csv
import json

import pytest

from src.backtest.cli import main
from src.backtest.signals import passes_marshall_hurdle
from src.backtest.transaction_costs import (
    FuturesCostConfig, futures_hedge_cost, load_option_costs,
    option_execution_cost, stock_hedge_cost,
)
from src.data.add_stress_scenario import export_option_costs


@pytest.mark.parametrize('quantity', [-3, 0, 2])
def test_observed_costs(quantity):
    # $10 is already the dollar half-spread per straddle, multiplier included.
    assert option_execution_cost(quantity, 10) == abs(quantity) * 11.30
    assert option_execution_cost(quantity, 10, scenario='stress') == abs(quantity) * 21.30
    assert option_execution_cost(quantity, 10, 20, scenario='stress') == abs(quantity) * 21.30
    assert option_execution_cost(quantity, 10, commission_per_straddle=2) == abs(quantity) * 12
    assert stock_hedge_cost(quantity, .02) == abs(quantity) * .02
    assert stock_hedge_cost(quantity, .02, 'stress') == abs(quantity) * .04
    assert futures_hedge_cost(quantity, FuturesCostConfig()) == abs(quantity) * 6.25
    assert futures_hedge_cost(quantity, FuturesCostConfig(commission_per_contract=1)) == abs(quantity) * 7.25


def test_fixed_scenario_rejected():
    with pytest.raises(ValueError, match='Unknown scenario'):
        option_execution_cost(1, 10, scenario='fixed_stress')
    with pytest.raises(ValueError, match='Unknown scenario'):
        stock_hedge_cost(1, .02, 'fixed_stress')


@pytest.mark.parametrize('unit,scale', [('decimal', 1), ('percentage_points', 100)])
def test_signal_hurdle(unit, scale):
    for sign in [-1, 1]:
        assert passes_marshall_hurdle(sign * .01 * scale, 0, iv_unit=unit)
        assert not passes_marshall_hurdle(sign * .0408 * scale, 0, enabled=True, iv_unit=unit)
        assert passes_marshall_hurdle(sign * .0409 * scale, 0, enabled=True, iv_unit=unit)
        assert passes_marshall_hurdle(sign * .041 * scale, 0, enabled=True, iv_unit=unit)
    assert not passes_marshall_hurdle(.20 * scale, .18 * scale, enabled=True, iv_unit=unit)


def test_signal_invalid_input():
    with pytest.raises(ValueError):
        passes_marshall_hurdle(float('nan'), .1)
    with pytest.raises(ValueError):
        passes_marshall_hurdle(.2, .1, iv_unit='auto')


def test_export_and_loading(tmp_path, capsys):
    source, target = tmp_path / 'original.csv', tmp_path / 'corrected.csv'
    rows = [
        ['ticker', 'base_cost_usd', 'fixed_stress_cost_usd', 'stress_cost_usd', 'commission_usd', 'note'],
        ['B', '10.000', '999', '20.00', '1.30', ''],
        ['A', '5', '888', '10', '1.30', 'a,b'],
    ]
    with source.open('w', newline='') as handle:
        csv.writer(handle).writerows(rows)
    before = source.read_bytes()
    assert export_option_costs(source, target) == 2
    assert source.read_bytes() == before
    with target.open(newline='') as handle:
        assert list(csv.reader(handle)) == [[row[i] for i in (0, 1, 3, 4, 5)] for row in rows]
    assert list(load_option_costs(target).ticker) == ['B', 'A']
    assert main(['load-options', '--input', str(target)]) == 0
    assert json.loads(capsys.readouterr().out)['rows'] == 2
    with pytest.raises(ValueError, match='Legacy'):
        load_option_costs(source)
    with pytest.raises(ValueError, match='preserved'):
        export_option_costs(source, source)


def test_signal_cli_default_and_opt_in(capsys):
    args = ['signal', '--ioiv', '.20', '--miv', '.18']
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == {'hurdle_enabled': False, 'hurdle_passed': True}
    assert main(args + ['--marshall-hurdle']) == 0
    assert json.loads(capsys.readouterr().out) == {'hurdle_enabled': True, 'hurdle_passed': False}
