
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


OPTION_COSTS_2019 = Path('data/transaction_costs/top30_2019/simulator_option_costs_2019.csv')


def load_option_costs(path=OPTION_COSTS_2019):
    """Load corrected per-straddle dollar costs; multipliers are already included."""
    frame = pd.read_csv(path)
    if any(c.startswith('fixed_stress') for c in frame.columns):
        raise ValueError('Legacy fixed_stress columns: regenerate the corrected export')
    required = ['base_cost_usd', 'stress_cost_usd', 'commission_usd']
    values = frame[required].apply(pd.to_numeric, errors='raise')
    if values.isna().any().any() or not ((values >= 0) & (values < float('inf'))).all().all():
        raise ValueError('Execution costs must be finite and nonnegative')
    return frame


@dataclass
class FuturesCostConfig:
    # ES: uncalibrated half-tick assumption = $6.25/contract/execution.
    half_spread_ticks: float = 0.5
    tick_value_usd: float = 12.50
    commission_per_contract: float = 0.0


def option_execution_cost(
    quantity: float,
    base_cost_per_straddle: float,
    stress_cost_per_straddle: float | None = None,
    *,
    commission_per_straddle: float = 1.30,
    scenario: str = "base",
) -> float:
    """
    Cost of trading a quantity of straddles.

    All input costs are in USD per one-way execution,
    excluding commissions.
    Base is an observed half-spread, already in dollars per straddle.
    If only that input is supplied, observed stress doubles it. Do not apply
    the contract multiplier again or pass commission-inclusive export columns.
    """
    costs = {
        "base": base_cost_per_straddle,
        "stress": (2 * base_cost_per_straddle if stress_cost_per_straddle is None
                   else stress_cost_per_straddle),
    }

    if scenario not in costs:
        raise ValueError(f"Unknown scenario: {scenario}")

    if quantity == 0:
        return 0.0

    return abs(quantity) * (
        costs[scenario] + commission_per_straddle
    )


def stock_hedge_cost(
    shares_traded: float,
    half_spread_per_share: float,
    scenario: str = "base",
) -> float:
    """
    Bid/ask execution cost for the net number of shares traded.
    """
    multiplier = {
        "base": 1.0,
        "stress": 2.0,
    }

    if scenario not in multiplier:
        raise ValueError(f"Unknown scenario: {scenario}")

    return (
        abs(shares_traded)
        * half_spread_per_share
        * multiplier[scenario]
    )


def futures_hedge_cost(
    contracts_traded: float,
    config: FuturesCostConfig,
) -> float:
    """
    Cost of trading futures, based on a configurable
    half-spread measured in ticks.
    """
    return abs(contracts_traded) * (
        config.half_spread_ticks * config.tick_value_usd
        + config.commission_per_contract
    )


def total_execution_cost(
    option_cost: float = 0.0,
    stock_cost: float = 0.0,
    futures_cost: float = 0.0,
) -> float:
    return option_cost + stock_cost + futures_cost
